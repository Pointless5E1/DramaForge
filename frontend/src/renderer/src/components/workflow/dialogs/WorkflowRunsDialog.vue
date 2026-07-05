<template>
  <el-dialog
    v-model="visible"
    title="工作流運行記錄"
    width="90%"
    :close-on-click-modal="false"
  >
    <div class="runs-dialog-content">
      <!-- 過濾器 -->
      <div class="filters">
        <el-select v-model="statusFilter" placeholder="狀態篩選" clearable @change="loadRuns" style="width: 150px">
          <el-option label="全部" value="" />
          <el-option label="運行中" value="running" />
          <el-option label="已暫停" value="paused" />
          <el-option label="已完成" value="succeeded" />
          <el-option label="失敗" value="failed" />
        </el-select>
        <el-button @click="loadRuns" :icon="Refresh">刷新</el-button>
      </div>

      <!-- 運行列表 -->
      <el-table :data="runs" v-loading="loading" stripe style="margin-top: 10px">
        <el-table-column prop="id" label="ID" width="60" />
        
        <el-table-column label="工作流" width="180">
          <template #default="{ row }">
            {{ row.workflow?.name || `工作流 #${row.workflow_id}` }}
          </template>
        </el-table-column>

        <el-table-column label="狀態" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="進度" width="150">
          <template #default="{ row }">
            <el-progress 
              v-if="row.status === 'running' || row.status === 'paused'"
              :percentage="getProgress(row.id)" 
              :status="row.status === 'paused' ? 'warning' : undefined"
              :stroke-width="8"
            />
            <el-progress 
              v-else-if="row.status === 'succeeded'"
              :percentage="100" 
              status="success"
              :stroke-width="8"
            />
            <el-progress 
              v-else-if="row.status === 'failed'"
              :percentage="100" 
              status="exception"
              :stroke-width="8"
            />
          </template>
        </el-table-column>

        <el-table-column label="創建時間" width="160">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" fixed="right" width="320">
          <template #default="{ row }">
            <div style="display: flex; gap: 4px; flex-wrap: nowrap;">
              <el-button
                v-if="row.status === 'running'"
                @click="pauseRun(row.id)"
                :icon="VideoPause"
                size="small"
              >
                暫停
              </el-button>

              <el-button
                v-if="row.status === 'paused' || row.status === 'failed'"
                type="primary"
                @click="resumeRunFromDialog(row)"
                :icon="VideoPlay"
                size="small"
              >
                恢復
              </el-button>

              <el-button
                @click="viewNodeStatus(row.id)"
                :icon="List"
                size="small"
              >
                狀態
              </el-button>
              
              <el-button
                type="danger"
                @click="deleteRun(row.id)"
                :icon="Delete"
                plain
                size="small"
              >
                刪除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 節點狀態對話框 -->
    <el-dialog
      v-model="nodeStatusVisible"
      title="節點執行狀態"
      width="700px"
      append-to-body
    >
      <el-table :data="nodeStatuses" v-loading="loadingNodeStatus" size="small">
        <el-table-column prop="node_id" label="節點 ID" width="120" />
        <el-table-column prop="node_type" label="節點類型" width="150" />
        <el-table-column label="狀態" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="進度" width="120">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :stroke-width="6" />
          </template>
        </el-table-column>
        <el-table-column prop="error" label="錯誤" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, VideoPause, VideoPlay, Close, List, Delete } from '@element-plus/icons-vue'
import { deleteRun as deleteRunApi } from '@renderer/api/workflows'
import request from '@renderer/api/request'

interface WorkflowRun {
  id: number
  workflow_id: number
  status: string
  created_at: string
  workflow?: {
    id: number
    name: string
  }
}

interface NodeStatus {
  node_id: string
  node_type: string
  status: string
  progress: number
  error?: string
}

interface RunStatusResponse {
  nodes: NodeStatus[]
}

const props = defineProps<{
  modelValue: boolean
  workflowId?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'resume-run', run: WorkflowRun): void
}>()

const visible = ref(props.modelValue)
const runs = ref<WorkflowRun[]>([])
const loading = ref(false)
const statusFilter = ref('')
const progressCache = ref<Record<number, number>>({})

const nodeStatusVisible = ref(false)
const nodeStatuses = ref<NodeStatus[]>([])
const loadingNodeStatus = ref(false)

let refreshTimer: number | null = null

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    loadRuns()
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
  if (!val) {
    stopAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})

