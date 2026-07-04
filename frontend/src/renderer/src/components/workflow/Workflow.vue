<template>
  <div class="workflow-container">
    <!-- 頂部工具欄 -->
    <div class="workflow-toolbar">
      <div class="toolbar-left">
        <el-select
          v-model="currentWorkflowId"
          placeholder="選擇工作流"
          filterable
          clearable
          @change="onWorkflowChange"
          style="width: 300px"
        >
          <el-option
            v-for="wf in workflowList"
            :key="wf.id"
            :label="wf.name"
            :value="wf.id"
          >
            <span style="float: left">{{ wf.name }}</span>
            <span style="float: right; color: #8492a6; font-size: 13px">
              {{ formatDate(wf.updated_at) }}
            </span>
          </el-option>
        </el-select>

        <el-button @click="createNewWorkflow">
          <el-icon><Plus /></el-icon>
          <span>新建</span>
        </el-button>
        
        <el-button 
          @click="deleteWorkflow" 
          :disabled="!currentWorkflowId"
          type="danger"
          plain
        >
          <el-icon><Delete /></el-icon>
          <span>刪除</span>
        </el-button>
      </div>

      <div class="toolbar-right">
        <div class="toolbar-switch-item">
          <span class="switch-label">持久化保存</span>
          <el-switch
            v-model="keepRunHistory"
            @change="onKeepRunHistoryChange"
            :disabled="!currentWorkflowId"
            size="small"
          />
        </div>
        
        <el-divider direction="vertical" />
        
        <el-button 
          @click="showRunsDialog = true"
          plain
        >
          <el-icon><Clock /></el-icon>
          <span>運行記錄</span>
        </el-button>
        
        <el-button 
          @click="validateWorkflowCode" 
          :disabled="!currentWorkflowId"
          plain
        >
          <el-icon><CircleCheck /></el-icon>
          <span>校驗代碼</span>
        </el-button>
        
        <el-divider direction="vertical" />
        
        <el-button @click="saveWorkflow">
          <el-icon><Document /></el-icon>
          <span>保存</span>
        </el-button>
        
        <el-divider direction="vertical" />
        
        <el-button
          v-if="canStart"
          @click="runWorkflow"
          type="primary"
        >
          <el-icon><VideoPlay /></el-icon>
          <span>執行</span>
        </el-button>
        <el-button
          v-if="canPause"
          @click="pauseCurrentRun"
          type="warning"
        >
          <el-icon><VideoPause /></el-icon>
          <span>暫停</span>
        </el-button>
        <el-button
          v-if="canResume"
          @click="resumeCurrentRun"
          type="success"
        >
          <el-icon><VideoPlay /></el-icon>
          <span>恢復</span>
        </el-button>
      </div>
    </div>

    <!-- 主內容區 -->
    <div class="workflow-content">
      <!-- 節點庫 -->
      <div class="library-section" :style="{ width: libraryWidth + 'px' }">
        <node-library @add-node="onAddNode" />
      </div>

      <!-- 拖動條 - 節點庫 -->
      <div class="resize-handle" @mousedown="startResizing('library')"></div>

      <!-- 節點塊編輯器 -->
      <div class="editor-section">
        <div class="section-header">
          <span class="section-title">工作流節點</span>
          <span class="section-subtitle" v-if="currentWorkflowName">
            {{ currentWorkflowName }}
          </span>
          <div class="view-mode-toggle" style="margin-left: auto">
             <el-radio-group v-model="viewMode" size="small">
                <el-radio-button label="visual">
                   <el-icon><List /></el-icon> 可視化
                </el-radio-button>
                <el-radio-button label="code">
                   <el-icon><Document /></el-icon> 代碼
                </el-radio-button>
             </el-radio-group>
          </div>
        </div>
        <div style="flex: 1; overflow: hidden; position: relative">
            <node-block-editor
              v-if="viewMode === 'visual'"
              v-model="code"
              :is-running="isRunning"
              :workflow-id="currentWorkflowId"
              :revision="currentWorkflowRevision"
              @revision-changed="handleVisualRevisionChanged"
            />
            <code-editor
              v-else
              v-model="code"
            />
        </div>
      </div>

      <!-- 拖動條 - Notebook -->
      <div class="resize-handle" @mousedown="startResizing('notebook')"></div>

      <!-- Notebook執行視圖 -->
      <div class="notebook-section" :style="{ width: notebookWidth + 'px' }">
        <workflow-notebook
          :cells="notebookCells"
          :is-running="isRunning"
          @cell-output="onCellOutput"
          @clear-output="clearOutput"
        />
      </div>
    </div>

    <!-- 運行記錄對話框 -->
    <workflow-runs-dialog 
      v-model="showRunsDialog" 
      :workflow-id="currentWorkflowId"
      @resume-run="onResumeRun"
    />

    <workflow-agent-dialog
      :workflow-id="currentWorkflowId"
      :revision="currentWorkflowRevision"
      @applied="handleWorkflowAgentApplied"
    />

    <!-- 校驗結果對話框 -->
    <el-dialog
      v-model="showValidationDialog"
      title="工作流校驗結果"
      width="600px"
    >
      <div v-if="validationResult">
        <el-alert
          :type="validationResult.is_valid ? 'success' : 'error'"
          :title="validationResult.is_valid ? '校驗通過' : '校驗失敗'"
          :closable="false"
          style="margin-bottom: 16px"
        >
          <template v-if="!validationResult.is_valid">
            發現 {{ validationResult.errors.length }} 個錯誤
            <span v-if="validationResult.warnings.length > 0">
              和 {{ validationResult.warnings.length }} 個警告
            </span>
          </template>
        </el-alert>

        <!-- 錯誤列表 -->
        <div v-if="validationResult.errors.length > 0" style="margin-bottom: 16px">
          <h4 style="margin-bottom: 8px; color: #f56c6c">錯誤</h4>
          <el-scrollbar max-height="300px">
            <div
              v-for="(error, index) in validationResult.errors"
              :key="'error-' + index"
              class="validation-item error-item"
            >
              <div class="validation-header">
                <el-tag type="danger" size="small">{{ error.error_type }}</el-tag>
                <span class="validation-location">行 {{ error.line }}</span>
                <span v-if="error.variable" class="validation-variable">{{ error.variable }}</span>
              </div>
              <div class="validation-message">{{ error.message }}</div>
              <div v-if="error.suggestion" class="validation-suggestion">
                💡 {{ error.suggestion }}
              </div>
            </div>
          </el-scrollbar>
        </div>

        <!-- 警告列表 -->
        <div v-if="validationResult.warnings.length > 0">
          <h4 style="margin-bottom: 8px; color: #e6a23c">警告</h4>
          <el-scrollbar max-height="200px">
            <div
              v-for="(warning, index) in validationResult.warnings"
              :key="'warning-' + index"
              class="validation-item warning-item"
            >
              <div class="validation-header">
                <el-tag type="warning" size="small">{{ warning.error_type }}</el-tag>
                <span class="validation-location">行 {{ warning.line }}</span>
                <span v-if="warning.variable" class="validation-variable">{{ warning.variable }}</span>
              </div>
              <div class="validation-message">{{ warning.message }}</div>
              <div v-if="warning.suggestion" class="validation-suggestion">
                💡 {{ warning.suggestion }}
              </div>
            </div>
          </el-scrollbar>
        </div>
      </div>

      <template #footer>
        <el-button @click="showValidationDialog = false">關閉</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Document, Delete, VideoPlay, VideoPause, Close, List, Clock, CircleCheck, ArrowDown } from '@element-plus/icons-vue'
