<template>
  <div class="node-block-editor">
    <!-- 節點塊列表 -->
    <div class="node-blocks">
      <div
        v-for="(node, index) in nodes"
        :key="index"
        class="node-block"
        :class="{ 
          'is-selected': selectedIndex === index,
          'is-disabled': node.disabled
        }"
        @click="selectNode(index)"
        @dblclick="editNodeCode(index)"
      >
        <!-- 節點頭部 -->
        <div class="node-block-header">
          <div class="node-info">
            <el-tag :type="getNodeCategoryColor(node.category)" size="small">
              {{ node.category }}
            </el-tag>
            <!-- 異步標識 -->
            <el-tag v-if="node.isAsync" type="warning" size="small" effect="dark">
              ⚡ 異步
            </el-tag>
            <!-- 變量名編輯 -->
            <el-input
              v-if="editingVariable?.nodeIndex === index"
              v-model="editingVariable.value"
              size="small"
              style="width: 120px"
              @blur="saveVariableEdit"
              @keydown.enter.stop="saveVariableEdit"
              @keydown.esc="cancelVariableEdit"
              ref="variableInputRef"
            />
            <span
              v-else
              class="node-variable editable"
              @click.stop="startVariableEdit(index, node.variable)"
              :title="點擊編輯變量名"
            >
              {{ node.variable }}
            </span>
            <span class="node-type">{{ node.nodeType }}</span>
          </div>
          <div class="node-actions">
            <el-tooltip :content="node.isAsync ? '切換爲同步' : '切換爲異步'" placement="top">
              <el-button
                size="small"
                text
                @click.stop="toggleAsync(index)"
                :type="node.isAsync ? 'warning' : 'info'"
              >
                <template #icon>
                  <span style="font-size: 16px">{{ node.isAsync ? '⚡' : '🔄' }}</span>
                </template>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="node.disabled ? '啓用節點' : '禁用節點'" placement="top">
              <el-switch
                v-model="node.disabled"
                @change="toggleNodeDisabled(index)"
                size="small"
                inactive-text=""
                active-text=""
                :active-value="true"
                :inactive-value="false"
                style="--el-switch-on-color: #909399; --el-switch-off-color: #67c23a"
                @click.stop
              />
            </el-tooltip>
            <el-tooltip content="刪除節點" placement="top">
              <el-button
                size="small"
                text
                type="danger"
                @click.stop="deleteNode(index)"
                :icon="Delete"
              />
            </el-tooltip>
          </div>
        </div>

        <div v-if="node.description" class="node-description" @click.stop>
          {{ node.description }}
        </div>

        <!-- 節點參數編輯器 -->
        <div class="node-params" v-if="node.fields && node.fields.length > 0">
          <div class="params-header">
            <div class="params-title">參數</div>
            <el-button
              text
              size="small"
              @click.stop="toggleNodeCollapse(index)"
              :icon="node.collapsed ? ArrowRight : ArrowDown"
            />
          </div>
          <div v-if="!node.collapsed" v-for="(field, fieldIndex) in node.fields" :key="field.name" class="param-item">
            <span class="param-key">{{ field.label }}:</span>
            <div class="param-value-wrapper">
              <!-- 編輯模式 -->
              <div
                v-if="editingParam?.nodeIndex === index && editingParam?.fieldIndex === fieldIndex"
                class="smart-selector"
                style="flex: 1; display:flex; gap: 4px;"
              >
                <!-- ProjectSelect (x-component: ProjectSelect) -->
                <el-select
                  v-if="field.rawSchema?.['x-component'] === 'ProjectSelect'"
                  v-model="editingParam.value"
                  filterable
                  :allow-create="field.name === 'project_name'"
                  :default-first-option="field.name === 'project_name'"
                  placeholder="選擇項目"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="p in projectList"
                    :key="p.id"
                    :label="p.name"
                    :value="getProjectOptionValue(field, p)"
                  />
                </el-select>

                <!-- LLMSelect (x-component: LLMSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'LLMSelect'"
                  v-model="editingParam.value"
                  filterable
                  :allow-create="field.name === 'llm_name'"
                  :default-first-option="field.name === 'llm_name'"
                  placeholder="選擇LLM配置"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="cfg in llmConfigList"
                    :key="cfg.id"
                    :label="cfg.display_name || cfg.model_name"
                    :value="getLlmOptionValue(field, cfg)"
                  />
                </el-select>

                <!-- PromptSelect (x-component: PromptSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'PromptSelect'"
                  v-model="editingParam.value"
                  filterable
                  placeholder="選擇提示詞"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="prompt in promptList"
                    :key="prompt.id"
                    :label="prompt.name"
                    :value="prompt.id"
                  />
                </el-select>

                <!-- CardTypeSelect (x-component: CardTypeSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'CardTypeSelect'"
                  v-model="editingParam.value"
                  filterable
                  allow-create
                  default-first-option
                  placeholder="卡片類型"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option
                    v-for="ct in cardTypeList"
                    :key="ct.id"
                    :label="ct.name"
                    :value="ct.name"
                  />
                </el-select>

                <!-- ResponseModelSelect (x-component: ResponseModelSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'ResponseModelSelect'"
                  v-model="editingParam.value"
                  filterable
                  placeholder="選擇響應模型"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option-group label="內置模型">
                    <el-option
                      v-for="model in builtinResponseModels"
                      :key="model"
                      :value="model"
                      :label="model"
                    />
                  </el-option-group>
                  <el-option-group label="自定義卡片類型">
                    <el-option
                      v-for="ct in cardTypeList"
                      :key="ct.id"
                      :label="ct.name"
                      :value="ct.name"
                    />
                  </el-option-group>
                </el-select>

                <!-- Textarea (x-component: Textarea) -->
                <el-input
                  v-else-if="field.rawSchema?.['x-component'] === 'Textarea'"
                  v-model="editingParam.value"
                  type="textarea"
                  :rows="4"
                  size="small"
                  placeholder="輸入內容"
                  @blur="saveParamEdit"
                />

                <!-- CodeEditor (x-component: CodeEditor) -->
                <el-input
                  v-else-if="field.rawSchema?.['x-component'] === 'CodeEditor'"
                  v-model="editingParam.value"
                  type="textarea"
                  :rows="6"
                  size="small"
                  class="code-expression-input"
                  placeholder="輸入 Python 表達式"
                  @blur="saveParamEdit"
                  @keydown.ctrl.enter.stop="saveParamEdit"
                />

                <!-- ToolMultiSelect (x-component: ToolMultiSelect) -->
                <el-select
                  v-else-if="field.rawSchema?.['x-component'] === 'ToolMultiSelect'"
                  v-model="editingParam.value"
                  filterable
                  multiple
                  collapse-tags
                  placeholder="選擇工具"
                  size="small"
                  @change="saveParamEdit"
                >
                  <el-option value="search_cards" label="搜索卡片" />
                  <el-option value="create_card" label="創建卡片" />
                  <el-option value="update_card" label="更新卡片" />
                  <el-option value="delete_card" label="刪除卡片" />
                  <el-option value="get_card" label="獲取卡片" />
                  <el-option value="list_cards" label="列出卡片" />
                </el-select>

                <!-- Case 5: Boolean Switch -->
                <el-switch
                  v-else-if="field.type === 'boolean'"
                  v-model="editingParam.value"
                  size="small"
                  @change="saveParamEdit"
                />
                
                <!-- Case 6: Array Input (dynamic list) -->
                <div v-else-if="field.type === 'array'" style="flex: 1; display: flex; flex-direction: column; gap: 4px;">
                  <div
                    v-for="(item, itemIndex) in editingParam.arrayItems"
                    :key="itemIndex"
                    style="display: flex; gap: 4px;"
                  >
                    <el-input
                      v-model="editingParam.arrayItems[itemIndex]"
                      size="small"
                      placeholder="輸入值"
                      style="flex: 1;"
                    />
                    <el-button
                      size="small"
                      type="danger"
                      :icon="Delete"
                      @click.stop="removeArrayItem(itemIndex)"
                    />
                  </div>
                  <el-button
                    size="small"
                    type="primary"
                    :icon="Plus"
                    @click.stop="addArrayItem"
                  >
                    添加項
                  </el-button>
                  <el-button
                    size="small"
                    type="success"
                    @click.stop="saveParamEdit"
                  >
                    保存
                  </el-button>
                </div>
                
                <!-- Case 7: Default Text Input -->
                <el-input
                  v-else
                  v-model="editingParam.value"
                  size="small"
                  @blur="saveParamEdit"
                  @keydown.enter.stop="saveParamEdit"
                >
                  <!-- Folder selection trigger for DirectorySelect -->
                  <template #append v-if="field.rawSchema?.['x-component'] === 'DirectorySelect'">
                    <el-button :icon="Folder" @click.stop="openFolderDialog" />
                  </template>
                </el-input>
              </div>

              <!-- 顯示模式 -->
              <el-input
                v-else-if="field.rawSchema?.['x-component'] === 'CodeEditor'"
                :model-value="formatDisplayValue(field)"
                type="textarea"
                :rows="3"
                readonly
                resize="none"
                class="param-code-preview"
                @click.stop="startParamEdit(index, fieldIndex)"
              />
              <span
                v-else
                class="param-value editable"
                @click.stop="startParamEdit(index, fieldIndex)"
              >
                {{ formatDisplayValue(field) }}
                <el-tag v-if="field.required" size="small" type="danger" style="margin-left: 4px">必填</el-tag>
                <!-- 智能選擇器提示圖標 -->
                <el-icon v-if="isSmartSelectorField(field)" class="selector-icon">
                  <ArrowDown />
                </el-icon>
                <el-icon v-else-if="field.rawSchema?.['x-component'] === 'DirectorySelect'" class="selector-icon">
                  <Folder />
                </el-icon>
                <el-icon v-else class="edit-icon">
                  <EditPen />
                </el-icon>
              </span>
            </div>
          </div>
        </div>

        <!-- 節點輸出字段 -->
        <div class="node-outputs" v-if="node.outputs && node.outputs.length > 0">
          <div class="outputs-title">輸出字段</div>
          <div class="output-items">
            <el-tag
              v-for="output in node.outputs"
              :key="output.name"
              size="small"
              type="success"
              class="output-tag"
            >
              {{ node.variable }}.{{ output.name }}
            </el-tag>
          </div>
        </div>

        <!-- 執行狀態（如果有） -->
        <div v-if="node.status" class="node-status" :class="`status-${node.status}`">
          <el-icon v-if="node.status === 'running'"><Loading /></el-icon>
          <el-icon v-else-if="node.status === 'completed'"><CircleCheck /></el-icon>
          <el-icon v-else-if="node.status === 'error'"><CircleClose /></el-icon>
          <span>{{ getStatusText(node.status) }}</span>
          <span v-if="node.progress !== undefined && node.status === 'running'">
            {{ node.progress }}%
          </span>
        </div>
      </div>

      <!-- 添加節點按鈕 -->
      <div class="add-node-block" @click="showAddNodeDialog">
        <el-icon><Plus /></el-icon>
        <span>添加節點</span>
      </div>
    </div>

    <!-- 添加節點對話框 -->
    <el-dialog
      v-model="addNodeDialogVisible"
      title="添加節點"
      width="600px"
    >
      <el-select
        v-model="selectedNodeType"
        placeholder="選擇節點類型"
        filterable
        style="width: 100%; margin-bottom: 16px"
      >
        <el-option-group
          v-for="(nodeList, category) in nodeTypesByCategory"
          :key="category"
          :label="category"
        >
          <el-option
            v-for="nodeType in nodeList"
            :key="nodeType.type"
            :label="`${nodeType.label} (${nodeType.type})`"
            :value="nodeType.type"
          >
            <div style="display: flex; flex-direction: column">
              <span>{{ nodeType.label }}</span>
              <span style="font-size: 12px; color: #909399">{{ nodeType.description }}</span>
            </div>
          </el-option>
        </el-option-group>
      </el-select>

      <el-input
        v-model="newNodeVariable"
        placeholder="變量名，例如: project"
        style="width: 100%"
      />

      <template #footer>
        <el-button @click="addNodeDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="addNode">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, Loading, CircleCheck, CircleClose, EditPen, Folder, ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import request from '@/api/request'
import { getContentModels } from '@/api/cards'
import { storeToRefs } from 'pinia'
import { useProjectListStore } from '@/stores/useProjectListStore'
import { useLLMConfigStore } from '@/stores/useLLMConfigStore'
import { usePromptStore } from '@/stores/usePromptStore'
import { useCardStore } from '@/stores/useCardStore'
import { ParameterFormatter } from '@/utils/parameterFormatter'
import { applyWorkflowPatch } from '@/api/workflowAgent'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  isRunning: {
    type: Boolean,
    default: false
  },
  workflowId: {
    type: Number,
    default: null
  },
  revision: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'node-selected', 'revision-changed'])

// 使用 stores
const projectListStore = useProjectListStore()
const llmConfigStore = useLLMConfigStore()
const promptStore = usePromptStore()
const cardStore = useCardStore()

// 從 stores 獲取響應式數據
const { projects: projectList } = storeToRefs(projectListStore)
const { llmConfigs: llmConfigList } = storeToRefs(llmConfigStore)
const { prompts: promptList } = storeToRefs(promptStore)
const { cardTypes: cardTypeList } = storeToRefs(cardStore)

// 狀態
const nodes = ref([])
const selectedIndex = ref(-1)
const addNodeDialogVisible = ref(false)
const selectedNodeType = ref('')
const newNodeVariable = ref('')
const nodeTypes = ref([])
// 參數編輯狀態
const editingParam = ref(null)
const paramInputRef = ref(null)
// 變量名編輯狀態
const editingVariable = ref(null)
const variableInputRef = ref(null)
// 智能選擇器數據
const variableList = ref([]) // 所有的變量列表
const fileDialogVisible = ref(false)
const builtinResponseModels = ref([])
// 內部更新標記
const isInternalUpdate = ref(false)
const parseWatchSeq = ref(0)
const revisionRef = ref(props.revision || '')

watch(() => props.revision, value => {
  revisionRef.value = value || ''
})

// 按分類組織的節點類型
const nodeTypesByCategory = computed(() => {
  const grouped = {}
  nodeTypes.value.forEach(nodeType => {
    if (!grouped[nodeType.category]) {
      grouped[nodeType.category] = []
    }
    grouped[nodeType.category].push(nodeType)
  })
  return grouped
})

// 解析代碼爲節點塊
async function parseCodeToNodes(code) {
  if (!code || !code.trim()) return []

  try {
    // 直接發送代碼給後端解析（後端會處理元數據註釋）
    const response = await request.post('/workflows/parse', { code }, '/api')
    
    if (!response.success || !response.statements) {
      const errorMsg = response.errors?.join('; ') || '未知錯誤'
      console.error('代碼解析失敗:', response.errors)
      throw new Error(errorMsg)
    }
    
    console.log(`[parseCodeToNodes] 解析了 ${response.statements.length} 個語句`)
    
    const parsedNodes = []
    
    // 構建節點
    for (let i = 0; i < response.statements.length; i++) {
      const stmt = response.statements[i]
      
      console.log(`[parseCodeToNodes] 語句 ${i}: ${stmt.variable} (行${stmt.line}), disabled=${stmt.disabled}, async=${stmt.is_async}`)
        
      // 處理節點調用
      if (stmt.node_type && stmt.node_type !== 'expression' && stmt.node_type !== '_wait') {
        const parts = stmt.node_type.split('.')
        const category = parts[0]
        const method = parts.slice(1).join('.')
        
        const node = {
          variable: stmt.variable,
          category: category,
          method: method,
          nodeType: stmt.node_type,
          description: stmt.description || '',
          params: stmt.config || {},
          code: stmt.code,
          outputs: [],
          collapsed: false,
          disabled: stmt.disabled || false,  // 從後端獲取
          isAsync: stmt.is_async || false    // 從後端獲取
        }
        
        await fetchNodeOutputs(node)
        parsedNodes.push(node)
      } else {
        // 處理純表達式、wait語句或其他非標準節點
        parsedNodes.push({
          variable: stmt.variable,
          category: 'Raw',
          method: 'Code',
          nodeType: stmt.node_type || 'Raw.Code',
          description: stmt.description || '',
          params: stmt.config || {},
          code: stmt.code,
          outputs: [],
          collapsed: false,
          disabled: stmt.disabled || false,
          isAsync: stmt.is_async || false
        })
      }
    }
    return parsedNodes
  } catch (error) {
    console.error('解析請求失敗:', error)
    // 重新拋出異常，讓調用者處理
    throw error
  }
}

// 獲取節點的輸入輸出字段
async function fetchNodeOutputs(node) {
  try {
    const response = await request.get(`/nodes/${node.nodeType}/metadata`, undefined, '/api', {
      showLoading: false
    })
    node.outputs = response.outputs || []

    // 合併字段定義和參數值，構建統一的字段列表
    const schema = response.input_schema?.properties || {}
    const hiddenFields = ['debug', 'debug_mode', 'verbose', 'log_level']
    
    // 首先從 schema 創建字段
    const schemaFields = Object.entries(schema)
      .filter(([fieldName]) => !hiddenFields.includes(fieldName))
      .map(([fieldName, fieldDef]) => {
        // 從 params 中獲取原始值
        let rawValue = node.params?.[fieldName]
        
        // 格式化爲字符串（用於顯示和代碼生成）
        let formattedValue = ''
        
        if (rawValue !== undefined && rawValue !== null && rawValue !== '') {
          const fieldType = resolveFieldType(fieldDef)
          
          console.log(`[fetchNodeOutputs] 處理字段 ${fieldName}:`, {
            fieldType,
            rawValue,
            rawValueType: typeof rawValue,
            isObject: typeof rawValue === 'object',
            isArray: Array.isArray(rawValue)
          })
          
          // 始終使用 ParameterFormatter 格式化
          try {
            formattedValue = ParameterFormatter.format({
              type: fieldType,
              value: rawValue
            })
            
            console.log(`[fetchNodeOutputs] 格式化成功 ${fieldName}:`, {
              formattedValue,
              formattedType: typeof formattedValue
            })
            
            // 確保返回的是字符串
            if (typeof formattedValue !== 'string') {
              console.warn(`[fetchNodeOutputs] 格式化結果不是字符串，強制轉換: ${fieldName}`)
              formattedValue = JSON.stringify(formattedValue)
            }
          } catch (e) {
            console.error(`[fetchNodeOutputs] 格式化字段 ${fieldName} 失敗:`, e, 'rawValue:', rawValue)
            // 降級處理：確保返回字符串
            if (typeof rawValue === 'object' && rawValue !== null) {
              formattedValue = JSON.stringify(rawValue)
            } else {
              formattedValue = String(rawValue)
            }
            console.log(`[fetchNodeOutputs] 降級處理後 ${fieldName}:`, formattedValue)
          }
        }
        
        return {
          name: fieldName,
          label: fieldDef.description || fieldName,
          type: resolveFieldType(fieldDef),
          required: fieldDef.required || false,
          default: fieldDef.default,
          value: formattedValue,  // 確保是字符串
          rawSchema: fieldDef  // 保存原始 schema，用於獲取 x-component
        }
      })
    
    // 然後添加不在 schema 中但存在於 params 的字段
    const schemaFieldNames = new Set(Object.keys(schema))
    const extraFields = Object.entries(node.params || {})
      .filter(([fieldName]) => !schemaFieldNames.has(fieldName) && !hiddenFields.includes(fieldName))
      .map(([fieldName, rawValue]) => {
        // 推斷類型
        let fieldType = 'string'
        if (typeof rawValue === 'number') {
          fieldType = Number.isInteger(rawValue) ? 'integer' : 'number'
        } else if (typeof rawValue === 'boolean') {
          fieldType = 'boolean'
        } else if (Array.isArray(rawValue)) {
          fieldType = 'array'
        } else if (typeof rawValue === 'object' && rawValue !== null) {
          fieldType = 'object'
        }
        
        console.log(`[fetchNodeOutputs] 處理額外字段 ${fieldName}:`, {
          fieldType,
          rawValue,
          rawValueType: typeof rawValue
        })
        
        // 格式化值（確保返回字符串）
        let formattedValue = ''
        try {
          formattedValue = ParameterFormatter.format({
            type: fieldType,
            value: rawValue
          })
          
          console.log(`[fetchNodeOutputs] 額外字段格式化成功 ${fieldName}:`, {
            formattedValue,
            formattedType: typeof formattedValue
          })
          
          // 確保返回的是字符串
          if (typeof formattedValue !== 'string') {
            console.warn(`[fetchNodeOutputs] 額外字段格式化結果不是字符串，強制轉換: ${fieldName}`)
            formattedValue = JSON.stringify(formattedValue)
          }
        } catch (e) {
          console.error(`[fetchNodeOutputs] 格式化額外字段 ${fieldName} 失敗:`, e, 'rawValue:', rawValue)
          // 降級處理：確保返回字符串
          if (typeof rawValue === 'object' && rawValue !== null) {
            formattedValue = JSON.stringify(rawValue)
          } else {
            formattedValue = String(rawValue)
          }
          console.log(`[fetchNodeOutputs] 額外字段降級處理後 ${fieldName}:`, formattedValue)
        }
        
        return {
          name: fieldName,
          label: fieldName,
          type: fieldType,
          required: false,
          default: undefined,
          value: formattedValue,  // 確保是字符串
          rawSchema: null  // 額外字段沒有 schema
        }
      })
    
    // 合併字段列表
    node.fields = [...schemaFields, ...extraFields]

    console.log('[fetchNodeOutputs] 節點字段:', node.nodeType, node.fields)
  } catch (error) {
    console.error('獲取節點元數據失敗:', error)
    node.outputs = []
    node.fields = []
  }
}

// 解析參數字符串
function parseParams(paramsStr) {
  const params = {}
  if (!paramsStr.trim()) return params

  // 簡單的參數解析
  const paramRegex = /(\w+)\s*=\s*([^,]+)/g
  let match

  while ((match = paramRegex.exec(paramsStr)) !== null) {
    const [, key, value] = match
    params[key] = value.trim().replace(/^["']|["']$/g, '')
  }

  return params
}

// 將節點塊轉換爲註釋標記 DSL 代碼
function buildNodeBlockCode(node, idx = -1) {
  if (!node?.variable || !node?.nodeType) {
    console.warn(`[buildNodeBlockCode] 節點 ${idx} 缺少必要信息`)
    return ''
  }

  const paramParts = (node.fields || [])
    .filter(f => f.value !== undefined && f.value !== null && f.value !== '')
    .map(f => {
      let paramValue = f.value

      if (typeof paramValue === 'object' && paramValue !== null) {
        try {
          paramValue = ParameterFormatter.format({
            type: f.type || 'object',
            value: paramValue
          })
        } catch {
          paramValue = JSON.stringify(paramValue)
        }
      }

      const paramStr = String(paramValue)
      if (paramStr === '[object Object]') {
        try {
          paramValue = JSON.stringify(f.value)
        } catch {
          paramValue = '""'
        }
      }

      return `${f.name}=${paramValue}`
    })

  const callExpr = paramParts.length
    ? `${node.variable} = ${node.nodeType}(\n${paramParts.map(p => `    ${p}`).join(',\n')}\n)`
    : `${node.variable} = ${node.nodeType}()`

  const metaParts = []
  if (node.isAsync) metaParts.push('async=true')
  if (node.disabled) metaParts.push('disabled=true')
  if (node.description && String(node.description).trim()) {
    metaParts.push(`description=${JSON.stringify(String(node.description))}`)
  }

  const metaLine = `#@node(${metaParts.join(', ')})`
  return `${metaLine}
${callExpr}
#</node>`
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function parseNodeBlocksFromCode(code) {
  const normalized = String(code || '').replace(/\r\n/g, '\n')
  const lines = normalized.split('\n')
  const blocks = []

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]
    if (!line || !line.trim().startsWith('#@node')) continue

    const startLine = index
    let endLine = -1
    let variable = null

    for (let cursor = index + 1; cursor < lines.length; cursor++) {
      const current = lines[cursor]
      if (!variable) {
        const assignMatch = current.match(/^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=/)
        if (assignMatch) {
          variable = assignMatch[1]
        }
      }

      if (current.trim() === '#</node>') {
        endLine = cursor
        break
      }
    }

    if (endLine >= 0) {
      blocks.push({
        variable,
        startLine,
        endLine,
      })
      index = endLine
    }
  }

  return { lines, blocks }
}

function normalizeEditorCode(code) {
  return String(code || '')
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/\s+$/, '')
}

function updateSingleNodeCode(node) {
  const currentCode = props.modelValue || ''
  const nodeBlock = buildNodeBlockCode(node)
  if (!nodeBlock) {
    return currentCode
  }

  if (!currentCode.trim()) {
    return normalizeEditorCode(nodesToCode())
  }

  const { lines, blocks } = parseNodeBlocksFromCode(currentCode)
  const target = blocks.find(block => block.variable === node.variable)
  if (!target) {
    console.warn(`[updateSingleNodeCode] 未找到節點塊，跳過整文件重排: ${node.variable}`)
    return currentCode
  }

  const newBlockLines = String(nodeBlock).replace(/\r\n/g, '\n').split('\n')
  const newLines = [
    ...lines.slice(0, target.startLine),
    ...newBlockLines,
    ...lines.slice(target.endLine + 1),
  ]

  return normalizeEditorCode(newLines.join('\n'))
}

function removeSingleNodeCode(nodeVariable) {
  const currentCode = props.modelValue || ''
  if (!nodeVariable) {
    return currentCode
  }

  if (!currentCode.trim()) {
    return ''
  }

  const { lines, blocks } = parseNodeBlocksFromCode(currentCode)
  const target = blocks.find(block => block.variable === nodeVariable)
  if (!target) {
    console.warn(`[removeSingleNodeCode] 未找到節點塊，跳過整文件重排: ${nodeVariable}`)
    return currentCode
  }

  const newLines = [
    ...lines.slice(0, target.startLine),
    ...lines.slice(target.endLine + 1),
  ]

  return normalizeEditorCode(newLines.join('\n'))
}

function appendSingleNodeCode(node) {
  const currentCode = props.modelValue || ''
  const nodeBlock = buildNodeBlockCode(node)
  if (!nodeBlock) return currentCode || ''

  if (!currentCode.trim()) {
    return normalizeEditorCode(nodeBlock)
  }

  const trimmedEnd = currentCode.replace(/\s+$/, '')
  return normalizeEditorCode(`${trimmedEnd}\n\n${nodeBlock}`)
}

function nodesToCode() {
  const nodeBlocks = nodes.value.map((node, idx) => buildNodeBlockCode(node, idx)).filter(code => code.trim() !== '')
  
  const result = nodeBlocks.join('\n\n')
  console.log('[nodesToCode] 生成節點代碼，節點數:', nodes.value.length)
  console.log('[nodesToCode] 最終代碼:\n', result)
  return result
}

function emitCodeUpdate(newCode, options = { internal: true }) {
  const normalized = typeof newCode === 'string' ? newCode : ''
  const current = typeof props.modelValue === 'string' ? props.modelValue : ''
  if (normalized === current) {
    return false
  }

  if (options.internal !== false) {
    isInternalUpdate.value = true
  }

  emit('update:modelValue', normalized)
  return true
}

async function applyCodeUpdateSafely(newCode, options = {}) {
  const normalized = typeof newCode === 'string' ? newCode : ''
  const current = typeof props.modelValue === 'string' ? props.modelValue : ''
  if (normalized === current) {
    return true
  }

  try {
    if (props.workflowId && revisionRef.value) {
      const result = await applyWorkflowPatch(props.workflowId, {
        base_revision: revisionRef.value,
        patch_ops: [
          {
            op: 'replace_code',
            new_code: normalized,
            reason: 'node_block_editor_safe_apply',
          },
        ],
        dry_run: false,
      })

      const finalCode = typeof result?.new_code === 'string' && result.new_code.length
        ? result.new_code
        : normalized

      // 不強制每一次 UI 操作都生成“可校驗通過”的代碼。
      // 否則像“先把節點設爲 async，再補 wait 節點”的正常編輯流程會被後端拒絕寫回。
      // 處理策略：若後端校驗失敗，則僅暫存到前端本地（不更新 revision），直到下一次校驗通過再寫回。
      if (!result?.success) {
        if (result?.error === 'validate_failed') {
          const parsedNodes = await parseCodeToNodes(finalCode)
          nodes.value = parsedNodes
          emitCodeUpdate(finalCode)
          if (!options.silent) {
            ElMessage.warning('代碼校驗未通過：已暫存本地（未寫回後端），請繼續修改直至通過校驗')
          }
          return true
        }

        throw new Error(result?.error || '後端補丁應用失敗')
      }

      const parsedNodes = await parseCodeToNodes(finalCode)
      nodes.value = parsedNodes
      revisionRef.value = result.new_revision || revisionRef.value
      emit('revision-changed', revisionRef.value)
      emitCodeUpdate(finalCode)
      return true
    }

    const parsedNodes = await parseCodeToNodes(normalized)
    nodes.value = parsedNodes
    emitCodeUpdate(normalized)
    return true
  } catch (error) {
    console.error('[applyCodeUpdateSafely] 校驗失敗，拒絕寫回:', error)
    if (!options.silent) {
      ElMessage.error(`代碼更新失敗：${error?.message || error}`)
    }
    return false
  }
}

// 選擇節點
function selectNode(index) {
  selectedIndex.value = index
  emit('node-selected', nodes.value[index])
}

// 刪除節點
function deleteNode(index) {
  const removedNode = nodes.value[index]
  nodes.value.splice(index, 1)
  if (selectedIndex.value === index) {
    selectedIndex.value = -1
    emit('node-selected', null)
  } else if (selectedIndex.value > index) {
    selectedIndex.value--
  }
  
  // 觸發代碼更新
  emitCodeUpdate(removeSingleNodeCode(removedNode?.variable))
}

// 切換節點禁用狀態
async function toggleNodeDisabled(index) {
  const node = nodes.value[index]
  const targetDisabledState = node.disabled
  const previousDisabledState = !targetDisabledState
  console.log(`[toggleNodeDisabled] 節點 ${node.variable} 禁用狀態: ${targetDisabledState}`)

  // 僅更新當前節點代碼塊，避免重排整個工作流代碼格式
  const applied = await applyCodeUpdateSafely(updateSingleNodeCode(node), { silent: true })
  if (!applied) {
    node.disabled = previousDisabledState
    ElMessage.error('節點狀態更新失敗，已回滾')
    return
  }
  
  const message = targetDisabledState ? '節點已禁用' : '節點已啓用'
  ElMessage.success(message)
}

// 切換異步/同步
async function toggleAsync(index) {
  const node = nodes.value[index]
  const previousAsyncState = node.isAsync
  
  // 切換 isAsync 狀態
  node.isAsync = !node.isAsync
  
  const targetAsyncState = node.isAsync

  // 僅更新當前節點代碼塊，避免重排整個工作流代碼格式
  const newCode = updateSingleNodeCode(node)

  const applied = await applyCodeUpdateSafely(newCode, { silent: true })
  if (!applied) {
    node.isAsync = previousAsyncState
    ElMessage.error('異步狀態更新失敗，已回滾')
    return
  }
  
  const message = targetAsyncState ? '已切換爲異步節點' : '已切換爲同步節點'
  ElMessage.success(message)
}

// 顯示添加節點對話框
function showAddNodeDialog() {
  selectedNodeType.value = ''
  newNodeVariable.value = ''
  addNodeDialogVisible.value = true
}

// 添加節點
async function addNode() {
  if (!selectedNodeType.value || !newNodeVariable.value) {
    ElMessage.warning('請選擇節點類型並輸入變量名')
    return
  }

  try {
    // 生成註釋標記 DSL 節點代碼
    const code = `#@node()
${newNodeVariable.value} = ${selectedNodeType.value}()
#</node>`
    
    console.log('[addNode] 生成的節點代碼:\n', code)
    
    const parsed = await parseCodeToNodes(code)

    if (parsed && parsed.length > 0) {
      console.log('[addNode] 解析後的節點:', parsed[0])
      
      nodes.value.push(parsed[0])
      
      const finalCode = appendSingleNodeCode(parsed[0])
      console.log('[addNode] 最終生成的代碼:\n', finalCode)
      
      emitCodeUpdate(finalCode)
      selectedIndex.value = nodes.value.length - 1
      emit('node-selected', nodes.value[selectedIndex.value])
      ElMessage.success('節點已添加')
    } else {
      ElMessage.error('節點添加失敗：代碼解析失敗')
    }
  } catch (error) {
    console.error('[addNode] 添加節點失敗:', error)
    ElMessage.error(`節點添加失敗：${error.message || error}`)
  }

  addNodeDialogVisible.value = false
}

// 開始編輯參數
function startParamEdit(nodeIndex, fieldIndex) {
  const node = nodes.value[nodeIndex]
  const field = node.fields[fieldIndex]
  
  console.log('[startParamEdit] 開始編輯:', { nodeIndex, fieldIndex, field })
  
  // 獲取當前值，去掉引號和 $ 前綴
  let editValue = field.value
  if (editValue === undefined || editValue === null) {
    editValue = field.default || (field.type === 'boolean' ? false : '')
  }
  
  console.log('[startParamEdit] 原始值:', { 
    fieldName: field.name, 
    fieldType: field.type, 
    editValue, 
    isArray: Array.isArray(editValue),
    valueType: typeof editValue
  })
  
  // 處理布爾值
  if (field.type === 'boolean') {
    // 將字符串 "True"/"False" 轉換爲布爾值
    if (typeof editValue === 'string') {
      editValue = editValue === 'True' || editValue === 'true'
    }
  }
  // 處理數組類型
  else if (field.type === 'array') {
    // 先去掉外層的引號（如果有）
    if (typeof editValue === 'string') {
      if ((editValue.startsWith('"') && editValue.endsWith('"')) || 
          (editValue.startsWith("'") && editValue.endsWith("'"))) {
        editValue = editValue.substring(1, editValue.length - 1)
        console.log('[startParamEdit] 去掉外層引號後:', editValue)
      }
    }
    
    // 將數組轉換爲可編輯的數組項
    let arrayItems = []
    if (Array.isArray(editValue)) {
      arrayItems = editValue.map(item => {
        // 去掉字符串的引號
        const str = String(item)
        if ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'"))) {
          return str.substring(1, str.length - 1)
        }
        return str
      })
    }
    // 如果是字符串形式的數組 ["A1", "A2"]，解析它
    else if (typeof editValue === 'string' && editValue.startsWith('[') && editValue.endsWith(']')) {
      try {
        // 先嚐試 JSON 解析
        const parsed = JSON.parse(editValue.replace(/'/g, '"'))
        arrayItems = parsed.map(item => {
          const str = String(item)
          // 去掉引號
          if ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'"))) {
            return str.substring(1, str.length - 1)
          }
          return str
        })
      } catch (e) {
        // 解析失敗，手動分割
        const content = editValue.substring(1, editValue.length - 1) // 去掉 [ ]
        arrayItems = content.split(',').map(s => {
          const trimmed = s.trim()
          // 去掉引號
          if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
            return trimmed.substring(1, trimmed.length - 1)
          }
          return trimmed
        }).filter(item => item)
      }
    }
    // 如果是逗號分隔的字符串
    else if (typeof editValue === 'string' && editValue.includes(',')) {
      arrayItems = editValue.split(',').map(s => s.trim()).filter(item => item)
    }
    // 單個值
    else if (editValue) {
      arrayItems = [String(editValue)]
    }
    
    console.log('[startParamEdit] 數組解析結果:', arrayItems)
    
    // 保存到 editingParam
    editValue = arrayItems
  }
  // 如果是字符串類型且有引號，去掉引號
  else if (typeof editValue === 'string' && field.type === 'string') {
    if ((editValue.startsWith('"') && editValue.endsWith('"')) || 
        (editValue.startsWith("'") && editValue.endsWith("'"))) {
      editValue = editValue.substring(1, editValue.length - 1)
    }
  }
  
  editingParam.value = {
    nodeIndex,
    fieldIndex,
    fieldName: field.name,
    fieldType: field.type,
    value: field.type === 'array' ? null : editValue,  // 數組類型不使用 value
    arrayItems: field.type === 'array' ? editValue : []  // 數組類型使用 arrayItems
  }
  
  console.log('[startParamEdit] 編輯狀態:', editingParam.value)
}

// 添加數組項
function addArrayItem() {
  if (!editingParam.value || !editingParam.value.arrayItems) return
  editingParam.value.arrayItems.push('')
}

// 刪除數組項
function removeArrayItem(index) {
  if (!editingParam.value || !editingParam.value.arrayItems) return
  editingParam.value.arrayItems.splice(index, 1)
}

// 保存參數編輯
async function saveParamEdit() {
  if (!editingParam.value) return
  
  const { nodeIndex, fieldIndex, fieldName, value, arrayItems } = editingParam.value
  const node = nodes.value[nodeIndex]
  
  if (!node || !node.fields || !node.fields[fieldIndex]) {
    console.error('[saveParamEdit] 節點或字段不存在:', { nodeIndex, fieldIndex })
    ElMessage.error('保存失敗：節點數據異常')
    editingParam.value = null
    return
  }
  
  const field = node.fields[fieldIndex]
  const fieldType = field.type || editingParam.value.fieldType || 'string'
  const previousFieldValue = field.value
  
  console.log('[saveParamEdit] 保存參數:', { 
    nodeIndex, 
    fieldIndex, 
    fieldName, 
    fieldType, 
    value,
    node: {
      variable: node.variable,
      nodeType: node.nodeType,
      fieldsCount: node.fields.length
    }
  })
  
  try {
    // 處理數組類型
    let finalValue = value
    if (fieldType === 'array' && arrayItems) {
      // 過濾掉空項
      const filteredItems = arrayItems.filter(item => item && item.trim())
      finalValue = filteredItems
      console.log('[saveParamEdit] 數組項:', filteredItems)
    }
    
    // 使用 ParameterFormatter 處理空值
    if (ParameterFormatter.isEmpty(finalValue)) {
      console.log('[saveParamEdit] 值爲空，清除字段值')
      field.value = undefined
      
      // 重新生成節點代碼（不包含該字段）
      const allCode = updateSingleNodeCode(node)
      console.log('[saveParamEdit] 完整代碼:\n', allCode)
      const applied = await applyCodeUpdateSafely(allCode, { silent: true })
      if (!applied) {
        field.value = previousFieldValue
        ElMessage.error('參數清除失敗，已回滾')
        editingParam.value = null
        return
      }
      ElMessage.success('參數已清除')
      
      editingParam.value = null
      return
    }
    
    // 使用 ParameterFormatter 格式化值
    const formattedValue = ParameterFormatter.format({
      type: fieldType,
      value: finalValue
    })

    console.log('[saveParamEdit] 格式化後的值:', formattedValue)

    if (String(formattedValue) === String(field.value ?? '')) {
      editingParam.value = null
      return
    }

    // 更新字段值
    field.value = formattedValue
    
    console.log('[saveParamEdit] 當前所有節點:')
    nodes.value.forEach((n, idx) => {
      console.log(`  [${idx}] ${n.variable}: fields=`, n.fields?.map(f => `${f.name}=${f.value}`))
    })
    
    // 重新生成節點代碼
    const allCode = updateSingleNodeCode(node)
    console.log('[saveParamEdit] 完整節點代碼:\n', allCode)
    
    // 驗證生成的代碼是否有效
    if (!allCode || allCode.trim() === '') {
      throw new Error('生成的代碼爲空')
    }
    
    const applied = await applyCodeUpdateSafely(allCode, { silent: true })
    if (!applied) {
      field.value = previousFieldValue
      ElMessage.error('參數更新失敗，已回滾')
      editingParam.value = null
      return
    }
    ElMessage.success('參數已更新')
    
    editingParam.value = null
  } catch (error) {
    console.error('[saveParamEdit] 保存參數失敗:', error)
    ElMessage.error(`保存失敗：${error.message}`)
    editingParam.value = null
  }
}


// 打開文件夾選擇對話框
async function openFolderDialog() {
  try {
    const result = await window.electron.ipcRenderer.invoke('dialog:openDirectory')
    if (result && !result.canceled && result.filePaths.length > 0) {
      if (editingParam.value) {
        const path = result.filePaths[0]
        // 轉義 Windows 路徑反斜槓
        editingParam.value.value = path.replace(/\\/g, '\\\\')
        // 自動保存
        saveParamEdit()
      }
    }
  } catch (e) {
    console.error('Failed to open directory dialog:', e)
  }
}

// 顯示可用參數（當節點沒有參數時）
function showAvailableParams(nodeIndex) {
  const node = nodes.value[nodeIndex]
  if (!node.fields || node.fields.length === 0) {
    ElMessage.info('該節點沒有可配置的參數')
    return
  }
  
  // 爲所有必填字段添加空值
  node.fields.forEach(field => {
    if (field.required && !field.value) {
      field.value = field.default || ''
    }
  })
  
  // 觸發更新
  emitCodeUpdate(updateSingleNodeCode(node))
}

// 格式化參數值
function formatParamValue(value) {
  // 處理空值
  if (value === undefined || value === null || value === '') {
    return '(未設置)'
  }
  
  // 轉換爲字符串
  const strValue = String(value)
  
  // 截斷過長的字符串
  if (strValue.length > 50) {
    return strValue.substring(0, 50) + '...'
  }
  
  return strValue
}

// 獲取節點分類顏色
function getNodeCategoryColor(category) {
  const colors = {
    'Logic': 'primary',
    'Novel': 'success',
    'Card': 'warning',
    'AI': 'danger',
    'Prompt': 'info'
  }
  return colors[category] || 'info'
}

// 獲取狀態文本
function getStatusText(status) {
  const texts = {
    'running': '運行中',
    'completed': '已完成',
    'error': '失敗'
  }
  return texts[status] || ''
}

// 加載節點類型
async function loadNodeTypes() {
  try {
    const response = await request.get('/nodes/types', undefined, '/api', { showLoading: false })
    nodeTypes.value = response.node_types || []
  } catch (error) {
    console.error('加載節點類型失敗:', error)
  }
}

// 監聽代碼變化
watch(() => props.modelValue, async (newCode, oldCode) => {
  if (newCode === oldCode) {
    return
  }

  // 如果是內部更新（saveParamEdit/saveVariableEdit 觸發），跳過重新解析
  if (isInternalUpdate.value) {
    console.log('[watch] 內部更新，跳過重新解析')
    isInternalUpdate.value = false
    return
  }
  
  console.log('[watch] 外部代碼變化，重新解析')
  console.log('[watch] 新代碼長度:', newCode?.length, '舊代碼長度:', oldCode?.length)
  console.log('[watch] 新代碼:\n', newCode)

  const requestSeq = ++parseWatchSeq.value
  
  try {
    const parsedNodes = await parseCodeToNodes(newCode)
    if (requestSeq !== parseWatchSeq.value) {
      return
    }
    console.log('[watch] 解析成功，節點數:', parsedNodes.length)
    nodes.value = parsedNodes
  } catch (error) {
    if (requestSeq !== parseWatchSeq.value) {
      return
    }
    console.error('[watch] 代碼解析失敗:', error)
    console.error('[watch] 失敗的代碼:\n', newCode)
    // 解析失敗時保持當前節點列表不變
    // 只有在非初始化時才顯示錯誤提示（避免組件掛載時的錯誤提示）
    if (oldCode !== undefined) {
      ElMessage.error(`代碼解析失敗：${error.message || error}`)
    }
  }
}, { immediate: true })

// 更新變量列表（從現有節點中提取）
function updateVariableList() {
  const vars = []
  nodes.value.forEach(node => {
     if (node.variable) {
        vars.push({
           value: node.variable,
           label: node.variable,
           type: 'variable'
        })
        // 如果有輸出字段，我也加進去? 還是隻加根變量?
        // 暫只加根變量
     }
  })
  variableList.value = vars
}

// 判斷字段是否需要智能選擇器（基於 x-component）
function isSmartSelectorField(field) {
  if (!field || !field.rawSchema) return false
  const xComponent = field.rawSchema['x-component']
  return ['ProjectSelect', 'LLMSelect', 'PromptSelect', 'CardTypeSelect', 'ResponseModelSelect', 'ToolMultiSelect'].includes(xComponent)
}

function getProjectOptionValue(field, project) {
  if (field?.name === 'project_name') {
    return project?.name ?? ''
  }
  return project?.id
}

function getLlmOptionValue(field, llmConfig) {
  if (field?.name === 'llm_name') {
    return llmConfig?.display_name || llmConfig?.model_name || ''
  }
  return llmConfig?.id
}

// 切換節點摺疊狀態
function toggleNodeCollapse(index) {
  const node = nodes.value[index]
  node.collapsed = !node.collapsed
}

// 開始編輯變量名
function startVariableEdit(nodeIndex, currentVariable) {
  console.log('[startVariableEdit] 開始編輯變量名:', { nodeIndex, currentVariable })
  
  editingVariable.value = {
    nodeIndex,
    value: currentVariable,
    originalValue: currentVariable
  }
  
  nextTick(() => {
    if (variableInputRef.value) {
      variableInputRef.value.focus()
      variableInputRef.value.select()
    }
  })
}

// 保存變量名編輯
async function saveVariableEdit() {
  console.log('[saveVariableEdit] 函數被調用')
  console.log('[saveVariableEdit] editingVariable:', editingVariable.value)
  
  if (!editingVariable.value) {
    console.log('[saveVariableEdit] editingVariable 爲空，退出')
    return
  }
  
  const { nodeIndex, value, originalValue } = editingVariable.value
  const newVariable = value.trim()
  
  console.log('[saveVariableEdit] 保存變量名:', { nodeIndex, newVariable, originalValue })
  
  // 驗證變量名
  if (!newVariable) {
    ElMessage.error('變量名不能爲空')
    editingVariable.value = null
    return
  }
  
  // 驗證變量名格式
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(newVariable)) {
    ElMessage.error('變量名只能包含字母、數字、下劃線，且不能以數字開頭')
    editingVariable.value = null
    return
  }
  
  // 檢查是否與其他節點重名
  const isDuplicate = nodes.value.some((n, idx) => idx !== nodeIndex && n.variable === newVariable)
  if (isDuplicate) {
    ElMessage.error(`變量名 "${newVariable}" 已被使用`)
    editingVariable.value = null
    return
  }
  
  // 如果沒有變化，直接返回
  if (newVariable === originalValue) {
    editingVariable.value = null
    return
  }
  
  console.log('[saveVariableEdit] 開始更新變量名和引用...')
  
  const allCode = props.modelValue || nodesToCode()
  console.log('[saveVariableEdit] 原始代碼:\n', allCode)
  
  try {
    // 調用後端 API 進行變量重命名
    console.log('[saveVariableEdit] 準備調用後端 API...')
    console.log('[saveVariableEdit] 請求參數:', {
      code: allCode,
      old_name: originalValue,
      new_name: newVariable
    })
    
    const response = await request.post('/workflows/rename-variable', {
      code: allCode,
      old_name: originalValue,
      new_name: newVariable
    }, '/api')
    
    console.log('[saveVariableEdit] 收到響應:', response)
    
    if (response.success && response.new_code) {
      console.log('[saveVariableEdit] 新代碼:\n', response.new_code)
      
      // 發送更新事件
      emitCodeUpdate(response.new_code)
      
      // 強制重新解析代碼以更新顯示
      try {
        nodes.value = await parseCodeToNodes(response.new_code)
        console.log('[saveVariableEdit] 節點已重新解析')
      } catch (error) {
        console.error('[saveVariableEdit] 重新解析失敗:', error)
      }
      
      ElMessage.success(`變量名已更新：${originalValue} → ${newVariable}`)
    } else {
      console.error('[saveVariableEdit] 重命名失敗:', response.error)
      ElMessage.error(`重命名失敗：${response.error || '未知錯誤'}`)
    }
  } catch (error) {
    console.error('[saveVariableEdit] 重命名請求失敗:', error)
    ElMessage.error(`重命名失敗：${error.message || error}`)
  }
  
  editingVariable.value = null
}