function startAutoRefresh() {
  stopAutoRefresh()
  refreshTimer = window.setInterval(() => {
    if (runs.value.some(r => r.status === 'running' || r.status === 'paused')) {
      loadRuns(true)
    }
  }, 3000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

async function loadRuns(silent = false) {
  if (!silent) {
    loading.value = true
  }

  try {
    const params: any = { limit: 50, offset: 0 }
    if (statusFilter.value) {
      params.status = statusFilter.value
    }

    // 如果指定了 workflowId，只載入該工作流的運行記錄
    const url = props.workflowId 
      ? `/workflows/${props.workflowId}/runs`
      : '/runs'
    
    const response = await request.get<WorkflowRun[]>(url, params, '/api')
    runs.value = response

    // 載入運行中任務的進度
    for (const run of runs.value) {
      if (run.status === 'running' || run.status === 'paused') {
        loadProgress(run.id)
      }
    }
  } catch (error: any) {
    if (!silent) {
      ElMessage.error(`載入運行列表失敗：${error.message || error}`)
    }
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

async function loadProgress(runId: number) {
  try {
    const status = await request.get<RunStatusResponse>(
      `/workflows/runs/${runId}/status`,
      {},
      '/api',
      { showLoading: false }
    )
    
    if (status.nodes && status.nodes.length > 0) {
      const totalProgress = status.nodes.reduce((sum: number, node: NodeStatus) => {
        return sum + node.progress
      }, 0)
      progressCache.value[runId] = Math.round(totalProgress / status.nodes.length)
    }
  } catch (error) {
    // 靜默失敗，避免幹擾用戶
    console.warn(`[WorkflowRunsDialog] 載入進度失敗: runId=${runId}`, error)
  }
}

function getProgress(runId: number): number {
  return progressCache.value[runId] || 0
}

async function pauseRun(runId: number) {
  try {
    await request.post(`/workflows/runs/${runId}/pause`, {}, '/api')
    ElMessage.success('工作流已暫停')
    loadRuns()
  } catch (error: any) {
    ElMessage.error(`暫停失敗：${error.message || error}`)
  }
}

async function resumeRun(runId: number) {
  try {
    await request.post(`/workflows/runs/${runId}/resume`, {}, '/api')
    ElMessage.success('工作流已恢復，將從斷點繼續執行')
    loadRuns()
  } catch (error: any) {
    ElMessage.error(`恢復失敗：${error.message || error}`)
  }
}

async function resumeRunFromDialog(run: WorkflowRun) {
  try {
    // 關閉對話框
    visible.value = false
    
    // 通知父組件恢復執行
    emit('resume-run', run)
    
    ElMessage.success('正在恢復工作流執行...')
  } catch (error: any) {
    ElMessage.error(`恢復失敗：${error.message || error}`)
  }
}

async function cancelRun(runId: number) {
  try {
    await ElMessageBox.confirm('確定要取消這個工作流運行嗎？', '確認取消', {
      type: 'warning'
    })

    await request.post(`/workflows/runs/${runId}/cancel`, {}, '/api')
    ElMessage.success('工作流已取消')
    loadRuns()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(`取消失敗：${error.message || error}`)
    }
  }
}

async function viewNodeStatus(runId: number) {
  nodeStatusVisible.value = true
  loadingNodeStatus.value = true

  try {
    const status = await request.get<RunStatusResponse>(`/workflows/runs/${runId}/status`, {}, '/api')
    nodeStatuses.value = status.nodes || []
  } catch (error: any) {
    ElMessage.error(`載入節點狀態失敗：${error.message || error}`)
  } finally {
    loadingNodeStatus.value = false
  }
}

async function deleteRun(runId: number) {
  try {
    await ElMessageBox.confirm('確定要刪除這條運行記錄嗎？此操作不可恢復。', '確認刪除', {
      type: 'warning',
      confirmButtonText: '確定刪除',
      cancelButtonText: '取消'
    })

    await deleteRunApi(runId)
    ElMessage.success('運行記錄已刪除')
    loadRuns()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(`刪除失敗：${error.message || error}`)
    }
  }
}

function getStatusType(status: string): string {
  const typeMap: Record<string, string> = {
    running: 'primary',
    paused: 'warning',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'info',
    idle: 'info',
    pending: 'info',
    success: 'success',
    error: 'danger'
  }
  return typeMap[status] || 'info'
}

function getStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    running: '運行中',
    paused: '已暫停',
    succeeded: '已完成',
    failed: '失敗',
    cancelled: '已取消',
    idle: '空閒',
    pending: '等待中',
    success: '成功',
    error: '錯誤',
    skipped: '已跳過'
  }
  return labelMap[status] || status
}

function formatTime(time?: string | number): string {
  if (!time) return '-'
  
  // 如果是數字（Unix 時間戳），需要乘以 1000 轉換爲毫秒
  // 但如果數字很小（< 100000000），說明可能是錯誤的資料
  if (typeof time === 'number') {
    console.warn('[formatTime] 收到數字類型的時間戳:', time)
    if (time < 100000000) {
      console.error('[formatTime] 時間戳異常小，可能是錯誤資料')
      return '資料異常'
    }
    time = time * 1000 // 轉換爲毫秒
  }
  
  const date = new Date(time)
  
  // 檢查日期是否有效
  if (isNaN(date.getTime())) {
    console.error('[formatTime] 無效的日期:', time)
    return '無效日期'
  }
  
  // 檢查日期是否在合理範圍內（2020-2030）
  const year = date.getFullYear()
  if (year < 2020 || year > 2030) {
    console.error('[formatTime] 日期超出合理範圍:', date.toISOString(), '原始值:', time)
    return '日期異常'
  }
  
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}
</script>

<style scoped>
.runs-dialog-content {
  min-height: 400px;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}
</style>