import NodeBlockEditor from './editor/NodeBlockEditor.vue'
import CodeEditor from './editor/CodeEditor.vue'
import WorkflowNotebook from './notebook/WorkflowNotebook.vue'
import NodeLibrary from './panels/NodeLibrary.vue'
import WorkflowRunsDialog from './dialogs/WorkflowRunsDialog.vue'
import WorkflowAgentDialog from './WorkflowAgentDialog.vue'
import { useWorkflowExecution } from '@/composables/useWorkflowExecution'
import { useWorkflowProgress } from '@/composables/useWorkflowProgress'
import { applyWorkflowPatch } from '@/api/workflowAgent'
import {
  listWorkflows,
  saveCodeWorkflow,
  getCodeWorkflow,
  updateWorkflow,
  deleteWorkflow as deleteWorkflowApi,
  validateWorkflow
} from '@/api/workflows'
import request from '@/api/request'

// 使用狀態機管理執行狀態
const {
  execution,
  isRunning,
  isPaused,
  isIdle,
  canPause,
  canResume,
  canStart,
  start: startExecution,
  updateRunId,
  pause: pauseExecution,
  resume: resumeExecution,
  complete: completeExecution,
  fail: failExecution,
  reset: resetExecution
} = useWorkflowExecution()

// 使用進度管理
const { startWorkflow, pauseWorkflow } = useWorkflowProgress()

