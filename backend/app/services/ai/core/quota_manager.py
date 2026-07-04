"""LLM配額管理

負責配額預檢和使用統計記錄。
"""

from typing import Tuple
from sqlmodel import Session
from loguru import logger

from app.services import llm_config_service


def precheck_quota(
    session: Session,
    llm_config_id: int,
    input_tokens: int,
    need_calls: int = 1
) -> Tuple[bool, str]:
    """預檢配額是否足夠
    
    Args:
        session: 數據庫會話
        llm_config_id: LLM配置ID
        input_tokens: 預計輸入token數
        need_calls: 預計調用次數
        
    Returns:
        (是否通過, 原因說明)
    """
    return llm_config_service.can_consume(
        session, llm_config_id, input_tokens, 0, need_calls
    )


def record_usage(
    session: Session,
    llm_config_id: int,
    input_tokens: int,
    output_tokens: int,
    calls: int = 1,
    aborted: bool = False
) -> None:
    """記錄LLM使用情況
    
    Args:
        session: 數據庫會話
        llm_config_id: LLM配置ID
        input_tokens: 實際輸入token數
        output_tokens: 實際輸出token數
        calls: 調用次數
        aborted: 是否被中止
    """
    try:
        llm_config_service.accumulate_usage(
            session, llm_config_id,
            max(0, input_tokens),
            max(0, output_tokens),
            max(0, calls),
            aborted=aborted
        )
    except Exception as e:
        logger.warning(f"記錄LLM統計失敗: {e}")
