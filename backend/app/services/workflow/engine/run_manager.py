"""運行管理器 - 統一管理代碼式工作流運行"""

import asyncio
from typing import Optional, Dict, Any
from sqlmodel import Session, select
from loguru import logger

from app.db.models import Workflow, WorkflowRun
from .state_manager import StateManager
from .runtime import workflow_runtime


class RunManager:
    """工作流運行管理器
    
    職責：
    - 創建和啓動運行
    - 管理運行生命週期
    - 提供暫停/恢復/取消接口
    - 協調各個組件
    
    只支持代碼式工作流系統。
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.state_manager = StateManager(session)
    
    def create_run(
        self,
        workflow_id: int,
        trigger_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None
    ) -> WorkflowRun:
        """創建工作流運行
        
        Args:
            workflow_id: 工作流ID
            trigger_data: 觸發數據（如卡片信息），會注入到 scope_json
            params: 運行參數，會注入到 params_json
            idempotency_key: 冪等鍵，防止重複執行
            
        Returns:
            WorkflowRun: 運行記錄
        """
        # 檢查冪等性（只檢查正在運行的任務，避免阻止失敗任務重試）
        if idempotency_key:
            stmt = select(WorkflowRun).where(
                WorkflowRun.idempotency_key == idempotency_key,
                WorkflowRun.status.in_(["queued", "running"])
            )
            existing = self.session.exec(stmt).first()
            if existing:
                logger.warning(
                    f"[RunManager] 冪等鍵衝突，任務正在運行: "
                    f"run_id={existing.id}, status={existing.status}"
                )
                return existing
        
        # 獲取工作流
        workflow = self.session.get(Workflow, workflow_id)
        if not workflow:
            raise ValueError(f"工作流不存在: {workflow_id}")
        
        if not workflow.is_active:
            raise ValueError(f"工作流未激活: {workflow_id}")
        
        # 創建運行記錄
        from datetime import datetime
        run = WorkflowRun(
            workflow_id=workflow_id,
            definition_version=workflow.dsl_version,  # 使用 dsl_version 代替 version
            status="queued",
            scope_json=trigger_data,
            params_json=params,
            idempotency_key=idempotency_key,
            created_at=datetime.now()  # 使用本地時間而不是 UTC
        )
        
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        
        # 清理該 run_id 的舊節點狀態（確保乾淨的開始）
        self.state_manager.clear_node_states(run.id)
        
        logger.info(
            f"[RunManager] 創建運行: run_id={run.id}, "
            f"workflow_id={workflow_id}"
        )
        
        return run
    
    async def start_run(
        self,
        run_id: int,
        priority: int = 0
    ) -> None:
        """啓動工作流運行
        
        Args:
            run_id: 運行ID
            priority: 優先級
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError(f"運行不存在: {run_id}")
        
        workflow = self.session.get(Workflow, run.workflow_id)
        if not workflow:
            raise ValueError(f"工作流不存在: {run.workflow_id}")
        
        if workflow_runtime.is_active(run_id):
            logger.info(f"[RunManager] 運行已在調度中: run_id={run_id}")
            return

        task = asyncio.create_task(self._execute_run_in_new_session(run_id))
        workflow_runtime.register_task(run_id, task)

    async def _execute_run_in_new_session(self, run_id: int) -> None:
        """在獨立數據庫會話中執行後臺運行。"""
        from app.db.session import engine as db_engine

        session = Session(db_engine)
        try:
            run = session.get(WorkflowRun, run_id)
            if not run:
                logger.error(f"[RunManager] 運行不存在: run_id={run_id}")
                return

            workflow = session.get(Workflow, run.workflow_id)
            if not workflow:
                logger.error(f"[RunManager] 工作流不存在: workflow_id={run.workflow_id}")
                return

            manager = RunManager(session)
            await manager._execute_run(run, workflow)
        finally:
            session.close()
    
    async def _execute_run(
        self,
        run: WorkflowRun,
        workflow: Workflow
    ) -> None:
        """執行運行（內部方法）"""
        from ..parser.marker_parser import WorkflowParser
        from .async_executor import AsyncExecutor
        
        run_id = run.id

        try:
            slot_status = await workflow_runtime.acquire_slot(run_id)
            if slot_status == "cancelled":
                self.state_manager.update_run_status(run_id, "cancelled")
                return
            if slot_status == "paused":
                self.state_manager.update_run_status(run_id, "paused")
                return

            # 更新狀態爲運行中
            self.state_manager.update_run_status(run_id, "running")

            # 解析工作流定義
            code = workflow.definition_code or ""

            if not code:
                raise ValueError("工作流缺少代碼內容")

            logger.info(f"[RunManager] 解析代碼式工作流: run_id={run_id}")

            # 解析代碼
            parser = WorkflowParser()
            plan = parser.parse(code)

            logger.info(f"[RunManager] 執行代碼式工作流: run_id={run_id}, 語句數={len(plan.statements)}")

            # 準備初始上下文（注入觸發器數據）
            initial_context = {}

            # 將 scope_json 和 params_json 直接展開到頂層
            if run.scope_json:
                initial_context.update(run.scope_json)
            if run.params_json:
                initial_context.update(run.params_json)

            # 執行工作流（流式）
            executor = AsyncExecutor(
                session=self.state_manager.session,
                state_manager=self.state_manager,
                run_id=run_id
            )
            
            # 保存執行器引用（用於暫停/恢復）
            workflow_runtime.register_executor(run_id, executor)
            
            try:
                # 消費所有事件（觸發器場景不需要處理進度）
                async for event in executor.execute_stream(plan, initial_context):
                    pass  # 可以在這裏添加日誌記錄
                
                if executor.is_paused or workflow_runtime.is_pause_requested(run_id):
                    self.state_manager.update_run_status(run_id, "paused")
                    logger.info(f"[RunManager] 運行已暫停: run_id={run_id}")
                    return

                # 獲取最終結果
                result_context = executor.context
            finally:
                # 清理執行器引用
                workflow_runtime.unregister_executor(run_id, executor)

            # 更新狀態爲成功
            self.state_manager.update_run_status(
                run_id,
                "succeeded",
                summary_json={
                    "variables": list(result_context.keys()),
                    "outputs": self.state_manager._make_json_serializable(result_context)
                }
            )

            logger.info(f"[RunManager] 運行成功: run_id={run_id}")

        except asyncio.CancelledError:
            logger.info(f"[RunManager] 運行被取消: run_id={run_id}")
            self.state_manager.update_run_status(run_id, "cancelled")
            raise
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"[RunManager] 運行失敗: run_id={run_id}")

            # 判斷是否超時
            if isinstance(e, asyncio.TimeoutError):
                self.state_manager.update_run_status(run_id, "timeout")
            else:
                self.state_manager.update_run_status(run_id, "failed")
                self.state_manager.save_error(run_id, error_msg)
        finally:
            workflow_runtime.finish_run(
                run_id,
                keep_pause=workflow_runtime.is_pause_requested(run_id)
            )
    
    async def cancel_run(self, run_id: int) -> bool:
        """取消運行
        
        Args:
            run_id: 運行ID
            
        Returns:
            是否成功取消
        """
        if workflow_runtime.request_cancel(run_id):
            self.state_manager.update_run_status(run_id, "cancelled")
            logger.info(f"[RunManager] 運行已取消: run_id={run_id}")
            return True

        run = self.session.get(WorkflowRun, run_id)
        if run and run.status in {"queued", "running", "paused"}:
            self.state_manager.update_run_status(run_id, "cancelled")
            logger.info(f"[RunManager] 未發現進程內任務，已將運行標記爲取消: run_id={run_id}")
            return True
        
        return False
    
    async def pause_run(self, run_id: int) -> bool:
        """暫停運行
        
        Args:
            run_id: 運行ID
            
        Returns:
            是否成功暫停
        """
        if workflow_runtime.request_pause(run_id):
            self.state_manager.update_run_status(run_id, "paused")
            logger.info(f"[RunManager] 運行已暫停: run_id={run_id}")
            return True
        
        logger.warning(f"[RunManager] 無法暫停運行（執行器不存在）: run_id={run_id}")
        return False
    
    async def resume_run(self, run_id: int) -> bool:
        """恢復運行
        
        Args:
            run_id: 運行ID
            
        Returns:
            是否成功恢復
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            logger.warning(f"[RunManager] 運行不存在: run_id={run_id}")
            return False
        
        if run.status != "paused":
            logger.warning(f"[RunManager] 運行狀態不是暫停: run_id={run_id}, status={run.status}")
            return False
        
        # 檢查執行器是否存在
        if workflow_runtime.request_resume(run_id):
            # 執行器存在，直接恢復
            self.state_manager.update_run_status(run_id, "running")
            logger.info(f"[RunManager] 運行已恢復: run_id={run_id}")
            return True
        else:
            # 執行器不存在（服務器重啓），重新啓動運行
            logger.info(f"[RunManager] 執行器不存在，重新啓動運行: run_id={run_id}")
            workflow = self.session.get(Workflow, run.workflow_id)
            if not workflow:
                logger.error(f"[RunManager] 工作流不存在: workflow_id={run.workflow_id}")
                return False
            
            # 重新啓動（會自動恢復狀態）
            await self.start_run(run_id)
            return True
    
    def get_run_status(self, run_id: int) -> Optional[Dict[str, Any]]:
        """獲取運行狀態
        
        Args:
            run_id: 運行ID
            
        Returns:
            運行狀態信息
        """
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            return None
        
        # 獲取節點狀態
        node_states = self.state_manager.get_all_node_states(run_id)
        
        return {
            "run_id": run.id,
            "workflow_id": run.workflow_id,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error": run.error_json,
            "nodes": [
                {
                    "node_id": ns.node_id,
                    "node_type": ns.node_type,
                    "status": ns.status,
                    "progress": int(ns.progress) if ns.progress is not None else 0,
                    "error": ns.error_message,
                    "outputs_json": ns.outputs_json
                }
                for ns in node_states
            ]
        }