const code = ref(``)
const showRunsDialog = ref(false)
const showValidationDialog = ref(false)
const validationResult = ref(null)

const viewMode = ref('visual') // 'visual' | 'code'
const notebookCells = reactive([])
let currentWorkflowId = ref(null) // 當前工作流ID
let currentWorkflowName = ref('未命名工作流') // 當前工作流名稱
const currentWorkflowRevision = ref('')
const keepRunHistory = ref(false) // 是否持久化保存運行記錄
const workflowList = ref([]) // 工作流列表

// 拖動調整寬度
const libraryWidth = ref(280)
const notebookWidth = ref(500)
const minLibraryWidth = 200
const maxLibraryWidth = 500
const minNotebookWidth = 300
const maxNotebookWidth = 800
let resizingPanel = ref(null)
let startX = 0
let startWidth = 0

function startResizing(panel) {
  resizingPanel.value = panel
  startX = window.event.clientX
  startWidth = panel === 'library' ? libraryWidth.value : notebookWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', handleResizing)
  window.addEventListener('mouseup', stopResizing)
}

function handleResizing(e) {
  if (!resizingPanel.value) return
  
  if (resizingPanel.value === 'library') {
    let newWidth = startWidth + (e.clientX - startX)
    newWidth = Math.max(minLibraryWidth, Math.min(maxLibraryWidth, newWidth))
    libraryWidth.value = newWidth
  } else if (resizingPanel.value === 'notebook') {
    let newWidth = startWidth - (e.clientX - startX)
    newWidth = Math.max(minNotebookWidth, Math.min(maxNotebookWidth, newWidth))
    notebookWidth.value = newWidth
  }
}

function stopResizing() {
  resizingPanel.value = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', handleResizing)
  window.removeEventListener('mouseup', stopResizing)
}

// 加載工作流列表
const loadWorkflowList = async () => {
  try {
    const workflows = await listWorkflows()
    // 所有工作流都是代碼式工作流（dsl_version === 2）
    workflowList.value = workflows.filter(wf => {
      return wf.dsl_version === 2
    })
  } catch (error) {
    console.error('[Workflow] 加載工作流列表失敗:', error)
    ElMessage.error('加載工作流列表失敗')
  }
}

// 刷新工作流列表
const refreshWorkflowList = async () => {
  await loadWorkflowList()
  ElMessage.success('工作流列表已刷新')
}

// 工作流切換
const onWorkflowChange = async (workflowId) => {
  if (!workflowId) {
    // 清空選擇
    currentWorkflowId.value = null
    currentWorkflowName.value = '未命名工作流'
    code.value = `# 示例工作流
#@node(description="選擇項目")
project = Logic.SelectProject(project_id=1)
#</node>

#@node(description="加載小說目錄")
novel = Novel.Load(root_path="E:\\\\Novels\\\\book")
#</node>

#@node(description="批量創建分卷卡片")
cards = Card.BatchUpsert(
    items=novel.volume_list,
    card_type="volume",
    title_template="{item}"
)
#</node>`
    notebookCells.length = 0
    return
  }

  try {
    const workflow = await getCodeWorkflow(workflowId)
    currentWorkflowId.value = workflow.id
    currentWorkflowName.value = workflow.name
    code.value = workflow.code || ''
    currentWorkflowRevision.value = workflow.revision || ''
    keepRunHistory.value = workflow.keep_run_history || false // 加載持久化設置
    notebookCells.length = 0 // 清空輸出
  } catch (error) {
    console.error('[Workflow] 加載工作流失敗:', error)
    ElMessage.error('加載工作流失敗')
  }
}

