"""狀態管理器 - 管理工作流運行時狀態"""

from typing import Dict, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from loguru import logger

from app.db.models import WorkflowRun, NodeExecutionState
from ..types import NodeStatus, RunStatus


class StateManager:
    """工作流狀態管理器
    
    職責：
    - 持久化運行狀態
    - 管理節點執行狀態
    - 支持暫停/恢復
    - 提供狀態查詢接口
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    # ==================== Run 狀態管理 ====================
    
    def update_run_status(
        self, 
        run_id: int, 
        status: RunStatus,
        **kwargs
    ) -> WorkflowRun:
        """更新運行狀態
        
        Args:
            run_id: 運行ID
            status: 新狀態
            **kwargs: 其他要更新的字段
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError(f"運行不存在: {run_id}")
        
        run.status = status
        
        # 更新時間戳
        if status == "running" and not run.started_at:
            run.started_at = datetime.now()  # 使用本地時間
        elif status in ("succeeded", "failed", "cancelled", "timeout"):
            run.finished_at = datetime.now()  # 使用本地時間
        
        # 更新其他字段
        for key, value in kwargs.items():
            if hasattr(run, key):
                setattr(run, key, value)
        
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        
        # logger.debug(f"[StateManager] 運行狀態更新: run_id={run_id}, status={status}")
        return run
    
    def save_run_state(
        self, 
        run_id: int, 
        state: Dict[str, Any]
    ) -> None:
        """保存運行時狀態（變量、節點輸出等）"""
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError(f"運行不存在: {run_id}")
        
        # 轉換狀態使其可JSON序列化（例如將set轉爲list）
        serializable_state = self._make_json_serializable(state)
        
        run.state_json = serializable_state
        self.session.add(run)
        self.session.commit()
    
    def _make_json_serializable(self, obj: Any) -> Any:
        """遞歸轉換對象爲JSON可序列化的格式
        
        主要處理：
        - set -> list
        - 其他不可序列化類型根據需要添加
        """
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        else:
            return obj
    
    def get_run_state(self, run_id: int) -> Optional[Dict[str, Any]]:
        """獲取運行時狀態"""
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            return None
        return run.state_json or {}
    
    def save_error(
        self, 
        run_id: int, 
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """保存錯誤信息"""
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            return
        
        run.error_json = {
            "message": error_message,
            "details": error_details or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        self.session.add(run)
        self.session.commit()
    
    # ==================== Node 狀態管理 ====================
    
    def create_node_state(
        self,
        run_id: int,
        node_id: str,
        node_type: str
    ) -> NodeExecutionState:
        """創建或獲取節點執行狀態記錄（upsert）"""
        # 先嚐試查找現有記錄
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()

        if state:
            # 如果已存在，重置狀態（用於重新執行）
            state.node_type = node_type
            state.status = "idle"
            state.start_time = None
            state.end_time = None
            state.progress = 0
            state.error_message = None
            state.inputs_json = None
            state.outputs_json = None
            state.logs_json = None
            state.updated_at = datetime.utcnow()
            logger.info(f"[StateManager] 重置節點狀態: run_id={run_id}, node_id={node_id}")
        else:
            # 不存在則創建新記錄
            state = NodeExecutionState(
                run_id=run_id,
                node_id=node_id,
                node_type=node_type,
                status="idle"
            )
            logger.info(f"[StateManager] 創建節點狀態: run_id={run_id}, node_id={node_id}")

        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)
        return state
    
    def update_node_status(
        self,
        run_id: int,
        node_id: str,
        status: NodeStatus,
        **kwargs
    ) -> Optional[NodeExecutionState]:
        """更新節點狀態
        
        Args:
            run_id: 運行ID
            node_id: 節點ID
            status: 新狀態
            **kwargs: 其他要更新的字段（如 progress, error_message 等）
        """
        # 查找節點狀態記錄
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if not state:
            logger.warning(
                f"[StateManager] 節點狀態記錄不存在: run_id={run_id}, node_id={node_id}"
            )
            return None
        
        state.status = status
        state.updated_at = datetime.utcnow()
        
        # 更新時間戳
        if status == "running" and not state.start_time:
            state.start_time = datetime.utcnow()
        elif status in ("success", "error", "skipped"):
            state.end_time = datetime.utcnow()
        
        # 更新其他字段
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        
        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)
        
        return state
    
    def save_node_inputs(
        self,
        run_id: int,
        node_id: str,
        inputs: Dict[str, Any]
    ) -> None:
        """保存節點輸入"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if state:
            state.inputs_json = inputs
            self.session.add(state)
            self.session.commit()
    
    def save_node_outputs(
        self,
        run_id: int,
        node_id: str,
        outputs: Dict[str, Any]
    ) -> None:
        """保存節點輸出"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if state:
            state.outputs_json = outputs
            self.session.add(state)
            self.session.commit()
    
    def add_node_log(
        self,
        run_id: int,
        node_id: str,
        level: str,
        message: str,
        **kwargs
    ) -> None:
        """添加節點日誌"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if state:
            logs = state.logs_json or []
            logs.append({
                "level": level,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                **kwargs
            })
            state.logs_json = logs
            self.session.add(state)
            self.session.commit()
    
    def get_node_state(
        self,
        run_id: int,
        node_id: str
    ) -> Optional[NodeExecutionState]:
        """獲取節點狀態"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        return self.session.exec(stmt).first()
    
    def get_all_node_states(self, run_id: int) -> list[NodeExecutionState]:
        """獲取運行的所有節點狀態"""
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id
        )
        return list(self.session.exec(stmt).all())
    
    def clear_node_states(self, run_id: int) -> None:
        """清理運行的所有節點狀態
        
        在開始新的運行前調用，確保沒有舊數據幹擾
        """
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id
        )
        old_states = self.session.exec(stmt).all()
        
        for state in old_states:
            self.session.delete(state)
        
        if old_states:
            self.session.commit()
            logger.info(f"[StateManager] 清理了 {len(old_states)} 箇舊節點狀態: run_id={run_id}")

    # ==================== 檢查點管理 ====================
    
    def save_checkpoint(
        self,
        run_id: int,
        node_id: str,
        percent: float,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """保存節點檢查點
        
        Args:
            run_id: 運行 ID
            node_id: 節點 ID（變量名）
            percent: 進度百分比（0-100）
            message: 進度消息
            data: 檢查點數據（輕量級元數據，< 10KB）
        
        注意：
        - data 只保存位置信息（索引、計數器、ID等）
        - 不保存業務數據（卡片內容、處理結果等）
        - 大小限制：< 10KB
        """
        # 驗證數據大小
        if data:
            import json
            data_size = len(json.dumps(data))
            if data_size > 10 * 1024:  # 10KB
                logger.warning(
                    f"[Checkpoint] 檢查點數據過大: {node_id}, "
                    f"大小={data_size} bytes, 建議 < 10KB"
                )
        
        # 構造檢查點 JSON
        checkpoint_json = {
            "percent": percent,
            "message": message,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 查找或創建 NodeExecutionState
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if not state:
            # 創建新狀態（通常不應該發生，但爲了健壯性）
            logger.warning(
                f"[Checkpoint] 節點狀態不存在，創建新狀態: run_id={run_id}, node_id={node_id}"
            )
            state = NodeExecutionState(
                run_id=run_id,
                node_id=node_id,
                node_type="unknown",
                status="running",
                progress=percent,
                checkpoint_json=checkpoint_json
            )
            self.session.add(state)
        else:
            # 更新現有狀態
            state.progress = percent
            state.checkpoint_json = checkpoint_json
            state.updated_at = datetime.utcnow()
        
        self.session.commit()
        logger.debug(
            f"[Checkpoint] 保存: {node_id}, "
            f"進度={percent}%, 消息={message}"
        )
    
    def load_checkpoint(
        self,
        run_id: int,
        node_id: str
    ) -> Optional[Dict[str, Any]]:
        """加載節點檢查點
        
        Args:
            run_id: 運行 ID
            node_id: 節點 ID（變量名）
            
        Returns:
            檢查點數據，格式：
            {
                "percent": 50.0,
                "message": "已處理 30/60",
                "data": {"processed_count": 30},
                "timestamp": "2026-02-04T10:30:00"
            }
            如果不存在則返回 None
        """
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id,
            NodeExecutionState.node_id == node_id
        )
        state = self.session.exec(stmt).first()
        
        if state and state.checkpoint_json:
            logger.debug(
                f"[Checkpoint] 加載: {node_id}, "
                f"進度={state.checkpoint_json.get('percent')}%"
            )
            return state.checkpoint_json
        
        return None
