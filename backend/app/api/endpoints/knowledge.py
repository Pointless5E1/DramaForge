from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List

from app.db.session import get_session
from app.schemas.prompt import KnowledgeRead, KnowledgeCreate, KnowledgeUpdate
from app.schemas.response import ApiResponse
from app.services.knowledge_service import KnowledgeService

router = APIRouter()

@router.get('/', response_model=ApiResponse[List[KnowledgeRead]], summary='獲取知識庫列表')
def list_knowledge(session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    items = svc.list()
    return ApiResponse(data=items)

@router.post('/', response_model=ApiResponse[KnowledgeRead], summary='創建知識庫')
def create_knowledge(body: KnowledgeCreate, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    if svc.get_by_name(body.name):
        raise HTTPException(status_code=400, detail='同名知識庫已存在')
    item = svc.create(name=body.name, description=body.description, content=body.content)
    return ApiResponse(data=item)

@router.get('/{kid}', response_model=ApiResponse[KnowledgeRead], summary='獲取單個知識庫')
def get_knowledge(kid: int, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    item = svc.get_by_id(kid)
    if not item:
        raise HTTPException(status_code=404, detail='知識庫不存在')
    return ApiResponse(data=item)

@router.put('/{kid}', response_model=ApiResponse[KnowledgeRead], summary='更新知識庫')
def update_knowledge(kid: int, body: KnowledgeUpdate, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    item = svc.update(kid, name=body.name, description=body.description, content=body.content)
    if not item:
        raise HTTPException(status_code=404, detail='知識庫不存在')
    return ApiResponse(data=item)

@router.delete('/{kid}', response_model=ApiResponse, summary='刪除知識庫')
def delete_knowledge(kid: int, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    item = svc.get_by_id(kid)
    if not item:
        raise HTTPException(status_code=404, detail='知識庫不存在')
    if getattr(item, 'built_in', False):
        raise HTTPException(status_code=400, detail='系統內置知識庫不可刪除')
    ok = svc.delete(kid)
    if not ok:
        raise HTTPException(status_code=404, detail='知識庫不存在')
    return ApiResponse(message='刪除成功') 