// 創建新工作流
const createNewWorkflow = async () => {
  try {
    const { value: name } = await ElMessageBox.prompt('請輸入工作流名稱', '新建工作流', {
      confirmButtonText: '確定',
      cancelButtonText: '取消',
      inputValue: '新工作流',
      inputPattern: /\S+/,
      inputErrorMessage: '工作流名稱不能爲空',
      inputValidator: (value) => {
        if (!value || !value.trim()) {
          return '工作流名稱不能爲空'
        }
        // 檢查是否重名
        const exists = workflowList.value.some(wf => wf.name === value.trim())
        if (exists) {
          return '工作流名稱已存在，請使用其他名稱'
        }
        return true
      }
    })

    // 創建新工作流，使用 marker DSL 模板
    const initialCode = `# 新工作流
#@node(description="選擇項目")
project = Logic.SelectProject(project_id=1)
#</node>`
    const workflow = await saveCodeWorkflow(name, initialCode)
    currentWorkflowId.value = workflow.id
    currentWorkflowName.value = workflow.name
    code.value = initialCode  // 更新代碼
    currentWorkflowRevision.value = ''

    // 刷新列表
    await loadWorkflowList()

    ElMessage.success(`工作流"${workflow.name}"已創建`)
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[Workflow] 創建工作流失敗:', error)
      ElMessage.error('創建工作流失敗')
    }
  }
}

