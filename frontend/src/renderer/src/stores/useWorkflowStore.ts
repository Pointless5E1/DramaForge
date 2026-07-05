import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { 
    getRun, 
    runCodeWorkflowStream, 
    getNodeTypes,
    type WorkflowStreamCallbacks,
    type WorkflowNodeType 
} from '@/api/workflows'

// 簡單的運行資訊接口，用於狀態欄顯示
export interface RunInfo {
    id: number
    workflow_id: number
    workflow_name?: string
    status: string
    created_at?: string
    error?: string // 從 error_json 提取的錯誤資訊
    current_node?: string // 當前執行的節點
    progress?: number // 執行進度（0-100）
}

// SSE 連接管理
interface SSEConnection {
    runId: number
    workflowId: number
    workflowName: string
    eventSource: EventSource
    callbacks: WorkflowStreamCallbacks
}

/**
 * 統一的工作流 Store
 * 管理：
 * 1. 節點類型、卡片類型等元資料
 * 2. 工作流運行狀態和 SSE 連接
 */
export const useWorkflowStore = defineStore('workflow', () => {
    // ==================== 元資料管理 ====================
    const nodeTypes = ref<WorkflowNodeType[]>([])
    const cardTypes = ref<any[]>([])
    const isLoadingNodeTypes = ref(false)

    // Getters
    const categories = computed(() => {
        const cats = new Set(nodeTypes.value.map(n => n.category))
        return Array.from(cats)
    })

    const getNodesByCategory = (category: string) => {
        return nodeTypes.value.filter(n => n.category === category)
    }

    const getNodeType = (type: string) => {
        return nodeTypes.value.find(n => n.type === type)
    }

    // Actions
    async function fetchNodeTypes() {
        if (isLoadingNodeTypes.value) return

        try {
            isLoadingNodeTypes.value = true
            const res = await getNodeTypes()
            nodeTypes.value = res.node_types
        } catch (error) {
            console.error('Failed to fetch node types:', error)
        } finally {
            isLoadingNodeTypes.value = false
        }
    }

    async function fetchCardTypes() {
        if (cardTypes.value.length > 0) return // cache
        try {
            const { getCardTypes } = await import('../api/cards')
            cardTypes.value = await getCardTypes()
        } catch (error) {
            console.error('Failed to fetch card types:', error)
        }
    }

    // ==================== 運行狀態管理 ====================
    const runs = ref<Map<number, RunInfo>>(new Map())
    const pollingTimer = ref<any>(null)
    const sseConnections = ref<Map<number, SSEConnection>>(new Map()) // 管理所有 SSE 連接

    // Getters
    const activeRuns = computed(() => {
        return Array.from(runs.value.values()).filter(r =>
            ['pending', 'running', 'paused'].includes(r.status)
        ).sort((a, b) => b.id - a.id)
    })

    const completedRuns = computed(() => {
        return Array.from(runs.value.values()).filter(r =>
            ['succeeded', 'failed', 'cancelled', 'timeout'].includes(r.status)
        ).sort((a, b) => b.id - a.id)
    })

    const totalRunCount = computed(() => runs.value.size)
    const activeRunCount = computed(() => activeRuns.value.length)

    // Actions
    function addRun(id: number, workflowName?: string) {
        if (runs.value.has(id)) return

        // 初始化佔位
        runs.value.set(id, {
            id,
            workflow_id: 0,
            status: 'running',
            workflow_name: workflowName || '載入中...',
            progress: 0
        })

        // 立即獲取一次詳情
        fetchRunDetails(id)

        // 確保輪詢開啓
        startPolling()
    }

    function updateRunProgress(id: number, progress: number, currentNode?: string) {
        const run = runs.value.get(id)
        if (run) {
            runs.value.set(id, {
                ...run,
                progress,
                current_node: currentNode
            })
        }
    }

    function updateRunStatus(id: number, status: string, error?: string) {
        const run = runs.value.get(id)
        if (run) {
            runs.value.set(id, {
                ...run,
                status,
                error
            })
        }
    }

    async function fetchRunDetails(id: number) {
        try {
            const run = await getRun(id)
            if (run) {
                const existingRun = runs.value.get(id)
                
                // 從 error_json 提取錯誤資訊
                let errorMessage: string | undefined
                if (run.error_json) {
                    errorMessage = typeof run.error_json === 'object' 
                        ? JSON.stringify(run.error_json) 
                        : String(run.error_json)
                }
                
                runs.value.set(id, {
                    id: run.id,
                    workflow_id: run.workflow_id,
                    workflow_name: run.workflow?.name || '未命名工作流',
                    status: run.status,
                    created_at: run.created_at || undefined,
                    error: errorMessage,
                    current_node: existingRun?.current_node, // 保留當前節點資訊
                    progress: existingRun?.progress // 保留進度資訊
                })
            }
        } catch (e) {
            console.error(`Failed to fetch run ${id}`, e)
        }
    }

    function startPolling() {
        if (pollingTimer.value) return

        // 立即執行一次檢查
        checkActiveRuns()

        pollingTimer.value = setInterval(() => {
            checkActiveRuns()
        }, 2000) // 2秒輪詢一次
    }

    function stopPolling() {
        if (pollingTimer.value) {
            clearInterval(pollingTimer.value)
            pollingTimer.value = null
        }
    }

    /**
     * 監聽後端觸發的工作流（通過響應頭通知）
     */
    function setupWorkflowListener() {
        const handleWorkflowStarted = (event: CustomEvent) => {
            const runIds = event.detail as number[]
            
            // 添加所有新啓動的運行到狀態
            runIds.forEach(runId => {
                if (!runs.value.has(runId)) {
                    addRun(runId, '觸發器工作流')
                }
            })
        }
        
        window.addEventListener('workflow-started', handleWorkflowStarted as EventListener)
        
        // 返回清理函數
        return () => {
            window.removeEventListener('workflow-started', handleWorkflowStarted as EventListener)
        }
    }

    async function checkActiveRuns() {
        if (activeRuns.value.length === 0) {
            stopPolling()
            return
        }

        // 更新所有活動運行的狀態
        for (const run of activeRuns.value) {
            await fetchRunDetails(run.id)
        }
    }

    // 清理已完成的運行（可選，避免內存佔用過多）
    function clearCompleted() {
        const completedIds = completedRuns.value.map(r => r.id)
        completedIds.forEach(id => {
            runs.value.delete(id)
            // 同時清理對應的 SSE 連接
            const conn = sseConnections.value.get(id)
            if (conn) {
                conn.eventSource.close()
                sseConnections.value.delete(id)
            }
        })
    }

    /**
     * 啓動工作流執行（全局 SSE 連接管理）
     * @param workflowId 工作流 ID
     * @param workflowName 工作流名稱
     * @param callbacks 回調函數（用於更新 UI）
     * @param resume 是否恢復執行
     * @param runId 恢復執行時的 run ID
     */
    async function startWorkflowExecution(
        workflowId: number,
        workflowName: string,
        callbacks: WorkflowStreamCallbacks,
        resume: boolean = false,
        runId?: number
    ) {
        let currentRunId: number | null = runId || null
        let totalNodes = 0
        let completedNodes = 0

        // 如果是恢復執行，確保運行記錄存在且狀態正確
        if (resume && runId) {
            const existingRun = runs.value.get(runId)
            if (existingRun) {
                // 更新狀態爲運行中
                updateRunStatus(runId, 'running')
                console.log('[WorkflowStore] 恢復執行，更新狀態爲 running:', runId)
            } else {
                // 如果不存在，添加到狀態欄
                addRun(runId, workflowName)
                console.log('[WorkflowStore] 恢復執行，添加運行記錄:', runId)
            }
        }

        // 包裝回調，自動更新狀態欄
        const wrappedCallbacks: WorkflowStreamCallbacks = {
            onRunStarted: (actualRunId: number) => {
                currentRunId = actualRunId
                // 添加到狀態欄（僅新執行）
                if (!resume) {
                    addRun(actualRunId, workflowName)
                }
                // 調用原始回調
                if (callbacks.onRunStarted) {
                    callbacks.onRunStarted(actualRunId)
                }
            },

            onStart: (event) => {
                totalNodes++
                // 更新狀態欄：當前節點
                if (currentRunId) {
                    const progress = totalNodes > 0 ? (completedNodes / totalNodes) * 100 : 0
                    updateRunProgress(currentRunId, progress, event.statement?.variable)
                }
                // 調用原始回調
                if (callbacks.onStart) {
                    callbacks.onStart(event)
                }
            },

            onProgress: (event) => {
                // 更新狀態欄：進度
                if (currentRunId) {
                    const nodeProgress = event.percent || 0
                    const overallProgress = totalNodes > 0 
                        ? ((completedNodes + nodeProgress / 100) / totalNodes) * 100 
                        : nodeProgress
                    updateRunProgress(currentRunId, overallProgress, event.statement?.variable)
                }
                // 調用原始回調
                if (callbacks.onProgress) {
                    callbacks.onProgress(event)
                }
            },

            onComplete: (event) => {
                completedNodes++
                // 更新狀態欄：完成一個節點
                if (currentRunId) {
                    const progress = totalNodes > 0 ? (completedNodes / totalNodes) * 100 : 100
                    updateRunProgress(currentRunId, progress, event.statement?.variable)
                }
                // 調用原始回調
                if (callbacks.onComplete) {
                    callbacks.onComplete(event)
                }
            },

            onError: (event) => {
                // 更新狀態
                if (currentRunId) {
                    updateRunStatus(currentRunId, 'failed', event.error)
                }
                // 調用原始回調
                if (callbacks.onError) {
                    callbacks.onError(event)
                }
            },

            onEnd: () => {
                // 工作流結束，最終更新狀態
                if (currentRunId) {
                    updateRunProgress(currentRunId, 100, undefined)
                    // 更新狀態爲 succeeded（如果不是 failed）
                    const run = runs.value.get(currentRunId)
                    if (run && run.status !== 'failed') {
                        updateRunStatus(currentRunId, 'succeeded')
                    }
                    // 清理 SSE 連接
                    const conn = sseConnections.value.get(currentRunId)
                    if (conn) {
                        conn.eventSource.close()
                        sseConnections.value.delete(currentRunId)
                    }
                }
                // 調用原始回調
                if (callbacks.onEnd) {
                    callbacks.onEnd()
                }
            }
        }

        try {
            // 如果是恢復執行，先清理舊的 SSE 連接
            if (resume && runId) {
                const oldConn = sseConnections.value.get(runId)
                if (oldConn) {
                    console.log('[WorkflowStore] 清理舊的 SSE 連接:', runId)
                    oldConn.eventSource.close()
                    sseConnections.value.delete(runId)
                }
            }
            
            // 啓動 SSE 連接
            const { runId: actualRunId, eventSource } = await runCodeWorkflowStream(
                workflowId,
                wrappedCallbacks,
                resume,
                runId
            )

            // 儲存連接資訊
            if (currentRunId) {
                console.log('[WorkflowStore] 儲存 SSE 連接:', currentRunId)
                sseConnections.value.set(currentRunId, {
                    runId: currentRunId,
                    workflowId,
                    workflowName,
                    eventSource,
                    callbacks: wrappedCallbacks
                })
            }

            return { runId: actualRunId, eventSource }
        } catch (error) {
            console.error('[WorkflowStore] 啓動工作流失敗:', error)
            throw error
        }
    }

    /**
     * 暫停工作流執行
     */
    function pauseWorkflowExecution(runId: number) {
        console.log('[WorkflowStore] 暫停工作流執行:', runId)
        const conn = sseConnections.value.get(runId)
        if (conn) {
            console.log('[WorkflowStore] 關閉 SSE 連接:', runId)
            conn.eventSource.close()
            sseConnections.value.delete(runId)
            updateRunStatus(runId, 'paused')
        } else {
            console.warn('[WorkflowStore] 未找到 SSE 連接:', runId)
        }
    }

    /**
     * 獲取 SSE 連接
     */
    function getSSEConnection(runId: number) {
        return sseConnections.value.get(runId)
    }

    return {
        // 元資料
        nodeTypes,
        cardTypes,
        isLoadingNodeTypes,
        categories,
        getNodesByCategory,
        getNodeType,
        fetchNodeTypes,
        fetchCardTypes,
        
        // 運行狀態
        runs,
        activeRuns,
        completedRuns,
        activeRunCount,
        totalRunCount,
        addRun,
        updateRunProgress,
        updateRunStatus,
        clearCompleted,
        startWorkflowExecution,
        pauseWorkflowExecution,
        getSSEConnection,
        
        // 工作流監聽器
        setupWorkflowListener
    }
})
