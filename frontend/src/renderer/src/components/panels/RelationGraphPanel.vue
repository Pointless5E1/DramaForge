<template>
  <div class="relation-graph-panel">
    <div class="toolbar">
      <el-input v-model="filters.keyword" placeholder="關鍵詞（實體/關係/事實）" clearable class="w-keyword" @keyup.enter="reload" />
      <el-select v-model="filters.kind" clearable placeholder="關係類型" class="w-select">
        <el-option v-for="k in kindOptions" :key="k" :label="k" :value="k" />
      </el-select>
      <el-select v-model="filters.stance" clearable placeholder="立場" class="w-select">
        <el-option v-for="s in stanceOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button type="primary" @click="reload">查詢</el-button>
      <el-button @click="resetFilters">重置</el-button>
    </div>

    <div class="actions">
      <el-button type="primary" @click="openCreate">新增關係</el-button>
      <el-button @click="openBatchCreate">批次新增</el-button>
      <el-button @click="openImport">匯入</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="exportSelected('json')">匯出 JSON</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="exportSelected('csv')">匯出 CSV</el-button>
      <el-button :disabled="selectedKeys.length === 0" type="danger" @click="batchDelete">批次刪除</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="batchKindVisible = true">批次改類型</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="batchStanceVisible = true">批次改立場</el-button>
      <el-button :disabled="selectedKeys.length === 0" @click="batchEventsVisible = true">批次追加事件</el-button>
    </div>

    <el-table :data="rows" border stripe v-loading="loading" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column prop="source" label="A" min-width="140" />
      <el-table-column prop="target" label="B" min-width="140" />
      <el-table-column prop="kind_cn" label="關係" width="120" />
      <el-table-column prop="stance" label="立場" width="100" />
      <el-table-column prop="fact" label="事實" min-width="260" show-overflow-tooltip />
      <el-table-column label="更新時間" width="180">
        <template #default="{ row }">
          {{ row.updated_at ? new Date(row.updated_at).toLocaleString() : '' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="scope">
          <el-button text size="small" @click="openEdit(scope.row)">編輯</el-button>
          <el-button text size="small" type="danger" @click="removeOne(scope.row)">刪除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @change="reload"
      />
    </div>

    <el-dialog v-model="editVisible" :title="editMode === 'create' ? '新增關係' : '編輯關係'" width="680px">
      <el-form label-width="110px">
        <el-form-item label="實體 A"><el-input v-model="form.source" /></el-form-item>
        <el-form-item label="關係類型">
          <el-select v-model="form.kind_cn" placeholder="選擇關係類型">
            <el-option v-for="k in kindOptions" :key="k" :label="k" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="實體 B"><el-input v-model="form.target" /></el-form-item>
        <el-form-item label="立場">
          <el-select v-model="form.stance" clearable>
            <el-option v-for="s in stanceOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="事實"><el-input v-model="form.fact" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="A稱呼B"><el-input v-model="form.a_to_b_addressing" /></el-form-item>
        <el-form-item label="B稱呼A"><el-input v-model="form.b_to_a_addressing" /></el-form-item>
        <el-form-item label="近期對話">
          <el-input v-model="form.dialoguesText" type="textarea" :rows="3" placeholder="每行一條" />
        </el-form-item>
        <el-form-item label="近期事件">
          <el-input v-model="form.eventsText" type="textarea" :rows="3" placeholder="每行一條摘要" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">儲存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchKindVisible" title="批次修改關係類型" width="420px">
      <el-select v-model="batchKind" placeholder="選擇新類型" style="width: 100%">
        <el-option v-for="k in kindOptions" :key="k" :label="k" :value="k" />
      </el-select>
      <template #footer>
        <el-button @click="batchKindVisible = false">取消</el-button>
        <el-button type="primary" @click="applyBatchKind">確定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchStanceVisible" title="批次修改立場" width="420px">
      <el-select v-model="batchStance" clearable placeholder="選擇新立場" style="width: 100%">
        <el-option v-for="s in stanceOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <template #footer>
        <el-button @click="batchStanceVisible = false">取消</el-button>
        <el-button type="primary" @click="applyBatchStance">確定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchEventsVisible" title="批次追加事件" width="520px">
      <el-input v-model="batchEventsText" type="textarea" :rows="6" placeholder="每行一條事件摘要" />
      <template #footer>
        <el-button @click="batchEventsVisible = false">取消</el-button>
        <el-button type="primary" @click="applyBatchEvents">確定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchCreateVisible" title="批次新增關係" width="680px">
      <div class="tip">支持 JSON 數組，或每行 CSV：source,target,kind_cn,stance</div>
      <el-input v-model="batchCreateText" type="textarea" :rows="12" />
      <template #footer>
        <el-button @click="batchCreateVisible = false">取消</el-button>
        <el-button type="primary" @click="submitBatchCreate">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="匯入關係圖" width="680px">
      <div class="toolbar compact">
        <el-select v-model="importFormat" class="w-select">
          <el-option label="JSON" value="json" />
          <el-option label="CSV" value="csv" />
        </el-select>
        <el-button @click="pickFile">從文件讀取</el-button>
      </div>
      <input ref="fileInputRef" type="file" class="hidden" @change="onFileChange" />
      <el-input v-model="importContent" type="textarea" :rows="12" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" @click="submitImport">匯入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import {
  batchAppendEventsRelationGraph,
  batchCreateRelationGraph,
  batchDeleteRelationGraph,
  batchUpdateKindRelationGraph,
  batchUpdateStanceRelationGraph,
  deleteRelationGraph,
  exportRelationGraph,
  getRelationGraphMeta,
  importRelationGraph,
  listRelationGraph,
  upsertRelationGraph,
  type RelationGraphKind,
  type RelationGraphKey,
  type RelationGraphRecord,
  type RelationGraphStance,
} from '@renderer/api/relationGraph'

const props = defineProps<{ refreshSeq?: number }>()

const projectStore = useProjectStore()
const loading = ref(false)
const rows = ref<RelationGraphRecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedRows = ref<RelationGraphRecord[]>([])

const filters = reactive<{ keyword: string; kind: RelationGraphKind | ''; stance: RelationGraphStance | '' }>({
  keyword: '',
  kind: '',
  stance: '',
})

const kindOptions = ref<RelationGraphKind[]>([])
const stanceOptions = ref<RelationGraphStance[]>([])

const editVisible = ref(false)
const editMode = ref<'create' | 'edit'>('create')
const editingKey = ref<RelationGraphKey | null>(null)
const form = reactive({
  source: '',
  target: '',
  kind_cn: '' as RelationGraphKind | '',
  stance: '' as RelationGraphStance | '',
  fact: '',
  a_to_b_addressing: '',
  b_to_a_addressing: '',
  dialoguesText: '',
  eventsText: '',
})

const batchKindVisible = ref(false)
const batchKind = ref<RelationGraphKind | ''>('')
const batchStanceVisible = ref(false)
const batchStance = ref<RelationGraphStance | ''>('')
const batchEventsVisible = ref(false)
const batchEventsText = ref('')
const batchCreateVisible = ref(false)
const batchCreateText = ref('')

const importVisible = ref(false)
const importFormat = ref<'json' | 'csv'>('json')
const importContent = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const selectedKeys = computed<RelationGraphKey[]>(() =>
  selectedRows.value
    .filter((r) => !!r.source && !!r.target && !!r.kind_en)
    .map((r) => ({ source: r.source!, target: r.target!, kind_en: r.kind_en! }))
)

function getProjectId(): number {
  const pid = projectStore.currentProject?.id
  if (!pid) throw new Error('請先選擇專案')
  return pid
}

function parseLines(text: string): string[] {
  return (text || '').split(/\r?\n/).map((x) => x.trim()).filter(Boolean)
}

function resetForm() {
  form.source = ''
  form.target = ''
  form.kind_cn = ''
  form.stance = ''
  form.fact = ''
  form.a_to_b_addressing = ''
  form.b_to_a_addressing = ''
  form.dialoguesText = ''
  form.eventsText = ''
}

function openCreate() {
  editMode.value = 'create'
  editingKey.value = null
  resetForm()
  editVisible.value = true
}

function openEdit(row: RelationGraphRecord) {
  editMode.value = 'edit'
  editingKey.value = { source: row.source!, target: row.target!, kind_en: row.kind_en! }
  form.source = row.source || ''
  form.target = row.target || ''
  form.kind_cn = ((row.kind_cn || row.kind || '') as RelationGraphKind | '')
  form.stance = ((row.stance || '') as RelationGraphStance | '')
  form.fact = row.fact || ''
  form.a_to_b_addressing = row.a_to_b_addressing || ''
  form.b_to_a_addressing = row.b_to_a_addressing || ''
  form.dialoguesText = (row.recent_dialogues || []).join('\n')
  form.eventsText = (row.recent_event_summaries || []).map((e: any) => e.summary || '').filter(Boolean).join('\n')
  editVisible.value = true
}

async function reload() {
  try {
    const projectId = getProjectId()
    loading.value = true
    const resp = await listRelationGraph({
      project_id: projectId,
      keyword: filters.keyword || undefined,
      kinds: filters.kind ? [filters.kind] : [],
      stances: filters.stance ? [filters.stance] : [],
      offset: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    })
    rows.value = resp.items || []
    total.value = resp.total || 0
  } catch (e: any) {
    ElMessage.error(e?.message || '載入關係圖失敗')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.kind = ''
  filters.stance = ''
  page.value = 1
  reload()
}

function onSelectionChange(list: RelationGraphRecord[]) {
  selectedRows.value = list || []
}

async function submitEdit() {
  try {
    const projectId = getProjectId()
    const saved = await upsertRelationGraph({
      project_id: projectId,
      relation: {
        source: form.source,
        target: form.target,
        kind_cn: form.kind_cn || undefined,
        fact: form.fact || undefined,
        a_to_b_addressing: form.a_to_b_addressing || undefined,
        b_to_a_addressing: form.b_to_a_addressing || undefined,
        stance: form.stance || undefined,
        recent_dialogues: parseLines(form.dialoguesText),
        recent_event_summaries: parseLines(form.eventsText).map((summary) => ({ summary })),
      },
    })

    if (editMode.value === 'edit' && editingKey.value) {
      const oldKey = editingKey.value
      const changedKey =
        oldKey.source !== saved.source ||
        oldKey.target !== saved.target ||
        oldKey.kind_en !== saved.kind_en
      if (changedKey) {
        await deleteRelationGraph({ project_id: projectId, key: oldKey })
      }
    }

    editVisible.value = false
    ElMessage.success('儲存成功')
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '儲存失敗')
  }
}

async function removeOne(row: RelationGraphRecord) {
  try {
    const projectId = getProjectId()
    await ElMessageBox.confirm(`確認刪除關係 ${row.source} -> ${row.target} 嗎？`, '刪除確認', { type: 'warning' })
    await deleteRelationGraph({ project_id: projectId, key: { source: row.source!, target: row.target!, kind_en: row.kind_en! } })
    ElMessage.success('刪除成功')
    reload()
  } catch {}
}

async function batchDelete() {
  try {
    const projectId = getProjectId()
    await ElMessageBox.confirm(`確認刪除已勾選的 ${selectedKeys.value.length} 條關係嗎？`, '批次刪除', { type: 'warning' })
    const resp = await batchDeleteRelationGraph({ project_id: projectId, keys: selectedKeys.value })
    ElMessage.success(`已刪除 ${resp.affected || 0} 條`)
    reload()
  } catch {}
}

async function applyBatchKind() {
  try {
    const projectId = getProjectId()
    const resp = await batchUpdateKindRelationGraph({
      project_id: projectId,
      keys: selectedKeys.value,
      new_kind_cn: batchKind.value || undefined,
    })
    ElMessage.success(`已更新 ${resp.affected || 0} 條`)
    batchKindVisible.value = false
    batchKind.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批次更新失敗')
  }
}

async function applyBatchStance() {
  try {
    const projectId = getProjectId()
    const resp = await batchUpdateStanceRelationGraph({
      project_id: projectId,
      keys: selectedKeys.value,
      stance: batchStance.value || undefined,
    })
    ElMessage.success(`已更新 ${resp.affected || 0} 條`)
    batchStanceVisible.value = false
    batchStance.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批次更新失敗')
  }
}

async function applyBatchEvents() {
  try {
    const projectId = getProjectId()
    const events = parseLines(batchEventsText.value).map((summary) => ({ summary }))
    const resp = await batchAppendEventsRelationGraph({ project_id: projectId, keys: selectedKeys.value, events, max_size: 20 })
    ElMessage.success(`已更新 ${resp.affected || 0} 條`)
    batchEventsVisible.value = false
    batchEventsText.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批次更新失敗')
  }
}

function openBatchCreate() {
  batchCreateVisible.value = true
}

function parseBatchCreateInput(text: string) {
  const trimmed = text.trim()
  if (!trimmed) return []
  if (trimmed.startsWith('[')) {
    const arr = JSON.parse(trimmed)
    if (!Array.isArray(arr)) throw new Error('JSON 必須是數組')
    return arr
  }
  return parseLines(trimmed).map((line) => {
    const [source, target, kind_cn, stance] = line.split(',').map((x) => x.trim())
    return { source, target, kind_cn, stance }
  })
}

async function submitBatchCreate() {
  try {
    const projectId = getProjectId()
    const relations = parseBatchCreateInput(batchCreateText.value)
    const resp = await batchCreateRelationGraph({ project_id: projectId, relations })
    ElMessage.success(`已處理 ${resp.affected || 0} 條`)
    batchCreateVisible.value = false
    batchCreateText.value = ''
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '批次新增失敗')
  }
}

