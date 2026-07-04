"""
靈感助手專用接口
支持工具調用的對話
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import AsyncGenerator
from loguru import logger

from app.db.session import get_session
from app.services.ai.assistant.assistant_service import generate_assistant_chat_streaming
from app.schemas.ai import AssistantChatRequest
from app.utils.stream_utils import wrap_sse_stream

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat")
async def assistant_chat(
    request: AssistantChatRequest,
    session: Session = Depends(get_session)
):
    """
    靈感助手對話接口（支持工具調用）
    
    特點：
    - 專用請求模型（語義清晰）
    - 自動注入工具集
    - 支持流式輸出
    - 支持工具調用結果返回
    """
    # 加載系統提示詞（根據模式選擇不同的提示詞）
    from app.services import prompt_service
    
    prompt_name = request.prompt_name
    react_enabled = bool(getattr(request, "react_mode_enabled", False))

    if react_enabled:
        react_prompt_name = f"{prompt_name}-React"
        p = prompt_service.get_prompt_by_name(session, react_prompt_name)
        if p and p.template:
            system_prompt = str(p.template)
            logger.info(f"[Assistant API] React 模式啓用，使用提示詞 {react_prompt_name}")
        else:
            logger.warning(f"[Assistant API] React 模式啓用但未找到 {react_prompt_name}，退回標準提示詞 {prompt_name}")
            p = prompt_service.get_prompt_by_name(session, prompt_name)
            if not p or not p.template:
                raise HTTPException(status_code=400, detail=f"未找到提示詞: {prompt_name}")
            system_prompt = str(p.template)
    else:
        p = prompt_service.get_prompt_by_name(session, prompt_name)
        if not p or not p.template:
            raise HTTPException(status_code=400, detail=f"未找到提示詞: {prompt_name}")
        system_prompt = str(p.template)
    
    # 所有模式統一走 LangChain ChatModel + Tools 管線
    async def stream_with_tools() -> AsyncGenerator[str, None]:
        logger.info("[Assistant API] 使用{}模式".format("React" if react_enabled else "標準"))
        async for chunk in generate_assistant_chat_streaming(
            session=session,
            request=request,
            system_prompt=system_prompt,
            track_stats=True,
        ):
            yield chunk
    
    return StreamingResponse(
        wrap_sse_stream(stream_with_tools()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
