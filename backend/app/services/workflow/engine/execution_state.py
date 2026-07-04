"""統一的執行狀態管理

職責：
- 統一管理執行上下文、節點狀態、檢查點
- 提供統一的加載和保存接口
- 確保狀態一致性
"""

from dataclasses import dataclass
from typing import Dict, Any, Set, Optional
from datetime import datetime
from sqlmodel import Session, select
from loguru import logger

from app.db.models import NodeExecutionState


@dataclass
class CheckpointData:
    """檢查點數據"""
    percent: float
    message: str
    data: Optional[Dict[str, Any]]
    timestamp: datetime


@dataclass
class NodeState:
    """節點狀態"""
    node_id: str
    node_type: str
    status: str  # idle, running, success, error, paused
    progress: float
    outputs: Optional[Dict[str, Any]]
    checkpoint: Optional[CheckpointData]
    error: Optional[str]


class ExecutionState:
    """統一的執行狀態
    
    職責：
    - 管理所有執行狀態（上下文、節點狀態、檢查點）
    - 提供統一的加載和保存接口
    - 確保狀態一致性
    
    使用示例：
        # 加載狀態
        state = ExecutionState.load(run_id, session)
        
        # 更新節點狀態
        state.update_node_state(
            node_id="task_a",
            node_type="Example.Process",
            status="running",
            progress=50.0
        )
        
        # 保存狀態
        state.save(session)
    """
    
    def __init__(self, run_id: int):
        self.run_id = run_id
        self.context: Dict[str, Any] = {}  # 執行上下文（變量值）
        self.completed_nodes: Set[str] = set()  # 已完成的節點
        self.node_states: Dict[str, NodeState] = {}  # 節點狀態
    
    @classmethod
    def load(cls, run_id: int, session: Session) -> 'ExecutionState':
        """從數據庫加載完整狀態
        
        Args:
            run_id: 運行 ID
            session: 數據庫會話
            
        Returns:
            ExecutionState 實例
        """
        state = cls(run_id)
        
        # 加載所有節點狀態
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == run_id
        )
        db_states = session.exec(stmt).all()
        
        if not db_states:
            logger.info(f"[ExecutionState] 沒有找到節點狀態: run_id={run_id}")
            return state
        
        logger.info(f"[ExecutionState] 加載節點狀態: run_id={run_id}, 節點數={len(db_states)}")
        
        for db_state in db_states:
            # 構建檢查點數據
            checkpoint = None
            if db_state.checkpoint_json:
                checkpoint = CheckpointData(
                    percent=db_state.checkpoint_json.get('percent', 0.0),
                    message=db_state.checkpoint_json.get('message', ''),
                    data=db_state.checkpoint_json.get('data'),
                    timestamp=datetime.fromisoformat(
                        db_state.checkpoint_json.get('timestamp', datetime.utcnow().isoformat())
                    )
                )
            
            # 構建節點狀態
            node_state = NodeState(
                node_id=db_state.node_id,
                node_type=db_state.node_type,
                status=db_state.status,
                progress=db_state.progress or 0.0,
                outputs=db_state.outputs_json,
                checkpoint=checkpoint,
                error=db_state.error_message
            )
            
            state.node_states[db_state.node_id] = node_state
            
            # 詳細日誌：記錄每個節點的狀態和輸出
            logger.info(
                f"[ExecutionState] 加載節點: {db_state.node_id}, "
                f"status={db_state.status}, "
                f"has_outputs={db_state.outputs_json is not None}, "
                f"outputs_keys={list(db_state.outputs_json.keys()) if db_state.outputs_json else []}"
            )
            
            # 恢復已完成節點（包括 success 和 skipped）
            if db_state.status in ("success", "skipped"):
                state.completed_nodes.add(db_state.node_id)
                if db_state.outputs_json:
                    state.context[db_state.node_id] = db_state.outputs_json
                    logger.info(
                        f"[ExecutionState] ✅ 恢復節點輸出到上下文: {db_state.node_id} "
                        f"(status={db_state.status}, outputs={db_state.outputs_json})"
                    )
                else:
                    logger.warning(
                        f"[ExecutionState] ⚠️ 節點狀態爲 {db_state.status} 但 outputs_json 爲 None: {db_state.node_id}"
                    )
        
        logger.info(
            f"[ExecutionState] 狀態加載完成: run_id={run_id}, "
            f"已完成={len(state.completed_nodes)}個節點, "
            f"上下文變量={list(state.context.keys())}"
        )
        
        return state
    
    def save(self, session: Session):
        """保存完整狀態到數據庫
        
        批量保存所有節點狀態，減少數據庫操作。
        
        Args:
            session: 數據庫會話
        """
        if not self.node_states:
            return
        
        for node_id, node_state in self.node_states.items():
            # 查找或創建節點狀態記錄
            stmt = select(NodeExecutionState).where(
                NodeExecutionState.run_id == self.run_id,
                NodeExecutionState.node_id == node_id
            )
            db_state = session.exec(stmt).first()
            
            if not db_state:
                db_state = NodeExecutionState(
                    run_id=self.run_id,
                    node_id=node_id,
                    node_type=node_state.node_type
                )
            
            # 更新狀態
            db_state.status = node_state.status
            db_state.progress = node_state.progress
            db_state.outputs_json = node_state.outputs  # 保存輸出用於斷點續傳
            db_state.error_message = node_state.error
            db_state.updated_at = datetime.utcnow()
            
            # 更新時間戳
            if node_state.status == "running" and not db_state.start_time:
                db_state.start_time = datetime.utcnow()
            elif node_state.status in ("success", "error", "paused"):
                if not db_state.end_time:
                    db_state.end_time = datetime.utcnow()
            
            # 更新檢查點
            if node_state.checkpoint:
                db_state.checkpoint_json = {
                    'percent': node_state.checkpoint.percent,
                    'message': node_state.checkpoint.message,
                    'data': node_state.checkpoint.data,
                    'timestamp': node_state.checkpoint.timestamp.isoformat()
                }
            
            session.add(db_state)
        
        session.commit()
        logger.debug(f"[ExecutionState] 狀態已保存: run_id={self.run_id}, 節點數={len(self.node_states)}")
    
    def get_node_state(self, node_id: str) -> Optional[NodeState]:
        """獲取節點狀態
        
        Args:
            node_id: 節點 ID
            
        Returns:
            節點狀態，如果不存在返回 None
        """
        return self.node_states.get(node_id)
    
    def update_node_state(
        self,
        node_id: str,
        node_type: str,
        status: str,
        progress: float = 0.0,
        outputs: Optional[Dict[str, Any]] = None,
        checkpoint: Optional[CheckpointData] = None,
        error: Optional[str] = None
    ):
        """更新節點狀態
        
        Args:
            node_id: 節點 ID
            node_type: 節點類型
            status: 狀態
            progress: 進度（0-100）
            outputs: 輸出數據
            checkpoint: 檢查點數據
            error: 錯誤信息
        """
        if node_id not in self.node_states:
            # 創建新狀態
            self.node_states[node_id] = NodeState(
                node_id=node_id,
                node_type=node_type,
                status=status,
                progress=progress,
                outputs=outputs,
                checkpoint=checkpoint,
                error=error
            )
        else:
            # 更新現有狀態
            node_state = self.node_states[node_id]
            node_state.status = status
            node_state.progress = progress
            if outputs is not None:
                node_state.outputs = outputs
            if checkpoint is not None:
                node_state.checkpoint = checkpoint
            if error is not None:
                node_state.error = error
        
        # 更新已完成列表和上下文
        if status == "success":
            self.completed_nodes.add(node_id)
            if outputs:
                self.context[node_id] = outputs
    
    def is_completed(self, node_id: str) -> bool:
        """檢查節點是否已完成
        
        Args:
            node_id: 節點 ID
            
        Returns:
            是否已完成
        """
        return node_id in self.completed_nodes
    
    def get_checkpoint(self, node_id: str) -> Optional[CheckpointData]:
        """獲取節點檢查點
        
        Args:
            node_id: 節點 ID
            
        Returns:
            檢查點數據，如果不存在返回 None
        """
        node_state = self.node_states.get(node_id)
        return node_state.checkpoint if node_state else None
    
    def clear_node_states(self, session: Session):
        """清理所有節點狀態
        
        在開始新的運行前調用，確保沒有舊數據幹擾。
        
        Args:
            session: 數據庫會話
        """
        stmt = select(NodeExecutionState).where(
            NodeExecutionState.run_id == self.run_id
        )
        old_states = session.exec(stmt).all()
        
        for state in old_states:
            session.delete(state)
        
        if old_states:
            session.commit()
            logger.info(f"[ExecutionState] 清理了 {len(old_states)} 箇舊節點狀態: run_id={self.run_id}")
        
        # 清空內存狀態
        self.node_states.clear()
        self.completed_nodes.clear()
        self.context.clear()
