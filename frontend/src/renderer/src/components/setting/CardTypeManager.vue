<template>
  <div class="card-type-manager">
    <!-- 工具條：搜索 + 新增 -->
    <div class="toolbar">
      <el-input v-model="query" placeholder="搜索類型（名稱/描述）" clearable class="search" />
      <el-button type="primary" @click="openEditor()">新增類型</el-button>
    </div>

    <!-- 列表 -->
    <el-table :data="filteredTypes" height="60vh" size="small" :border="false" v-loading="loading">
      <el-table-column prop="name" label="名稱" width="220" />
      <el-table-column prop="description" label="描述" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ (row.description && String(row.description).trim()) ? row.description : '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="AI" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_ai_enabled ? 'success' : 'info'">{{ row.is_ai_enabled ? '啓用' : '關閉' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" align="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditor(row)">編輯</el-button>
          <el-button size="small" type="primary" plain @click="openSchemaStudio(row)">編輯結構</el-button>
          <template v-if="!isBuiltInCardType(row)">
            <el-popconfirm title="刪除該類型？（若有引用將影響創建操作）" @confirm="removeType(row)">
              <template #reference>
                <el-button size="small" type="danger" plain>刪除</el-button>
              </template>
            </el-popconfirm>
          </template>
          <el-button v-else size="small" type="danger" plain disabled>刪除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 編輯抽屜：基礎信息 + 結構編輯入口 -->
    <el-drawer v-model="drawer.visible" :title="drawer.editing ? '編輯卡片類型' : '新增卡片類型'" size="60%">
      <div class="editor-grid">
        <el-form label-position="top" :model="form">
          <el-form-item label="名稱"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="是否啓用AI"><el-switch v-model="form.is_ai_enabled" /></el-form-item>
          <el-form-item label="是否單例"><el-switch v-model="form.is_singleton" /></el-form-item>
          <el-form-item label="默認上下文模板"><el-input v-model="form.default_ai_context_template" type="textarea" :rows="4" /></el-form-item>

          <template v-if="form.is_ai_enabled">
            <div class="ai-section-title">AI 參數</div>
            <el-form-item label="模型（LLM 配置）">
              <el-select v-model="aiParams.llm_config_id" filterable placeholder="選擇模型" style="width:100%">
                <el-option v-for="c in llmConfigs" :key="c.id" :label="c.display_name || (c.provider + ':' + c.model_name)" :value="c.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="提示詞">
              <el-select v-model="aiParams.prompt_name" filterable placeholder="選擇提示詞" style="width:100%">
                <el-option v-for="p in prompts" :key="p.name" :label="p.name" :value="p.name" />
              </el-select>
            </el-form-item>
            <div class="ai-grid">
              <el-form-item label="溫度">
                <el-input-number v-model="aiParams.temperature" :min="0" :max="2" :step="0.1" controls-position="right" style="width:100%" />
              </el-form-item>
              <el-form-item label="最大 tokens">
                <el-input-number v-model="aiParams.max_tokens" :min="1" :step="128" controls-position="right" style="width:100%" />
              </el-form-item>
              <el-form-item label="超時 (秒)">
                <el-input-number v-model="aiParams.timeout" :min="1" :max="600" :step="5" controls-position="right" style="width:100%" />
              </el-form-item>
            </div>
          </template>

          <el-form-item label="UI 佈局（可選）">
            <el-input v-model="uiLayoutText" type="textarea" :rows="6" placeholder='{ "sections": [ ... ] }' />
          </el-form-item>
        </el-form>
        <div class="mt-2">
          <el-button type="primary" plain @click="openSchemaEditor">編輯結構（Schema）</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="drawer.visible=false">取消</el-button>
        <el-button type="primary" @click="saveType">保存</el-button>
      </template>
    </el-drawer>

    <SchemaStudio v-model:visible="studio.visible" :mode="'type'" :target-id="studio.typeId" :context-title="studio.typeName" @saved="onStudioSaved" />


  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { useCardStore } from '@renderer/stores/useCardStore'
import { schemaService } from '@renderer/api/schema'
import { listCardTypes, createCardType, updateCardType, deleteCardType, listLLMConfigs, listPrompts, type CardTypeRead as CTR, type CardTypeCreate as CTC, type CardTypeUpdate as CTU } from '@renderer/api/setting'
import SchemaStudio from '../shared/SchemaStudio.vue'

// 後端 CardType 類型
type CardTypeRead = CTR
type CardTypeCreate = CTC
type CardTypeUpdate = CTU

function isBuiltInCardType(row: any): boolean { return !!row?.built_in }

const cardStore = useCardStore()

const loading = ref(false)
const types = ref<CardTypeRead[]>([])
const query = ref('')

async function fetchTypes() { loading.value = true; try { types.value = await listCardTypes() } finally { loading.value = false } }

