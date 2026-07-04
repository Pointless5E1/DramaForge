"""工作流調度器 - 管理工作流運行隊列"""

import asyncio
from typing import Dict, Optional
from loguru import logger

from app.db.models import WorkflowRun


class WorkflowScheduler:
    """工作流調度器
    
    職責：
    - 管理運行隊列
    - 控制併發運行數
    - 優先級調度
    """
    
    def __init__(self, max_concurrent_runs: int = 5):
        self.max_concurrent_runs = max_concurrent_runs
        self.running_runs: Dict[int, asyncio.Task] = {}  # run_id -> task
        self.pending_queue: asyncio.Queue = asyncio.Queue()  # (priority, run_id)
    
    async def schedule_run(
        self,
        run_id: int,
        executor_coro,
        priority: int = 0
    ) -> None:
        """調度工作流運行
        
        Args:
            run_id: 運行ID
            executor_coro: 執行器協程
            priority: 優先級（數字越小優先級越高）
        """
        if len(self.running_runs) < self.max_concurrent_runs:
            # 直接啓動
            await self._start_run(run_id, executor_coro)
        else:
            # 加入隊列等待
            logger.info(
                f"[Scheduler] 運行加入等待隊列: run_id={run_id}, "
                f"priority={priority}"
            )
            await self.pending_queue.put((priority, run_id, executor_coro))
    
    async def _start_run(self, run_id: int, executor_coro) -> None:
        """啓動運行"""
        logger.info(f"[Scheduler] 啓動運行: run_id={run_id}")
        
        # 創建任務
        task = asyncio.create_task(self._run_with_cleanup(run_id, executor_coro))
        self.running_runs[run_id] = task
    
    async def _run_with_cleanup(self, run_id: int, executor_coro) -> None:
        """執行運行並清理"""
        try:
            await executor_coro
        finally:
            # 清理
            if run_id in self.running_runs:
                del self.running_runs[run_id]
            
            logger.info(
                f"[Scheduler] 運行完成: run_id={run_id}, "
                f"當前運行數={len(self.running_runs)}"
            )
            
            # 啓動隊列中的下一個
            await self._start_next_from_queue()
    
    async def _start_next_from_queue(self) -> None:
        """從隊列中啓動下一個運行"""
        if self.pending_queue.empty():
            return
        
        if len(self.running_runs) >= self.max_concurrent_runs:
            return
        
        # 獲取優先級最高的運行
        priority, run_id, executor_coro = await self.pending_queue.get()
        logger.info(
            f"[Scheduler] 從隊列啓動運行: run_id={run_id}, priority={priority}"
        )
        await self._start_run(run_id, executor_coro)
    
    def cancel_run(self, run_id: int) -> bool:
        """取消運行
        
        Args:
            run_id: 運行ID
            
        Returns:
            是否成功取消
        """
        if run_id in self.running_runs:
            task = self.running_runs[run_id]
            task.cancel()
            logger.info(f"[Scheduler] 取消運行: run_id={run_id}")
            return True
        return False
    
    def get_running_count(self) -> int:
        """獲取當前運行數"""
        return len(self.running_runs)
    
    def get_pending_count(self) -> int:
        """獲取等待隊列長度"""
        return self.pending_queue.qsize()
    
    def is_running(self, run_id: int) -> bool:
        """檢查運行是否正在執行"""
        return run_id in self.running_runs
