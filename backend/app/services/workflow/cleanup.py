from datetime import datetime, timedelta
from sqlmodel import Session, select, delete
from loguru import logger
from app.db.models import WorkflowRun, Workflow
from app.core.config import settings

def cleanup_expired_runs(session: Session):
    """清理過期的工作流運行記錄
    
    策略（精簡版）：
    1. 非持久化 (keep_run_history=False): 下次啓動時直接清理所有已完成的運行
    2. 持久化 (keep_run_history=True): 保留 N 天
    3. 狀態未完成（running/queued/paused）的運行不刪除
    """
    persistent_retention_days = settings.workflow.retention_persistent_days
        
    now = datetime.utcnow()
    deleted_count = 0
    
    try:
        # 策略 A: 清理所有"非持久化"且"已完成"的運行（無需判斷時間）
        stmt_transient = (
            select(WorkflowRun.id)
            .join(Workflow)
            .where(
                WorkflowRun.status.in_(["succeeded", "failed", "cancelled", "timeout"]),
                (Workflow.keep_run_history == False) | (Workflow.keep_run_history == None)
            )
        )
        transient_ids = session.exec(stmt_transient).all()
        
        if transient_ids:
            stmt_del = delete(WorkflowRun).where(WorkflowRun.id.in_(transient_ids))
            result = session.exec(stmt_del)
            deleted_count += result.rowcount if hasattr(result, 'rowcount') else len(transient_ids)
            logger.info(f"[Cleanup] 清理非持久化運行記錄: {len(transient_ids)} 條")

        # 策略 B: 清理"持久化"且"已完成"且"超過保留期"的運行
        persistent_cutoff = now - timedelta(days=persistent_retention_days)
        stmt_persistent = (
            select(WorkflowRun.id)
            .join(Workflow)
            .where(
                WorkflowRun.status.in_(["succeeded", "failed", "cancelled", "timeout"]),
                WorkflowRun.finished_at < persistent_cutoff,
                Workflow.keep_run_history == True
            )
        )
        persistent_ids = session.exec(stmt_persistent).all()
        
        if persistent_ids:
            stmt_del = delete(WorkflowRun).where(WorkflowRun.id.in_(persistent_ids))
            result = session.exec(stmt_del)
            count = result.rowcount if hasattr(result, 'rowcount') else len(persistent_ids)
            deleted_count += count
            logger.info(f"[Cleanup] 清理過期持久化記錄: {count} 條")
            
        session.commit()
        if deleted_count > 0:
            logger.info(f"[Cleanup] 工作流清理完成，共刪除 {deleted_count} 條記錄")
            
    except Exception as e:
        logger.error(f"[Cleanup] 清理工作流失敗: {e}")
        session.rollback()
