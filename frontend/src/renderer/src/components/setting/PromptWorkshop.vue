<template>
  <div class="prompt-workshop">
    <div class="toolbar">
      <h2>提示詞工坊</h2>
      <el-button type="primary" @click="handleCreate">新建提示詞</el-button>
    </div>
    <el-table :data="prompts" style="width: 100%" v-loading="loading">
      <el-table-column prop="name" label="名稱" width="180" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" @click="handleEdit(row)">編輯</el-button>
          <el-popconfirm title="刪除該提示詞？" @confirm="handleDelete(row.id)" v-if="!isBuiltInPrompt(row)">
            <template #reference>
              <el-button size="small" type="danger" :disabled="isBuiltInPrompt(row)">刪除</el-button>
            </template>
          </el-popconfirm>
          <el-button v-else size="small" type="danger" plain disabled>刪除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 抽屜編輯器 -->
    <el-drawer v-model="drawerVisible" :title="dialogTitle" size="60%" append-to-body>
      <el-form :model="currentPrompt" label-width="90px" ref="promptForm" class="form-grid">
        <el-form-item label="名稱" prop="name" :rules="{ required: true, message: '請輸入名稱', trigger: 'blur' }">
          <el-input v-model="currentPrompt.name" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="currentPrompt.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="結構化編輯">
          <el-switch v-model="useStructured" />
          <span class="hint">（開啓後按 Role/Skills/Goals/Knowledge/OutputFormat 分區編輯，儲存時會自動組合模板並寫入資料庫）</span>
        </el-form-item>

        <!-- 結構化編輯模式 -->
        <template v-if="useStructured">
          <el-divider content-position="left">Role</el-divider>
          <el-input v-model="structured.role" placeholder="如：小說創作助手" />

          <el-divider content-position="left">Skills</el-divider>
          <el-input v-model="structured.skills" type="textarea" :rows="2" placeholder="可寫要點，換行分隔" />

          <el-divider content-position="left">Goals</el-divider>
          <el-input v-model="structured.goals" type="textarea" :rows="4" placeholder="每行一個目標，或用序號/短句" />

          <el-divider content-position="left">Knowledge（可選）</el-divider>
          <div class="knowledge-grid">
            <div class="row">
              <span class="label">引用方式：</span>
              <el-radio-group v-model="knowledgeMode" size="small">
                <el-radio-button label="id">按ID</el-radio-button>
                <el-radio-button label="name">按名稱</el-radio-button>
              </el-radio-group>
              <span class="hint" style="margin-left:8px">將插入 @KB{ id=... } 或 @KB{ name=... }，生成時後端會動態注入最新內容</span>
            </div>
            <el-select v-model="selectedKnowledgeIds" multiple filterable placeholder="選擇要引用的知識庫（可多選）" style="width:100%">
              <el-option v-for="kb in knowledgeItems" :key="kb.id" :label="kb.name" :value="kb.id" />
            </el-select>
          </div>

          <el-divider content-position="left">OutputFormat（可選）</el-divider>
          <el-input v-model="structured.outputFormat" type="textarea" :rows="2" placeholder="預設：請嚴格根據提供的Json Schema返回結果" />

          <el-divider content-position="left">預覽</el-divider>
          <el-input :model-value="composedTemplate" type="textarea" :rows="10" readonly />
        </template>

        <!-- 原始模板模式 -->
        <template v-else>
          <el-form-item label="模板" prop="template" :rules="{ required: true, message: '請輸入模板內容', trigger: 'blur' }">
            <el-input v-model="currentPrompt.template" type="textarea" :rows="14" />
            <div class="template-hint">使用 <code>${variable}</code> 的形式來定義佔位符，例如 <code>${text_content}</code>。</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave" :loading="saving">儲存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { listKnowledge, type Knowledge, listPrompts, createPrompt, updatePrompt, deletePrompt } from '@renderer/api/setting'

interface Prompt {
  id: number
  name: string
  description: string
  template: string
  built_in?: boolean
}

const DEFAULT_OUTPUT_FORMAT = '請嚴格根據提供的Json Schema返回結果'

const prompts = ref<Prompt[]>([])
const loading = ref(false)
const drawerVisible = ref(false)
const saving = ref(false)
const currentPrompt = ref<Partial<Prompt>>({})
const promptForm = ref<FormInstance>()

const dialogTitle = computed(() => (currentPrompt.value.id ? '編輯提示詞' : '新建提示詞'))

const isBuiltInPrompt = (row: Prompt) => !!row.built_in

// 結構化編輯相關
const useStructured = ref(false)
const structured = ref({ role: '', skills: '', goals: '', knowledge: '', outputFormat: DEFAULT_OUTPUT_FORMAT })

// 知識庫選擇與模式
const knowledgeItems = ref<Knowledge[]>([])
const selectedKnowledgeIds = ref<number[]>([])
const knowledgeMode = ref<'id' | 'name'>('name')

// 組合預覽
const composedTemplate = computed(() => composeTemplate(structured.value))

function composeTemplate(s: { role: string; skills: string; goals: string; knowledge?: string; outputFormat?: string }) {
  const lines: string[] = []
  if (s.role?.trim()) lines.push(`- Role: ${s.role.trim()}`)
  if (s.skills?.trim()) lines.push(`- Skills: ${s.skills.trim()}`)
  if (s.goals?.trim()) {
    lines.push('- Goals:')
    // 將多行 goals 做縮進
    const gl = s.goals.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
    for (const g of gl) lines.push(`    - ${g}`)
  }
  // 知識庫佔位符引用
  if (selectedKnowledgeIds.value.length) {
    lines.push('\n- knowledge:')
    for (const kid of selectedKnowledgeIds.value) {
      const item = knowledgeItems.value.find(k => k.id === kid)
      if (!item) continue
      if (knowledgeMode.value === 'id') {
        lines.push(`    - @KB{ id=${kid} }  # ${item.name}`)
      } else {
        lines.push(`    - @KB{ name=${item.name} }`)
      }
    }
  }
  if (s.outputFormat?.trim()) lines.push(`\n- OutputFormat: ${s.outputFormat.trim()}`)
  return lines.join('\n')
}

