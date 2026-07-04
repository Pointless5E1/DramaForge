from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlmodel import Session
from app.db.session import get_session
from app.schemas.prompt import PromptRead, PromptCreate, PromptUpdate
from app.schemas.response import ApiResponse
from app.services import prompt_service

router = APIRouter()

@router.post("/", response_model=ApiResponse[PromptRead], summary="創建新提示詞")
def create_prompt(
    *,
    session: Session = Depends(get_session),
    prompt: PromptCreate,
):
    """
    創建一個新的提示詞模板。
    """
    new_prompt = prompt_service.create_prompt(session=session, prompt_create=prompt)
    return ApiResponse(data=new_prompt)

@router.get("/", response_model=ApiResponse[List[PromptRead]], summary="獲取提示詞列表")
def read_prompts(
    *,
    session: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
):
    """
    獲取所有提示詞模板的列表。
    """
    prompts = prompt_service.get_prompts(session=session, skip=skip, limit=limit)
    return ApiResponse(data=prompts)

@router.get("/{prompt_id}", response_model=ApiResponse[PromptRead], summary="獲取單個提示詞")
def read_prompt(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
):
    """
    根據ID獲取單個提示詞模板的詳細信息。
    """
    db_prompt = prompt_service.get_prompt(session=session, prompt_id=prompt_id)
    if not db_prompt:
        raise HTTPException(status_code=404, detail="提示詞未找到")
    return ApiResponse(data=db_prompt)

@router.put("/{prompt_id}", response_model=ApiResponse[PromptRead], summary="更新提示詞")
def update_prompt(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
    prompt: PromptUpdate,
):
    """
    更新一個已存在的提示詞模板。
    """
    updated_prompt = prompt_service.update_prompt(session=session, prompt_id=prompt_id, prompt_update=prompt)
    if not updated_prompt:
        raise HTTPException(status_code=404, detail="提示詞未找到")
    return ApiResponse(data=updated_prompt)

@router.delete("/{prompt_id}", response_model=ApiResponse, summary="刪除提示詞")
def delete_prompt(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
):
    """
    刪除一個提示詞模板。
    """
    db_prompt = prompt_service.get_prompt(session=session, prompt_id=prompt_id)
    if not db_prompt:
        raise HTTPException(status_code=404, detail="提示詞未找到")
    if getattr(db_prompt, 'built_in', False):
        raise HTTPException(status_code=400, detail="系統內置提示詞不可刪除")
    if not prompt_service.delete_prompt(session=session, prompt_id=prompt_id):
        raise HTTPException(status_code=404, detail="提示詞未找到")
    return ApiResponse(message="提示詞刪除成功") 