// 刪除工作流
const deleteWorkflow = async () => {
  if (!currentWorkflowId.value) {
    ElMessage.warning('請先選擇要刪除的工作流')
    return
  }

  try {
    await ElMessageBox.confirm(
      `確定要刪除工作流"${currentWorkflowName.value}"嗎？此操作不可恢復。`,
      '刪除工作流',
      {
        confirmButtonText: '確定刪除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 刪除工作流
    await deleteWorkflowApi(currentWorkflowId.value)

    // 清空當前選擇
    currentWorkflowId.value = null
    currentWorkflowName.value = '未命名工作流'
    currentWorkflowRevision.value = ''
    code.value = `# 示例工作流
#@node(description="選擇項目")
project = Logic.SelectProject(project_id=1)
#</node>

#@node(description="加載小說目錄")
novel = Novel.Load(root_path="E:\\\\Novels\\\\book")
#</node>

#@node(description="批量創建分卷卡片")
cards = Card.BatchUpsert(
    items=novel.volume_list,
    card_type="volume",
    title_template="{item}"
)
#</node>`
    notebookCells.length = 0

    // 刷新列表
    await loadWorkflowList()

    ElMessage.success('工作流已刪除')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[Workflow] 刪除工作流失敗:', error)
      ElMessage.error('刪除工作流失敗')
    }
  }
}

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date

  // 小於1分鐘
  if (diff < 60000) return '剛剛'
  // 小於1小時
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分鐘前`
  // 小於1天
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小時前`
  // 小於7天
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`

  // 超過7天顯示日期
  return date.toLocaleDateString('zh-CN')
}

// 持久化開關變更
const onKeepRunHistoryChange = async (value) => {
  if (!currentWorkflowId.value) return
  
  try {
    await updateWorkflow(currentWorkflowId.value, {
      keep_run_history: value
    })
    ElMessage.success(value ? '已開啓運行記錄持久化' : '已關閉運行記錄持久化')
  } catch (error) {
    console.error('[Workflow] 更新持久化設置失敗:', error)
    ElMessage.error('更新持久化設置失敗')
    // 恢復原值
    keepRunHistory.value = !value
  }
}

// 執行工作流
const runWorkflow = async () => {
  if (!canStart.value) return

  notebookCells.length = 0 // 清空之前的輸出

  try {
    // 1. 每次執行都重新保存工作流（確保代碼是最新的）
    if (currentWorkflowId.value) {
      // 更新現有工作流
      await updateWorkflow(currentWorkflowId.value, {
        definition_code: code.value
      })
      currentWorkflowRevision.value = ''
    } else {
      // 創建新工作流
      const workflow = await saveCodeWorkflow(currentWorkflowName.value, code.value)
      currentWorkflowId.value = workflow.id
    }

    // 2. 執行工作流
    // 使用全局 SSE 連接管理（自動更新狀態欄）
    await startWorkflow(
      currentWorkflowId.value,
      currentWorkflowName.value,
      {
        onRunStarted: (actualRunId) => {
          // 更新狀態機中的 runId（不改變狀態）
          updateRunId(actualRunId)
        },
        onStart: (event) => {
          notebookCells.push({
            id: event.statement?.variable || 'unknown',
            type: 'execution',
            content: event.statement?.code || '',
            description: event.statement?.description || '',
            status: 'running',
            outputs: []
          })
        },
        onProgress: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            // 使用 splice 來強制觸發響應式更新
            const updatedCell = {
              ...notebookCells[cellIndex],
              status: 'progress',
              progress: event.percent,
              message: event.message
            }
            notebookCells.splice(cellIndex, 1, updatedCell)
          }
        },
        onComplete: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            notebookCells[cellIndex] = {
              ...notebookCells[cellIndex],
              status: 'completed',
              outputs: [event.result],
              resumed: event.resumed || false  // 標記是否是恢復的節點
            }
          } else {
            // 如果 cell 不存在（恢復的節點），創建一個
            notebookCells.push({
              id: event.statement?.variable || 'unknown',
              type: 'execution',
              content: event.statement?.code || '',
              status: 'completed',
              outputs: [event.result],
              resumed: true  // 標記爲恢復的節點
            })
          }
        },
        onError: (event) => {
          const cell = notebookCells.find(c => c.id === event.statement?.variable)
          if (cell) {
            cell.status = 'error'
            cell.error = event.error
          } else {
            // 沒有對應的 cell（比如解析失敗），創建一個錯誤 cell
            notebookCells.push({
              id: 'error-' + Date.now(),
              type: 'execution',
              content: event.statement?.code || '代碼解析失敗',
              status: 'error',
              error: event.error || '未知錯誤',
              outputs: []
            })
          }
          // 標記爲失敗狀態
          failExecution(event.error || '工作流執行失敗')
          ElMessage.error(event.error || '工作流執行失敗')
        },
        onEnd: () => {
          // 如果不是失敗狀態，標記爲完成
          if (execution.state === 'running') {
            completeExecution()
          }
        }
      },
      false // resume=false，從頭開始
    )
    
    // 初始狀態轉換（使用臨時 runId 0）
    // 真實的 runId 會在 onRunStarted 回調中更新
    startExecution(currentWorkflowId.value, 0)
  } catch (error) {
    console.error('[Workflow] 工作流執行失敗:', error)
    failExecution(error.message || '工作流執行失敗')
    ElMessage.error(error.message || '工作流執行失敗')
  }
}

// 清空輸出
const clearOutput = () => {
  notebookCells.length = 0
  // 重置狀態機
  if (!isIdle.value) {
    resetExecution()
  }
}

// 暫停當前運行
const pauseCurrentRun = async () => {
  if (!canPause.value) return
  
  if (execution.runId === null || execution.runId === undefined) {
    console.error('[Workflow] 無法暫停：缺少 runId')
    return
  }
  
  try {
    console.log('[Workflow] 開始暫停工作流:', execution.runId)
    
    // 1. 先通過 store 關閉 SSE 連接（停止接收事件）
    pauseWorkflow(execution.runId)
    
    // 2. 調用 pause API 更新數據庫狀態（後端會停止執行）
    await request.post(`/workflows/runs/${execution.runId}/pause`, {}, '/api')
    
    // 3. 狀態機轉換到暫停狀態
    pauseExecution()
    
    console.log('[Workflow] 工作流已暫停')
    ElMessage.success('工作流已暫停')
  } catch (error) {
    console.error('[Workflow] 暫停失敗:', error)
    ElMessage.error(`暫停失敗：${error.message || error}`)
  }
}

// 恢復當前運行
const resumeCurrentRun = async () => {
  if (!canResume.value) return
  
  if (execution.runId === null || execution.runId === undefined || execution.workflowId === null || execution.workflowId === undefined) {
    console.error('[Workflow] 無法恢復：缺少 runId 或 workflowId')
    return
  }
  
  try {
    // 清空之前的輸出（避免重複顯示）
    notebookCells.length = 0
    
    // 恢復執行：傳遞 resume=true 和 run_id
    await startWorkflow(
      execution.workflowId,
      currentWorkflowName.value,
      {
        onStart: (event) => {
          notebookCells.push({
            id: event.statement?.variable || 'unknown',
            type: 'execution',
            content: event.statement?.code || '',
            status: 'running',
            outputs: []
          })
        },
        onProgress: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            const updatedCell = {
              ...notebookCells[cellIndex],
              status: 'progress',
              progress: event.percent,
              message: event.message
            }
            notebookCells.splice(cellIndex, 1, updatedCell)
          }
        },
        onComplete: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            notebookCells[cellIndex] = {
              ...notebookCells[cellIndex],
              status: 'completed',
              outputs: [event.result],
              resumed: event.resumed || false
            }
          } else {
            // 如果 cell 不存在（恢復的節點），創建一個
            notebookCells.push({
              id: event.statement?.variable || 'unknown',
              type: 'execution',
              content: event.statement?.code || '',
              description: event.statement?.description || '',
              status: 'completed',
              outputs: [event.result],
              resumed: true
            })
          }
        },
        onError: (event) => {
          const cell = notebookCells.find(c => c.id === event.statement?.variable)
          if (cell) {
            cell.status = 'error'
            cell.error = event.error
          } else {
            notebookCells.push({
              id: 'error-' + Date.now(),
              type: 'execution',
              content: event.statement?.code || '代碼解析失敗',
              description: event.statement?.description || '',
              status: 'error',
              error: event.error || '未知錯誤',
              outputs: []
            })
          }
          // 標記爲失敗狀態
          failExecution(event.error || '工作流執行失敗')
          ElMessage.error(event.error || '工作流執行失敗')
        },
        onEnd: () => {
          // 如果不是失敗狀態，標記爲完成
          if (execution.state === 'running') {
            completeExecution()
          }
        }
      },
      true, // resume=true
      execution.runId // 傳遞 run_id
    )
    
    // 狀態機轉換到運行狀態
    resumeExecution()
    
    ElMessage.success('工作流已恢復執行')
  } catch (error) {
    console.error('[Workflow] 恢復執行失敗:', error)
    failExecution(error.message || '恢復執行失敗')
    ElMessage.error(error.message || '恢復執行失敗')
  }
}

// 取消當前運行
const cancelCurrentRun = async () => {
  if (!currentRunId.value) return
  
  try {
    await ElMessageBox.confirm('確定要取消當前工作流運行嗎？', '確認取消', {
      type: 'warning'
    })
    
    await request.post(`/workflows/runs/${currentRunId.value}/cancel`, {}, '/api')
    ElMessage.success('工作流已取消')
    
    isRunning.value = false
    isPaused.value = false
    currentRunId.value = null
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`取消失敗：${error.message || error}`)
    }
  }
}

// 保存工作流
const saveWorkflow = async () => {
  try {
    if (currentWorkflowId.value) {
      // 更新現有工作流
      await updateWorkflow(currentWorkflowId.value, {
        definition_code: code.value
      })
      try {
        const workflowData = await getCodeWorkflow(currentWorkflowId.value)
        currentWorkflowRevision.value = workflowData.revision || ''
      } catch {
        // ignore
      }
      ElMessage.success('工作流已更新')
    } else {
      // 創建新工作流，先詢問名稱
      const { value: name } = await ElMessageBox.prompt('請輸入工作流名稱', '保存工作流', {
        confirmButtonText: '確定',
        cancelButtonText: '取消',
        inputValue: currentWorkflowName.value,
        inputPattern: /\S+/,
        inputErrorMessage: '工作流名稱不能爲空'
      })

      // 保存代碼式工作流
      const workflow = await saveCodeWorkflow(name, code.value)
      currentWorkflowId.value = workflow.id
      currentWorkflowName.value = workflow.name
      currentWorkflowRevision.value = ''
      ElMessage.success(`工作流"${workflow.name}"已保存`)
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[Workflow] 保存工作流失敗:', error)
      ElMessage.error(error.message || '保存工作流失敗')
    }
  }
}

// 校驗工作流
const validateWorkflowCode = async () => {
  if (!currentWorkflowId.value) {
    ElMessage.warning('請先選擇或保存工作流')
    return
  }

  try {
    const runPatchDryRun = async () => {
      return applyWorkflowPatch(currentWorkflowId.value, {
        base_revision: currentWorkflowRevision.value || '',
        patch_ops: [
          {
            op: 'replace_code',
            new_code: code.value || '',
            reason: 'ui_validate',
          },
        ],
        dry_run: true,
      })
    }

    let patchResult
    try {
      patchResult = await runPatchDryRun()
    } catch (error) {
      // 若 revision 落後，先刷新再重試一次
      const status = error?.response?.status
      const detail = error?.response?.data?.detail
      if (status === 409 && detail?.code === 'revision_mismatch') {
        const workflowData = await getCodeWorkflow(currentWorkflowId.value)
        currentWorkflowRevision.value = workflowData.revision || currentWorkflowRevision.value
        patchResult = await runPatchDryRun()
      } else {
        throw error
      }
    }

    validationResult.value = patchResult?.validation || {
      is_valid: false,
      errors: [
        {
          line: 0,
          variable: '',
          error_type: 'unknown',
          message: patchResult?.error || '校驗失敗',
          suggestion: null,
        },
      ],
      warnings: [],
    }
    showValidationDialog.value = true

    if (validationResult.value.is_valid) {
      ElMessage.success('校驗通過！')
    } else {
      ElMessage.error(`發現 ${validationResult.value.errors.length} 個錯誤`)
    }
  } catch (error) {
    console.error('校驗工作流失敗:', error)
    ElMessage.error('校驗工作流失敗')
  }
}

// 代碼變化處理
const onCodeChange = (newCode) => {
  code.value = newCode
}

// 節點選中處理
// const onNodeSelected = (node) => {
//   selectedNode.value = node
// }

// 節點更新處理（來自屬性面板）
const onNodeUpdate = (updatedNode) => {
  // 重新生成代碼
  // 需要找到對應的節點並替換其代碼
  const lines = code.value.split('\n')

  // 簡單實現：找到包含該變量名的行並替換
  // 更好的實現應該在 NodeBlockEditor 中維護節點列表
  let updated = false
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(`${updatedNode.variable} =`)) {
      lines[i] = updatedNode.code
      updated = true
      break
    }
  }

  if (updated) {
    code.value = lines.join('\n')
    ElMessage.success('節點已更新')
  } else {
    ElMessage.error('更新失敗：未找到對應節點')
  }
}

// 添加節點（來自節點庫）
const onAddNode = (nodeType) => {
  // 生成唯一的變量名
  const baseName = generateVariableName(nodeType)
  const variableName = generateUniqueVariableName(baseName)

  // 生成註釋標記 DSL 的節點代碼
  const nodeCode = `#@node()
${variableName} = ${nodeType}()
#</node>`

  // 添加到代碼末尾
  const newCode = code.value.trim()
  if (newCode) {
    code.value = newCode + '\n\n' + nodeCode  // 使用雙換行分隔
  } else {
    code.value = nodeCode
  }

  ElMessage.success('節點已添加')
}