// 取消變量名編輯
function cancelVariableEdit() {
  editingVariable.value = null
}

// 格式化顯示值（去掉引號和 $ 前綴）
function formatDisplayValue(field) {
  if (ParameterFormatter.isEmpty(field.value)) {
    return field.default || '(未設置)'
  }
  
  // 使用 ParameterFormatter 解析顯示值
  let displayValue = ParameterFormatter.parseDisplayValue(field.value)
  
  // 對於智能選擇器，顯示對應的名稱而不是 ID
  const xComponent = field.rawSchema?.['x-component']
  
  if (xComponent === 'ProjectSelect') {
    // 顯示項目名稱
    const projectId = parseInt(displayValue)
    const project = projectList.value.find(p => p.id === projectId)
    if (project) {
      displayValue = project.name
    }
  } else if (xComponent === 'LLMSelect') {
    // 顯示 LLM 配置名稱
    const llmConfigId = parseInt(displayValue)
    const llmConfig = llmConfigList.value.find(cfg => cfg.id === llmConfigId)
    if (llmConfig) {
      displayValue = llmConfig.display_name || llmConfig.model_name || `LLM #${llmConfigId}`
    }
  } else if (xComponent === 'PromptSelect') {
    // 顯示提示詞名稱
    const promptId = parseInt(displayValue)
    const prompt = promptList.value.find(p => p.id === promptId)
    if (prompt) {
      displayValue = prompt.name
    }
  }
  
  // CodeEditor / Textarea 不截斷，保留多行展示
  if (xComponent === 'CodeEditor' || xComponent === 'Textarea') {
    return displayValue
  }

  // 其他字段截斷過長的值
  return displayValue.length > 50 ? displayValue.substring(0, 50) + '...' : displayValue
}

