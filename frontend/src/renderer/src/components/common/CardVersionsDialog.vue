<template>
  <el-dialog v-model="visible" title="歷史版本" width="80%">
    <div class="toolbar">
      <el-button size="small" @click="reload">刷新</el-button>
      <el-popconfirm title="清空該卡片的所有本地版本？" @confirm="clearAll">
        <template #reference>
          <el-button size="small" type="danger" plain>清空全部</el-button>
        </template>
      </el-popconfirm>
      <span class="tip">歷史版本僅保存在前端，最多保留最近20條。</span>
    </div>

    <el-table :data="versions" style="width:100%" height="50vh" size="small" v-loading="loading">
      <el-table-column label="時間" width="200">
        <template #default="{ row }">{{ format(row.createdAt) }}</template>
      </el-table-column>
      <el-table-column prop="title" label="標題" width="240" />
      <el-table-column label="摘要(內容)" width="320">
        <template #default="{ row }">
          <span class="summary">{{ summarize(row.content) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要(上下文)" width="320">
        <template #default="{ row }">
          <span class="summary">{{ summarizeCtx(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button size="small" @click="preview(row)">預覽</el-button>
          <el-popconfirm title="恢復該版本並覆蓋當前內容？" @confirm="restore(row)">
            <template #reference>
              <el-button size="small" type="primary">恢復</el-button>
            </template>
          </el-popconfirm>
          <el-popconfirm title="刪除該版本？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" type="danger" plain>刪除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible=false">關閉</el-button>
    </template>

    <!-- 預覽抽屜：改爲並排差異高亮渲染 -->
    <el-drawer v-model="drawerVisible" title="版本預覽" size="70%">
      <div class="preview-wrap2">
        <div class="pane">
          <h4>內容對比</h4>
          <div class="diff-table">
            <div class="diff-header">所選版本</div>
            <div class="diff-header">當前</div>
            <template v-for="(row, idx) in contentDiffRows" :key="'c-'+idx">
              <pre class="diff-cell" :class="row.left?.type ? 'diff-' + row.left.type : 'diff-empty'">{{ row.left?.text || '' }}</pre>
              <pre class="diff-cell" :class="row.right?.type ? 'diff-' + row.right.type : 'diff-empty'">{{ row.right?.text || '' }}</pre>
            </template>
          </div>
        </div>
        <div class="pane">
          <h4>上下文模板對比</h4>
          <div class="diff-table">
            <div class="diff-header">所選版本</div>
            <div class="diff-header">當前</div>
            <template v-for="(row, idx) in contextDiffRows" :key="'x-'+idx">
              <pre class="diff-cell" :class="row.left?.type ? 'diff-' + row.left.type : 'diff-empty'">{{ row.left?.text || '' }}</pre>
              <pre class="diff-cell" :class="row.right?.type ? 'diff-' + row.right.type : 'diff-empty'">{{ row.right?.text || '' }}</pre>
            </template>
          </div>
        </div>
      </div>
    </el-drawer>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { listVersions, clearVersions, deleteVersion, type CardVersionSnapshot } from '@renderer/services/versionService'
import { ElMessage } from 'element-plus'
import { cloneContextTemplates, CONTEXT_TEMPLATE_LABELS, type ContextTemplates } from '@renderer/services/contextSlots'

const props = defineProps<{ projectId: number; cardId: number; modelValue: boolean; currentContent: any; currentContextTemplates: ContextTemplates }>()
const emit = defineEmits(['update:modelValue','restore'])

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => visible.value = v)
watch(visible, v => emit('update:modelValue', v))

const versions = ref<CardVersionSnapshot[]>([])
const loading = ref(false)

function reload() {
  loading.value = true
  versions.value = listVersions(props.projectId, props.cardId)
  loading.value = false
}

watch(() => props.cardId, reload, { immediate: true })

function format(iso: string) { return new Date(iso).toLocaleString() }
function summarize(content: any) {
  const s = JSON.stringify(content ?? {})
  return s.length > 100 ? s.slice(0, 100) + '…' : s
}
function summarizeCtx(snapshot: CardVersionSnapshot) {
  const s = [
    `${CONTEXT_TEMPLATE_LABELS.generation}: ${String(snapshot.ai_context_template ?? '')}`,
    `${CONTEXT_TEMPLATE_LABELS.review}: ${String(snapshot.ai_context_template_review ?? '')}`,
  ].join('\n')
  return s.length > 100 ? s.slice(0, 100) + '…' : s
}

function clearAll() {
  clearVersions(props.projectId, props.cardId)
  reload()
  ElMessage.success('已清空該卡片的本地版本')
}

function remove(v: CardVersionSnapshot) {
  deleteVersion(props.projectId, props.cardId, v.id)
  reload()
  ElMessage.success('已刪除該版本')
}

const drawerVisible = ref(false)
const selectedText = ref('')
const selectedCtx = ref<ContextTemplates>(cloneContextTemplates())
const currentText = computed(() => JSON.stringify(props.currentContent ?? {}, null, 2))
const currentCtx = computed(() =>
  [
    `${CONTEXT_TEMPLATE_LABELS.generation}\n${props.currentContextTemplates?.generation ?? ''}`,
    `${CONTEXT_TEMPLATE_LABELS.review}\n${props.currentContextTemplates?.review ?? ''}`,
  ].join('\n\n')
)

function preview(v: CardVersionSnapshot) {
  selectedText.value = JSON.stringify(v.content ?? {}, null, 2)
  selectedCtx.value = cloneContextTemplates({
    generation: v.ai_context_template,
    review: v.ai_context_template_review,
  })
  drawerVisible.value = true
}

function restore(v: CardVersionSnapshot) {
  emit('restore', v)
}

// 輕量行級差異算法（LCS 對齊）
// 輸入兩段文本，按行拆分後計算最短編輯路徑對齊，輸出左右並排渲染所需的數據結構
interface DiffPart { text: string; type: 'equal' | 'add' | 'del' }
interface DiffRow { left?: DiffPart; right?: DiffPart }

function computeDiffRows(left: string, right: string): DiffRow[] {
  const a = (left || '').split('\n')
  const b = (right || '').split('\n')
  const m = a.length, n = b.length
  // dp[i][j] 表示 a[0..i-1] 與 b[0..j-1] 的 LCS 長度
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }
  // 回溯獲取對齊路徑
  const rows: DiffRow[] = []
  let i = m, j = n
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      rows.push({ left: { text: a[i - 1], type: 'equal' }, right: { text: b[j - 1], type: 'equal' } })
      i--; j--
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      rows.push({ left: { text: a[i - 1], type: 'del' } })
      i--
    } else {
      rows.push({ right: { text: b[j - 1], type: 'add' } })
      j--
    }
  }
  while (i > 0) { rows.push({ left: { text: a[i - 1], type: 'del' } }); i-- }
  while (j > 0) { rows.push({ right: { text: b[j - 1], type: 'add' } }); j-- }
  rows.reverse()
  return rows
}

// 內容與上下文的並排差異結果
const contentDiffRows = computed<DiffRow[]>(() => computeDiffRows(selectedText.value, currentText.value))
const contextDiffRows = computed<DiffRow[]>(() => computeDiffRows(
  [
    `${CONTEXT_TEMPLATE_LABELS.generation}\n${selectedCtx.value.generation}`,
    `${CONTEXT_TEMPLATE_LABELS.review}\n${selectedCtx.value.review}`,
  ].join('\n\n'),
  currentCtx.value
))
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tip { color: var(--el-text-color-secondary); font-size: 12px; margin-left: auto; }
.preview-wrap2 { display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: minmax(140px, auto); gap: 12px; }
.pane { overflow: auto; border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 8px; }
.summary { color: var(--el-text-color-secondary); }

/* 差異渲染：兩列並排，行級高亮 */
.diff-table { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--el-border-color-light); border-radius: 4px; overflow: hidden; }
.diff-header { background: var(--el-fill-color-light); font-weight: 600; padding: 6px 8px; border-bottom: 1px solid var(--el-border-color-light); }
.diff-cell { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; padding: 2px 6px; border-left: 3px solid transparent; border-bottom: 1px solid var(--el-border-color-extra-light); }
.diff-equal { background: transparent; }
.diff-add { background: rgba(46, 204, 113, 0.12); border-left-color: #2ecc71; }
.diff-del { background: rgba(231, 76, 60, 0.13); border-left-color: #e74c3c; }
.diff-empty { background: var(--el-fill-color-blank); }
</style> 
