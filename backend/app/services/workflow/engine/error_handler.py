"""統一的錯誤處理器

職責：
- 統一處理節點執行錯誤
- 處理任務取消
- 保存錯誤信息到狀態
"""

import asyncio
from typing import TYPE_CHECKING
from loguru import logger
from sqlmodel import Session

if TYPE_CHECKING:
    from .execution_state import ExecutionState
    from ..engine.execution_plan import Statement
    from .async_executor import ProgressEvent


class ExecutionError(Exception):
    """執行錯誤基類"""
    def __init__(self, node_id: str, message: str, details: dict = None):
        self.node_id = node_id
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NodeExecutionError(ExecutionError):
    """節點執行錯誤"""
    pass


class CheckpointError(ExecutionError):
    """檢查點錯誤"""
    pass


class ErrorHandler:
    """統一的錯誤處理器"""
    
    @staticmethod
    async def handle_node_error(
        error: Exception,
        stmt: 'Statement',
        execution_state: 'ExecutionState',
        session: Session
    ) -> 'ProgressEvent':
        """處理節點執行錯誤
        
        Args:
            error: 異常對象
            stmt: 語句對象
            execution_state: 執行狀態
            session: 數據庫會話
            
        Returns:
            錯誤事件
        """
        from .async_executor import ProgressEvent
        
        logger.error(f"[ErrorHandler] 節點執行失敗: {stmt.variable}, 錯誤: {error}")
        
        # 更新節點狀態
        execution_state.update_node_state(
            node_id=stmt.variable,
            node_type=stmt.node_type or "unknown",
            status="error",
            error=str(error)
        )
        
        # 保存狀態
        execution_state.save(session)
        
        # 返回錯誤事件
        return ProgressEvent(
            statement=stmt,
            type='error',
            error=str(error)
        )
    
    @staticmethod
    async def handle_cancellation(
        stmt: 'Statement',
        execution_state: 'ExecutionState',
        session: Session
    ):
        """處理任務取消
        
        當異步任務被取消時調用，保存當前進度。
        
        Args:
            stmt: 語句對象
            execution_state: 執行狀態
            session: 數據庫會話
        """
        logger.info(f"[ErrorHandler] 任務被取消: {stmt.variable}")
        
        # 獲取當前進度
        node_state = execution_state.get_node_state(stmt.variable)
        current_progress = node_state.progress if node_state else 0.0
        
        # 標記爲暫停狀態
        execution_state.update_node_state(
            node_id=stmt.variable,
            node_type=stmt.node_type or "unknown",
            status="paused",
            progress=current_progress
        )
        
        # 保存狀態
        execution_state.save(session)
        
        logger.info(f"[ErrorHandler] 任務取消已處理: {stmt.variable}, 進度={current_progress}%")
