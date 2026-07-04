/**
 * 工作流進度管理 Composable
 * 
 * 統一管理工作流執行進度，供執行界面和狀態欄共用
 * 注意：SSE 連接管理已移到 WorkflowStatusStore 中，確保切換界面時連接不斷
 */

import { useWorkflowStore } from '@/stores/useWorkflowStore'
import type { WorkflowStreamCallbacks } from '@/api/workflows'

export function useWorkflowProgress() {
  const workflowStore = useWorkflowStore()

  /**
   * 啓動工作流執行（全局 SSE 連接管理）
   */
  async function startWorkflow(
    workflowId: number,
    workflowName: string,
    callbacks: WorkflowStreamCallbacks,
    resume: boolean = false,
    runId?: number
  ) {
    return await workflowStore.startWorkflowExecution(
      workflowId,
      workflowName,
      callbacks,
      resume,
      runId
    )
  }

  /**
   * 暫停工作流執行
   */
  function pauseWorkflow(runId: number) {
    workflowStore.pauseWorkflowExecution(runId)
  }

  /**
   * 獲取 SSE 連接
   */
  function getConnection(runId: number) {
    return workflowStore.getSSEConnection(runId)
  }

  return {
    startWorkflow,
    pauseWorkflow,
    getConnection
  }
}