async function fetchPrompts() {
  loading.value = true
  try {
    prompts.value = await listPrompts()
  } catch (error) {
    ElMessage.error('載入提示詞列表失敗')
  } finally {
    loading.value = false
  }
}

async function fetchKnowledgeList() {
  try {
    knowledgeItems.value = await listKnowledge()
  } catch {
    knowledgeItems.value = []
  }
}

function resetStructuredDefaults() {
  structured.value = { role: '', skills: '', goals: '', knowledge: '', outputFormat: DEFAULT_OUTPUT_FORMAT }
  selectedKnowledgeIds.value = []
  knowledgeMode.value = 'name'
}

function handleCreate() {
  currentPrompt.value = { name: '', description: '', template: '' }
  resetStructuredDefaults()
  useStructured.value = false
  drawerVisible.value = true
}

function parseKnowledgeBlock(tpl: string) {
  // 提取 knowledge 區塊
  const k = /-\s*knowledge:\s*([\s\S]*?)(?:\n-\s*OutputFormat\s*[:：]|$)/i.exec(tpl)
  const ids: number[] = []
  let mode: 'id' | 'name' = 'name'
  if (k && k[1]) {
    const block = k[1]
    const idReg = /@KB\{\s*id\s*=\s*(\d+)\s*\}/gi
    const nameReg = /@KB\{\s*name\s*=\s*([^}]+)\}/gi
    let m: RegExpExecArray | null
    while ((m = idReg.exec(block))) {
      const id = Number(m[1])
      if (!Number.isNaN(id)) ids.push(id)
    }
    if (!ids.length) {
      const names: string[] = []
      while ((m = nameReg.exec(block))) {
        const n = (m[1] || '').trim().replace(/^['"]|['"]$/g, '')
        if (n) names.push(n)
      }
      if (names.length) {
        mode = 'name'
        for (const n of names) {
          const found = knowledgeItems.value.find(kb => kb.name === n)
          if (found) ids.push(found.id)
        }
      }
    } else {
      mode = 'id'
    }
  }
  selectedKnowledgeIds.value = Array.from(new Set(ids))
  knowledgeMode.value = mode
}

async function tryParseStructured(tpl?: string) {
  if (!tpl) return resetStructuredDefaults()
  // 粗略解析，僅在常見格式時填充字段，解析失敗保持預設
  try {
    const r = /-\s*Role:\s*(.*)/i.exec(tpl)
    const s = /-\s*Skills?:\s*([\s\S]*?)(?:\n-\s*Goals?:|\n-\s*knowledge:|\n-\s*OutputFormat\s*[:：]|$)/i.exec(tpl)
    const g = /-\s*Goals?:\s*([\s\S]*?)(?:\n-\s*knowledge:|\n-\s*OutputFormat\s*[:：]|$)/i.exec(tpl)
    const o = /-\s*OutputFormat\s*[:：]\s*([\s\S]*)/i.exec(tpl)
    structured.value.role = r?.[1]?.trim() || ''
    structured.value.skills = (s?.[1] || '').trim()
    structured.value.goals = (g?.[1] || '').replace(/^\s*-\s*/gm, '').trim()
    structured.value.outputFormat = (o?.[1] || DEFAULT_OUTPUT_FORMAT).trim()
    // 解析知識庫引用
    parseKnowledgeBlock(tpl)
  } catch {
    resetStructuredDefaults()
  }
}

async function handleEdit(prompt: any) {
  currentPrompt.value = { ...prompt }
  await fetchKnowledgeList()
  // 嘗試解析爲結構化表單，若失敗則回退到原始模板模式
  await tryParseStructured(prompt.template)
  useStructured.value = false
  drawerVisible.value = true
}

async function handleSave() {
  if (!promptForm.value) return
  await promptForm.value.validate(async (valid) => {
    if (valid) {
      saving.value = true
      try {
        const payload: any = { ...currentPrompt.value }
        // 若是結構化編輯，則組合模板寫回
        if (useStructured.value) {
          payload.template = composeTemplate(structured.value)
        }
        if (payload.id) {
          await updatePrompt(payload.id, payload)
        } else {
          await createPrompt(payload)
        }
        ElMessage.success('儲存成功')
        drawerVisible.value = false
        fetchPrompts()
      } catch (error) {
        ElMessage.error('儲存失敗')
      } finally {
        saving.value = false
      }
    }
  })
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('確定要刪除這個提示詞嗎？', '警告', {
      confirmButtonText: '確定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deletePrompt(id)
    ElMessage.success('刪除成功')
    fetchPrompts()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('刪除失敗')
    }
  }
}

onMounted(async () => { await fetchKnowledgeList(); await fetchPrompts() })
</script>

<style scoped>
.prompt-workshop { padding: 20px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.form-grid { display: flex; flex-direction: column; gap: 8px; }
.hint { color: var(--el-text-color-secondary); margin-left: 8px; font-size: 12px; }
.template-hint { font-size: 12px; color: #909399; margin-top: 5px; }
.drawer-footer { display: flex; justify-content: flex-end; gap: 8px; }
.knowledge-grid { display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 8px; }
.label { color: var(--el-text-color-regular); }
</style> 