function saveDownload(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime || 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function exportSelected(format: 'json' | 'csv') {
  try {
    const projectId = getProjectId()
    const resp = await exportRelationGraph({ project_id: projectId, format, keys: selectedKeys.value })
    saveDownload(resp.filename || `relation-graph.${format}`, resp.content || '', resp.mime_type || 'text/plain')
    ElMessage.success('匯出完成')
  } catch (e: any) {
    ElMessage.error(e?.message || '匯出失敗')
  }
}

function openImport() {
  importVisible.value = true
}

function pickFile() {
  fileInputRef.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importContent.value = await file.text()
}

async function submitImport() {
  try {
    const projectId = getProjectId()
    const resp = await importRelationGraph({ project_id: projectId, format: importFormat.value, content: importContent.value })
    ElMessage.success(`匯入完成：新增 ${resp.created || 0}，更新 ${resp.updated || 0}，失敗 ${resp.failed || 0}`)
    if ((resp.errors || []).length > 0) {
      ElMessage.warning(`存在 ${resp.errors?.length} 條錯誤，請檢查輸入格式`)
    }
    importVisible.value = false
    reload()
  } catch (e: any) {
    ElMessage.error(e?.message || '匯入失敗')
  }
}

async function loadMeta() {
  try {
    const meta = await getRelationGraphMeta()
    kindOptions.value = (meta.kinds || []).map((item) => item.kind_cn).filter(Boolean)
    stanceOptions.value = (meta.stances || []).filter(Boolean)
  } catch (e: any) {
    ElMessage.error(e?.message || '載入關係元資料失敗')
  }
}

onMounted(async () => {
  await loadMeta()
  reload()
})

watch(() => props.refreshSeq, (next, prev) => {
  if (next !== prev) {
    reload()
  }
})
</script>

<style scoped>
.relation-graph-panel { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar.compact { padding: 0 0 8px 0; }
.actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.w-keyword { width: 280px; }
.w-select { width: 140px; }
.pager { display: flex; justify-content: flex-end; padding-top: 8px; }
.hidden { display: none; }
.tip { color: var(--el-text-color-secondary); font-size: 12px; margin-bottom: 8px; }
</style>
