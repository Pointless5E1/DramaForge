/**
 * 工作流執行狀態機
 * 
 * 管理工作流執行的狀態轉換，防止非法操作
 */

import { reactive, readonly, computed } from 'vue'

export enum WorkflowState {
  IDLE = 'idle',           // 空閒狀態
  RUNNING = 'running',     // 運行中
  PAUSED = 'paused',       // 已暫停
  COMPLETED = 'completed', // 已完成
  FAILED = 'failed'        // 失敗
}

export interface WorkflowExecution {
  state: WorkflowState
  runId: number | null
  workflowId: number | null
  error: string | null
}

/**
 * 工作流執行狀態機
 */
export function useWorkflowExecution() {
  // 內部狀態
  const execution = reactive<WorkflowExecution>({
    state: WorkflowState.IDLE,
    runId: null,
    workflowId: null,
    error: null
  })

  // 狀態轉換規則
  const validTransitions: Record<WorkflowState, WorkflowState[]> = {
    [WorkflowState.IDLE]: [WorkflowState.RUNNING],
    [WorkflowState.RUNNING]: [WorkflowState.PAUSED, WorkflowState.COMPLETED, WorkflowState.FAILED],
    [WorkflowState.PAUSED]: [WorkflowState.RUNNING, WorkflowState.FAILED],
    [WorkflowState.COMPLETED]: [WorkflowState.IDLE, WorkflowState.RUNNING],  // 允許從完成狀態直接開始新執行
    [WorkflowState.FAILED]: [WorkflowState.IDLE, WorkflowState.RUNNING]      // 允許從失敗狀態直接開始新執行
  }

  // 計算屬性
  const isRunning = computed(() => execution.state === WorkflowState.RUNNING)
  const isPaused = computed(() => execution.state === WorkflowState.PAUSED)
  const isIdle = computed(() => execution.state === WorkflowState.IDLE)
  const isCompleted = computed(() => execution.state === WorkflowState.COMPLETED)
  const isFailed = computed(() => execution.state === WorkflowState.FAILED)
  const canPause = computed(() => execution.state === WorkflowState.RUNNING)
  const canResume = computed(() => execution.state === WorkflowState.PAUSED)
  const canStart = computed(() => 
    execution.state === WorkflowState.IDLE || 
    execution.state === WorkflowState.COMPLETED || 
    execution.state === WorkflowState.FAILED
  )

  /**
   * 狀態轉換
   * @param newState 新狀態
   * @throws Error 如果狀態轉換非法
   */
  function transitionTo(newState: WorkflowState) {
    const currentState = execution.state
    const allowedStates = validTransitions[currentState]

    if (!allowedStates.includes(newState)) {
      throw new Error(
        `非法狀態轉換: ${currentState} -> ${newState}. ` +
        `允許的轉換: ${allowedStates.join(', ')}`
      )
    }

    console.log(`[WorkflowExecution] 狀態轉換: ${currentState} -> ${newState}`)
    execution.state = newState
  }

  /**
   * 開始執行
   * @param workflowId 工作流ID
   * @param runId 運行ID
   */
  function start(workflowId: number, runId: number) {
    // 如果當前是完成或失敗狀態，先重置再開始（自動清空之前的結果）
    if (execution.state === WorkflowState.COMPLETED || execution.state === WorkflowState.FAILED) {
      console.log(`[WorkflowExecution] 從 ${execution.state} 狀態重新開始，自動清空結果`)
    }
    
    transitionTo(WorkflowState.RUNNING)
    execution.workflowId = workflowId
    execution.runId = runId
    execution.error = null
  }

  /**
   * 更新運行ID（不改變狀態）
   * @param runId 新的運行ID
   */
  function updateRunId(runId: number) {
    console.log(`[WorkflowExecution] 更新 runId: ${execution.runId} -> ${runId}`)
    execution.runId = runId
  }

  /**
   * 暫停執行
   */
  function pause() {
    transitionTo(WorkflowState.PAUSED)
  }

  /**
   * 恢復執行
   */
  function resume() {
    transitionTo(WorkflowState.RUNNING)
  }

  /**
   * 完成執行
   */
  function complete() {
    transitionTo(WorkflowState.COMPLETED)
  }

  /**
   * 執行失敗
   * @param error 錯誤信息
   */
  function fail(error: string) {
    transitionTo(WorkflowState.FAILED)
    execution.error = error
  }

  /**
   * 重置狀態
   */
  function reset() {
    transitionTo(WorkflowState.IDLE)
    execution.runId = null
    execution.workflowId = null
    execution.error = null
  }

  return {
    // 只讀狀態
    execution: readonly(execution),
    
    // 計算屬性
    isRunning,
    isPaused,
    isIdle,
    isCompleted,
    isFailed,
    canPause,
    canResume,
    canStart,
    
    // 狀態轉換方法
    start,
    updateRunId,
    pause,
    resume,
    complete,
    fail,
    reset
  }
}