function resolveFieldType(fieldDef) {
  if (!fieldDef || typeof fieldDef !== 'object') {
    return 'string'
  }

  if (typeof fieldDef.type === 'string' && fieldDef.type.trim()) {
    return fieldDef.type
  }

  if (Array.isArray(fieldDef.type)) {
    const picked = fieldDef.type.find(t => typeof t === 'string' && t !== 'null')
    if (picked) return picked
  }

  if (Array.isArray(fieldDef.anyOf)) {
    const picked = fieldDef.anyOf
      .map(item => item?.type)
      .find(t => typeof t === 'string' && t !== 'null')
    if (picked) return picked
  }

  if (Array.isArray(fieldDef.oneOf)) {
    const picked = fieldDef.oneOf
      .map(item => item?.type)
      .find(t => typeof t === 'string' && t !== 'null')
    if (picked) return picked
  }

  return 'string'
}

// 組件掛載時加載節點類型和數據
onMounted(async () => {
  loadNodeTypes()

  // 使用 stores 加載數據
  try {
    await Promise.all([
      projectListStore.fetchProjects(),
      llmConfigStore.fetchLLMConfigs(),
      promptStore.fetchPrompts(),
      cardStore.fetchInitialData() // 這會加載 cardTypes
    ])

    try {
      builtinResponseModels.value = await getContentModels()
    } catch (e) {
      console.warn('[NodeBlockEditor] 加載內置響應模型失敗，使用回退列表', e)
      builtinResponseModels.value = [
        'OneSentence',
        'ChapterOutline',
        'VolumeOutline',
        'WorldBuilding',
        'WritingGuide',
        'ParagraphOverview',
        'BookStageChunkPlan',
        'BookStageFinalPlan'
      ]
    }

    // 調試日誌
    console.log('[NodeBlockEditor] 數據加載完成:')
    console.log('  - 項目列表:', projectList.value.length, '個')
    console.log('  - LLM配置:', llmConfigList.value.length, '個')
    console.log('  - 提示詞:', promptList.value.length, '個')
    console.log('  - 卡片類型:', cardTypeList.value.length, '個')
    console.log('  - 內置響應模型:', builtinResponseModels.value.length, '個')
  } catch (error) {
    console.error('加載數據失敗:', error)
  }
})
</script>