const filteredTypes = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return types.value
  return types.value.filter(t => (t.name || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q))
})

const drawer = ref({ visible: false, editing: false, id: 0 })
const form = ref<any>({ name: '', description: '', is_ai_enabled: true, is_singleton: false, default_ai_context_template: '' })
const uiLayoutText = ref('')
// AI 參數與可選項
const aiParams = ref<{ llm_config_id?: number; prompt_name?: string; temperature?: number; max_tokens?: number; timeout?: number }>({})
const defaultAIParams = { temperature: 0.7, max_tokens: 1024, timeout: 60 }
const llmConfigs = ref<any[]>([])
const prompts = ref<any[]>([])

function openEditor(row?: CardTypeRead) {
  drawer.value = { visible: true, editing: !!row, id: row?.id || 0 }
  form.value = row ? { ...row } : { name: '', description: '', is_ai_enabled: true, is_singleton: false, default_ai_context_template: '' }
  uiLayoutText.value = row?.ui_layout ? JSON.stringify(row.ui_layout, null, 2) : ''
  aiParams.value = (row as any)?.ai_params ? { ...defaultAIParams, ...(row as any).ai_params } : { ...defaultAIParams }
  // 首次打開加載可選項
  if (llmConfigs.value.length === 0) { listLLMConfigs().then((v) => { llmConfigs.value = v; if (!aiParams.value.llm_config_id && v?.length) aiParams.value.llm_config_id = v[0].id }).catch(() => {}) }
  else if (!aiParams.value.llm_config_id && llmConfigs.value?.length) { aiParams.value.llm_config_id = llmConfigs.value[0].id }
  if (prompts.value.length === 0) { listPrompts().then((v:any) => prompts.value = v).catch(() => {}) }
}

function openSchemaEditor() { openSchemaStudio(form.value?.id ? { id: form.value.id, name: form.value.name } as any : undefined) }

const studio = ref<{ visible: boolean; typeId: number; typeName: string }>({ visible: false, typeId: 0, typeName: '' })
function openSchemaStudio(row?: CardTypeRead) {
  const id = row?.id || drawer.value.id
  const name = row?.name || form.value?.name || ''
  if (!id) { ElMessage.warning('請先保存類型的基礎信息'); return }
  studio.value = { visible: true, typeId: id as number, typeName: name }
}



async function saveType(): Promise<void> {
  let ui_layout: any = undefined
  try { ui_layout = uiLayoutText.value ? JSON.parse(uiLayoutText.value) : undefined } catch { ElMessage.error('UI 佈局不是有效的 JSON'); return }
  const payload: Partial<CardTypeCreate & CardTypeUpdate> = { ...form.value, ui_layout } as any
  ;(payload as any).ai_params = form.value.is_ai_enabled ? aiParams.value : null
  try {
    if (drawer.value.editing) {
      const id = drawer.value.id
      await updateCardType(id, payload)
      ElMessage.success('已更新卡片類型')
    } else {
      await createCardType(payload)
      ElMessage.success('已創建卡片類型')
    }
    drawer.value.visible = false
    await fetchTypes()
    await cardStore.fetchCardTypes()
    await schemaService.refreshSchemas()
  } catch (e:any) { ElMessage.error('保存失敗：' + (e?.message || e)) }
}

async function removeType(row: CardTypeRead) { try { await deleteCardType(row.id as number); ElMessage.success('已刪除'); await fetchTypes() } catch (e:any) { ElMessage.error('刪除失敗：' + (e?.message || e)) } }

function onStudioSaved() { fetchTypes(); cardStore.fetchCardTypes(); schemaService.refreshSchemas() }

onMounted(() => {
  fetchTypes()
  const handler = () => fetchTypes()
  ;(window as any).__cardTypesUpdatedHandler = handler
  window.addEventListener('card-types-updated', handler as any)
})
onBeforeUnmount(() => {
  const handler = (window as any).__cardTypesUpdatedHandler
  if (handler) window.removeEventListener('card-types-updated', handler as any)
})

// 啓用AI時若參數爲空，爲其填充默認值
watch(() => form.value.is_ai_enabled, (v) => {
  if (v) {
    aiParams.value = { ...defaultAIParams, ...(aiParams.value || {}) }
  }
})
</script>

<style scoped>
.card-type-manager { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.toolbar { display: flex; gap: 8px; align-items: center; }
.search { width: 320px; max-width: 60vw; }
.editor-grid { display: grid; grid-template-columns: 1fr; gap: 12px; height: calc(100% - 48px); }
.mt-2 { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
.hint { color: var(--el-text-color-secondary); }
.ai-section-title { font-weight: 600; color: var(--el-text-color-regular); margin-top: 4px; }
.ai-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
</style> 