// 根據節點類型生成基礎變量名
function generateVariableName(nodeType) {
  // 提取節點類型名並轉換爲合適的變量名
  const parts = nodeType.split('.')
  if (parts.length >= 2) {
    const method = parts[1].toLowerCase()
    // 移除常見的動詞前綴
    const cleanMethod = method.replace(/^(get|set|create|update|delete|fetch|load)_?/, '')
    return cleanMethod || method
  }
  return nodeType.replace(/\./g, '_').toLowerCase()
}

// 生成唯一的變量名
function generateUniqueVariableName(baseName) {
  let counter = 2
  let variableName = baseName

  // 檢查是否已存在同名變量
  const allLines = code.value.split('\n')
  const usedVariables = new Set()

  allLines.forEach(line => {
    // 賦值形式：variable = ...
    const assignMatch = line.match(/^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*/)
    if (assignMatch) {
      usedVariables.add(assignMatch[1])
    }
  })

  // 如果基礎名已存在，添加數字後綴
  while (usedVariables.has(variableName)) {
    variableName = `${baseName}${counter++}`
  }

  return variableName
}

// 單元格輸出處理
const onCellOutput = (output) => {
  // 處理單元格輸出
}

// 從運行記錄恢復執行
const onResumeRun = async (run) => {
  // 清空之前的輸出
  notebookCells.length = 0
  
  // 加載工作流代碼
  let workflowData
  try {
    workflowData = await getCodeWorkflow(run.workflow_id)
    code.value = workflowData.code || ''
    currentWorkflowName.value = workflowData.name
    currentWorkflowId.value = run.workflow_id
    currentWorkflowRevision.value = workflowData.revision || ''
  } catch (error) {
    console.error('[Workflow] 加載工作流失敗:', error)
    ElMessage.error('加載工作流失敗')
    return
  }
  
  try {
    await startWorkflow(
      run.workflow_id,
      workflowData.name,  // 使用 workflowData.name
      {
        onStart: (event) => {
          notebookCells.push({
            id: event.statement?.variable || 'unknown',
            type: 'execution',
            content: event.statement?.code || '',
            description: event.statement?.description || '',
            status: 'running',
            outputs: []
          })
        },
        onProgress: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            const updatedCell = {
              ...notebookCells[cellIndex],
              status: 'progress',
              progress: event.percent,
              message: event.message
            }
            notebookCells.splice(cellIndex, 1, updatedCell)
          }
        },
        onComplete: (event) => {
          const cellIndex = notebookCells.findIndex(c => c.id === event.statement?.variable)
          if (cellIndex !== -1) {
            notebookCells[cellIndex] = {
              ...notebookCells[cellIndex],
              status: 'completed',
              outputs: [event.result],
              resumed: event.resumed || false
            }
          } else {
            // 如果 cell 不存在（恢復的節點），創建一個
            notebookCells.push({
              id: event.statement?.variable || 'unknown',
              type: 'execution',
              content: event.statement?.code || '',
              description: event.statement?.description || '',
              status: 'completed',
              outputs: [event.result],
              resumed: true
            })
          }
        },
        onError: (event) => {
          const cell = notebookCells.find(c => c.id === event.statement?.variable)
          if (cell) {
            cell.status = 'error'
            cell.error = event.error
          } else {
            notebookCells.push({
              id: 'error-' + Date.now(),
              type: 'execution',
              content: event.statement?.code || '代碼解析失敗',
              description: event.statement?.description || '',
              status: 'error',
              error: event.error || '未知錯誤',
              outputs: []
            })
          }
          // 標記爲失敗狀態
          failExecution(event.error || '工作流執行失敗')
          ElMessage.error(event.error || '工作流執行失敗')
        },
        onEnd: () => {
          // 如果不是失敗狀態，標記爲完成
          if (execution.state === 'running') {
            completeExecution()
          }
        }
      },
      true, // resume=true
      run.id // 傳遞 run_id
    )
    
    // 狀態機轉換到運行狀態
    startExecution(run.workflow_id, run.id)
  } catch (error) {
    console.error('[Workflow] 恢復執行失敗:', error)
    failExecution(error.message || '恢復執行失敗')
    ElMessage.error(error.message || '恢復執行失敗')
  }
}