<style scoped>
.node-block-editor {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color-page);
}

.node-blocks {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.node-block {
  margin-bottom: 12px;
  padding: 16px;
  background: var(--el-bg-color);
  border: 2px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.node-block:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 12px var(--el-box-shadow-light);
}

.node-block.is-selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.node-block.is-disabled {
  opacity: 0.5;
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color-light);
  position: relative;
}

.node-block.is-disabled::before {
  content: '已禁用';
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 2px 8px;
  background: var(--el-text-color-secondary);
  color: white;
  font-size: 12px;
  border-radius: 4px;
  z-index: 1;
}

.node-block.is-disabled:hover {
  border-color: var(--el-border-color);
  box-shadow: none;
}

.node-block.is-disabled .node-variable,
.node-block.is-disabled .node-type,
.node-block.is-disabled .param-label,
.node-block.is-disabled .param-value {
  color: var(--el-text-color-secondary);
}

.node-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.node-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.node-variable {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.node-type {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.node-description {
  margin: -4px 0 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
  border-left: 3px solid var(--el-color-primary-light-5);
}

.node-actions {
  display: flex;
  gap: 4px;
}

.node-params {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 13px;
  margin-bottom: 8px;
}

.params-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.params-title {
  font-weight: 600;
  color: var(--el-text-color-regular);
  font-size: 12px;
  text-transform: uppercase;
}

.param-item {
  display: flex;
  gap: 8px;
}

.param-key {
  color: var(--el-text-color-secondary);
  min-width: 120px;
}


.param-value-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
}

.param-value {
  color: var(--el-text-color-primary);
  flex: 1;
  word-break: break-all;
}

.param-value.editable {
  cursor: text;
  border-bottom: 1px dashed transparent;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.param-value.editable:hover {
  background-color: var(--el-color-primary-light-9);
  border-bottom-color: var(--el-color-primary);
  padding-left: 4px;
  border-radius: 2px;
}

.edit-icon {
  display: none;
  font-size: 12px;
  color: var(--el-color-primary);
}

.param-value.editable:hover .edit-icon {
  display: inline-flex;
}

.code-expression-input :deep(.el-textarea__inner),
.param-code-preview :deep(.el-textarea__inner) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Monaco', 'Menlo', 'Courier New', monospace;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.param-code-preview {
  width: 100%;
}

.param-code-preview :deep(.el-textarea__inner) {
  cursor: text;
  background-color: var(--el-fill-color-lighter);
}

.param-code-preview:hover :deep(.el-textarea__inner) {
  border-color: var(--el-color-primary);
}

.add-param-hint {
  padding: 8px 0;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.add-param-hint .el-button {
  color: var(--el-color-primary);
}

.node-outputs {
  padding: 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  margin-top: 8px;
}

.outputs-title {
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
  font-size: 12px;
  text-transform: uppercase;
}

.output-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.output-tag {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  cursor: pointer;
}

.output-tag:hover {
  opacity: 0.8;
}

.node-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
}

.status-running {
  background: var(--el-color-info-light-9);
  color: var(--el-color-info);
}

.status-completed {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.status-error {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.add-node-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  background: var(--el-bg-color);
  border: 2px dashed var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  transition: all 0.3s;
}

.add-node-block:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
</style>