// 組件卸載時清理
onUnmounted(() => {
  // SSE 連接由 store 管理，組件卸載時不需要手動清理
})

// 組件掛載時加載工作流列表
onMounted(() => {
  loadWorkflowList()
})

const handleWorkflowAgentApplied = (payload) => {
  code.value = payload.newCode || code.value
  if (payload.newRevision) {
    currentWorkflowRevision.value = payload.newRevision
  }
}

const handleVisualRevisionChanged = (revision) => {
  if (typeof revision === 'string' && revision.trim()) {
    currentWorkflowRevision.value = revision
  }
}
</script>

<style scoped>
.workflow-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color-page);
}

.workflow-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  box-shadow: 0 1px 4px var(--el-box-shadow-light);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-switch-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  height: 32px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
}

.switch-label {
  font-size: 14px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.dropdown-switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  min-width: 180px;
}

.switch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.workflow-content {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
  background: var(--el-border-color-lighter);
  position: relative;
}

.library-section {
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
  flex-shrink: 0;
}

.resize-handle {
  width: 4px;
  background: var(--el-border-color-lighter);
  cursor: col-resize;
  flex-shrink: 0;
  position: relative;
  transition: background-color 0.2s;
}

.resize-handle:hover {
  background: var(--el-color-primary);
}

.resize-handle:active {
  background: var(--el-color-primary);
}

.editor-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
  min-width: 400px;
}

.property-section {
  width: 350px;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
}

.notebook-section {
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  overflow: hidden;
  flex-shrink: 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.section-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* 校驗結果樣式 */
.validation-item {
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 4px;
  border-left: 3px solid;
}

.error-item {
  background-color: var(--el-color-danger-light-9);
  border-left-color: var(--el-color-danger);
}

.warning-item {
  background-color: var(--el-color-warning-light-9);
  border-left-color: var(--el-color-warning);
}

.validation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.validation-location {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.validation-variable {
  font-size: 12px;
  font-family: 'Courier New', monospace;
  color: var(--el-text-color-regular);
  background-color: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 3px;
}

.validation-message {
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.validation-suggestion {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-style: italic;
}
</style>
