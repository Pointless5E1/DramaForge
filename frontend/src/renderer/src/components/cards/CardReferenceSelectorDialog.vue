<template>
  <el-dialog
    :model-value="modelValue"
    title="引用卡片/上下文"
    width="84%"
    @update:modelValue="$emit('update:modelValue', $event)"
    @close="reset"
  >
    <div class="selector-container">
      <!-- 左列：模式選擇 + 列表區 -->
      <div class="column left">
        <h3>1. 選擇引用方式</h3>
        <el-radio-group v-model="mode" size="small">
          <el-radio-button label="title">按標題</el-radio-button>
          <el-radio-button label="type">按類型</el-radio-button>
          <el-radio-button label="special">特殊</el-radio-button>
        </el-radio-group>

        <!-- 按標題模式：原有卡片列表 -->
        <template v-if="mode === 'title'">
          <el-input v-model="cardSearch" placeholder="搜索卡片..." clearable class="mt8" />
          <el-scrollbar class="list-container">
            <ul class="card-list">
              <li
                v-for="card in filteredCards"
                :key="card.id"
                :class="{ selected: selectedKard?.id === card.id }"
                @click="handleCardSelect(card)"
              >
                {{ card.title }}
              </li>
            </ul>
          </el-scrollbar>
        </template>

        <!-- 按類型模式：類型選擇 + 過濾方式（previous/sibling/first/last/index） + index 表達式 -->
        <template v-else-if="mode === 'type'">
          <div class="mt8">
            <el-select v-model="selectedTypeName" placeholder="選擇卡片類型" style="width: 100%" @change="handleTypeChange">
              <el-option v-for="t in cardTypeNames" :key="t" :label="t" :value="t" />
            </el-select>
          </div>
          <div class="mt8">
            <el-radio-group v-model="typeFilterMode" size="small">
              <el-radio-button label="first" :title="filterTips.first">first</el-radio-button>
              <el-radio-button label="last" :title="filterTips.last">last</el-radio-button>
              <el-radio-button label="previous" :title="filterTips.previous">previous</el-radio-button>
              <el-radio-button label="sibling" :title="filterTips.sibling" :disabled="!hasParent">sibling</el-radio-button>
              <el-radio-button label="index" :title="filterTips.index">index</el-radio-button>
            </el-radio-group>
          </div>
          <div class="mt8" v-if="typeFilterMode === 'previous'">
            <el-radio-group v-model="previousMode" size="small">
              <el-radio-button label="global" :title="previousModeTips.global">全局</el-radio-button>
              <el-radio-button label="local" :title="previousModeTips.local" :disabled="!hasParent">局部</el-radio-button>
            </el-radio-group>
          </div>
          <div class="mt8" v-if="typeFilterMode === 'previous' && previousMode === 'global'">
            <el-input v-model="previousCount" placeholder="可選：輸入數字限制返回最近 n 個，留空=全部" />
          </div>
          <div class="mt8" v-if="typeFilterMode === 'index'">
            <el-input v-model="indexExpr" placeholder="index= 的表達式，例如 1 / last / $current.volumeNumber-1 / $self.content.volume_number-1 / filter:content.name in $self.content.entity_list" />
            <div class="mt8">
              <el-checkbox v-model="advMode">高級模式</el-checkbox>
            </div>
            <div class="mt8 adv-grid" v-if="advMode">
              <div class="cond-list">
                <div class="cond-item" v-for="(c, idx) in advConds" :key="idx">
                  <el-select v-model="c.field" placeholder="選擇字段" style="width: 45%">
                    <el-option v-for="fp in flatFieldList" :key="fp.path" :label="fp.label + ' ('+fp.path+')'" :value="fp.path" />
                  </el-select>
                  <el-select v-model="c.op" placeholder="操作符" style="width: 12%">
                    <el-option label="=" value="=" />
                    <el-option label="in" value="in" />
                    <el-option label="<" value="<" />
                    <el-option label=">" value=">" />
                  </el-select>
                  <el-input v-model="c.rhs" placeholder='右值：$self./$parent./$current. 或 JSON/字面量' style="width: 40%" />
                  <el-button text type="danger" @click="removeCond(idx)">刪除</el-button>
                </div>
                <div class="mt8">
                  <el-button size="small" @click="addCond">添加條件</el-button>
                </div>
              </div>
            </div>
            <div class="hint" v-if="advMode">將生成：index=filter:{{ advCondPreview }}</div>
          </div>
        </template>

        <!-- 特殊模式：self / parent / stage:current -->
        <template v-else>
          <div class="mt8">
            <el-select v-model="specialKey" placeholder="選擇特殊引用" style="width: 100%">
              <el-option label="self（當前卡片）" value="self" />
              <el-option label="parent（父卡片）" value="parent" :disabled="!hasParent" />
              <el-option label="stage:current（當前階段）" value="stage:current" />
            </el-select>
          </div>
          <div class="mt8" v-if="specialKey === 'self' || specialKey === 'stage:current'">
            <el-input v-model="specialPath" placeholder="可選：在此輸入字段路徑，如 content.volume_number" />
          </div>
        </template>
      </div>

      <!-- 右列：字段樹 -->
      <div class="column">
        <div class="row-head">
          <h3>2. 選擇字段（可選）</h3>
          <div class="right-tools">
            <el-checkbox v-model="multiMode">多選字段</el-checkbox>
          </div>
        </div>
        <el-tree
          v-if="fieldPaths.length"
          ref="treeRef"
          :data="fieldPaths"
          :props="{ label: 'label', children: 'children' }"
          :show-checkbox="multiMode"
          :check-strictly="true"
          @node-click="handleFieldSelect"
          @check="handleTreeCheck"
          class="field-tree"
          highlight-current
        />
        <div v-else class="empty-state">
          <p>在此選擇要追加的字段路徑（可選）。</p>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <div class="footer-container">
        <span class="selection-preview">
          預覽: <strong>{{ selectionPreview }}</strong>
        </span>
        <span class="dialog-footer">
          <el-button @click="$emit('update:modelValue', false)">取消</el-button>
          <el-button type="primary" @click="handleConfirm" :disabled="!canConfirm">
            確認
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { CardRead } from '@renderer/api/cards'
import { schemaService, type JSONSchema } from '@renderer/api/schema'
import { getCardSchema } from '@renderer/api/setting'
import { ElDialog, ElInput, ElScrollbar, ElTree, ElButton, ElRadioGroup, ElRadioButton, ElSelect, ElOption, ElCheckbox } from 'element-plus'

interface FieldPath {
  label: string
  path: string
  children?: FieldPath[]
}

const props = defineProps<{ modelValue: boolean; cards: CardRead[]; currentCardId?: number }>()
const emit = defineEmits(['update:modelValue', 'confirm'])

// --- 模式與選擇 ---
const mode = ref<'title' | 'type' | 'special'>('title')

// 當前卡片與父卡片
const currentCard = computed(() => props.cards.find(c => c.id === props.currentCardId))
const parentCard = computed(() => props.cards.find(c => c.id === (currentCard.value?.parent_id || -1)))
const hasParent = computed(() => !!parentCard.value)

// 按標題
const cardSearch = ref('')
const selectedKard = ref<CardRead | null>(null)

// 按類型
const selectedTypeName = ref<string | undefined>(undefined)
const typeFilterMode = ref<'previous' | 'sibling' | 'first' | 'last' | 'index'>('first')
const previousMode = ref<'global' | 'local'>('global')
const indexExpr = ref<string>('1')
const previousCount = ref<string>('')

const filterTips = {
  first: '全局穩定排序中的第一個同類型卡片',
  last: '全局穩定排序中的最後一個同類型卡片',
  previous: '選擇 previous 模式：全局/局部',
  sibling: '與當前卡片同一父卡片下的同類型兄弟卡片（返回數組）',
  index: '按表達式選擇單個卡片：1、-1、$current.volumeNumber-1、$self.content.volume_number+1 等'
}

const previousModeTips = {
  global: '全局：樹形先序順序中，當前卡片之前的所有同類型卡片',
  local: '局部：同一父卡片下，當前卡片之前的同類型兄弟卡片'
}

// 特殊
const specialKey = ref<string | undefined>(undefined)
const specialPath = ref<string>('')

// 字段樹
const treeRef = ref()
const selectedFieldPath = ref<string | null>(null)
const selectedFieldPaths = ref<string[]>([])
const multiMode = ref<boolean>(false)
const fieldPaths = ref<FieldPath[]>([])
// 高級模式（僅 index）：多條件
const advMode = ref<boolean>(false)
type AdvCond = { field: string; op: '='|'in'|'<'|'>'; rhs: string }
const advConds = ref<AdvCond[]>([])

const flatFieldList = computed(() => {
  const out: { label: string; path: string }[] = []
  function walk(nodes: FieldPath[]) {
    for (const n of nodes) {
      out.push({ label: n.label, path: n.path })
      if (n.children && n.children.length) walk(n.children)
    }
  }
  walk(fieldPaths.value)
  return out
})

// 過濾卡片（按標題）
const filteredCards = computed(() => props.cards.filter(card => card.title.toLowerCase().includes(cardSearch.value.toLowerCase())))

// 所有類型名
const cardTypeNames = computed(() => Array.from(new Set(props.cards.map(c => c.card_type?.name).filter(Boolean) as string[])))

function buildPathSpec(): string {
  if (multiMode.value && selectedFieldPaths.value.length > 0) {
    return ".{" + selectedFieldPaths.value.join(',') + "}"
  }
  if (selectedFieldPath.value) return `.${selectedFieldPath.value}`
  return ''
}

// 預覽字符串
const selectionPreview = computed(() => {
  const pathSpec = buildPathSpec()
  if (mode.value === 'title') {
    if (!selectedKard.value) return ''
    // 標題模式：未選字段時默認 .content
    if (!pathSpec) return `@${selectedKard.value.title}.content`
    return `@${selectedKard.value.title}${pathSpec}`
  }
  if (mode.value === 'type') {
    if (!selectedTypeName.value) return ''
    let filter = ''
    if (typeFilterMode.value === 'previous') {
      const n = previousCount.value.trim()
      if (previousMode.value === 'local') {
        filter = '[previous:local]'
      } else {
        // global 模式
        filter = n ? `[previous:global:${n}]` : '[previous:global]'
      }
    } else if (typeFilterMode.value === 'sibling') filter = '[sibling]'
    else if (typeFilterMode.value === 'first') filter = '[first]'
    else if (typeFilterMode.value === 'last') filter = '[last]'
    else if (typeFilterMode.value === 'index') filter = `[index=${indexExpr.value.trim()}]`
    // 類型模式：未選字段時默認 .content
    if (!pathSpec) return `@type:${selectedTypeName.value}${filter}.content`
    return `@type:${selectedTypeName.value}${filter}${pathSpec}`
  }
  if (mode.value === 'special') {
    if (!specialKey.value) return ''
    if (multiMode.value && selectedFieldPaths.value.length > 0) {
      return `@${specialKey.value}${pathSpec}`
    }
    if (selectedFieldPath.value) {
      return `@${specialKey.value}${pathSpec}`
    }
    // 特殊：parent/self 默認 .content；stage/chapters 按原規則
    let s = `@${specialKey.value}`
    if (specialKey.value === 'parent' || specialKey.value === 'self') {
      s += `.content`
    }
    if (specialPath.value && specialKey.value !== 'chapters:previous') s += `.${specialPath.value}`
    return s
  }
  return ''
})

const canConfirm = computed(() => {
  if (mode.value === 'title') return !!selectedKard.value
  if (mode.value === 'type') return !!selectedTypeName.value
  if (mode.value === 'special') return !!specialKey.value && (specialKey.value !== 'parent' || hasParent.value)
  return false
})

const advCondPreview = computed(() => {
  return advConds.value
    .filter(c => c.field && c.op && (c.rhs || c.op === 'in'))
    .map(c => `${c.field || 'content.<field>'} ${c.op} ${c.rhs || '<rhs>'}`)
    .join(' && ')
})

function addCond() {
  advConds.value.push({ field: 'content.name', op: 'in', rhs: '[]' })
}
function removeCond(idx: number) {
  advConds.value.splice(idx, 1)
}

// 同步高級模式表達式到 indexExpr（多條件）
watch([advMode, advConds], () => {
  if (mode.value === 'type' && typeFilterMode.value === 'index' && advMode.value) {
    const expr = advCondPreview.value
    indexExpr.value = expr ? `filter:${expr}` : 'filter:'
  }
}, { deep: true })

watch(
  () => props.modelValue,
  isOpening => {
    if (isOpening) reset()
  }
)

function reset() {
  mode.value = 'title'
  // 標題模式
  cardSearch.value = ''
  selectedKard.value = null
  // 類型模式
  selectedTypeName.value = undefined
  typeFilterMode.value = 'first'
  previousMode.value = 'global'
  indexExpr.value = '1'
  previousCount.value = ''
  advMode.value = false
  advConds.value = []
  // 特殊模式
  specialKey.value = undefined
  specialPath.value = ''
  // 字段樹與路徑
  selectedFieldPath.value = null
  selectedFieldPaths.value = []
  multiMode.value = false
  fieldPaths.value = []
}

// --- Stage:Current 支持 ---
function unwrapVolumeOutline(content: any): any {
  if (!content || typeof content !== 'object') return {}
  for (const k of ['volume_outline','VolumeOutline','volumeOutline','volume_outline_response','VolumeOutlineResponse']) {
    if (content[k] && typeof content[k] === 'object') return content[k]
  }
  return content
}

function findCurrentStage(cards: CardRead[], currentCardId?: number): { stage: any | null; volumeNumber?: number; chapterNumber?: number } {
  const cur = cards.find(c => c.id === currentCardId)
  if (!cur) return { stage: null }
  const c = (cur.content || {}) as any
  const vol = typeof c?.volume_number === 'number' ? c.volume_number : undefined
  const chn = typeof c?.chapter_number === 'number' ? c.chapter_number : undefined
  if (!vol || !chn) return { stage: null }
  const volCard = cards.find(x => (x.card_type as any)?.output_model_name === 'VolumeOutline' || x.card_type?.name === '分卷大綱')
  if (!volCard) return { stage: null, volumeNumber: vol, chapterNumber: chn }
  const vo = unwrapVolumeOutline(volCard.content || {})
  const stages = Array.isArray(vo?.stage_lines) ? vo.stage_lines : []
  if (!stages.length) return { stage: null, volumeNumber: vol, chapterNumber: chn }
  const match = stages.find((st: any) => {
    const rc = st?.reference_chapter
    if (!Array.isArray(rc) || rc.length < 2) return false
    const [start, end] = rc
    return typeof start === 'number' && typeof end === 'number' && chn >= start && chn <= end
  })
  return { stage: match || null, volumeNumber: vol, chapterNumber: chn }
}

const stageFound = ref<boolean>(false)
const stageMeta = ref<{ volume?: number; chapter?: number; name?: string } | null>(null)

// 當選擇特殊引用爲 parent 時，自動加載父卡片 schema 並渲染字段樹
watch(specialKey, async (key) => {
  selectedFieldPath.value = null
  selectedFieldPaths.value = []
  fieldPaths.value = []
  if (key === 'parent') {
    if (!hasParent.value) { fieldPaths.value = []; return }
    try {
      const resp = await getCardSchema(parentCard.value!.id)
      const sch = resp?.effective_schema || resp?.json_schema
      fieldPaths.value = sch ? generateFieldPaths(sch as any) : []
    } catch { fieldPaths.value = [] }
  } else if (key === 'self') {
    try {
      const resp = await getCardSchema(currentCard.value!.id)
      const sch = resp?.effective_schema || resp?.json_schema
      fieldPaths.value = sch ? generateFieldPaths(sch as any) : []
    } catch { fieldPaths.value = [] }
  } else if (key === 'stage:current') {
    // 自動定位當前章節所在階段；若命中，則右側展示 StageLine 字段
    const { stage, volumeNumber, chapterNumber } = findCurrentStage(props.cards, props.currentCardId)
    stageFound.value = !!stage
    stageMeta.value = { volume: volumeNumber, chapter: chapterNumber, name: typeof stage?.stage_name === 'string' ? stage.stage_name : undefined }
    await schemaService.loadSchemas()
    const stageSchema = schemaService.getSchema('StageLine')
    // 對於特殊對象，路徑不加 'content.' 前綴，直接展示字段名
    fieldPaths.value = stage ? (stageSchema ? generateFieldPaths(stageSchema, '') : []) : []
  } else {
    fieldPaths.value = []
  }
})

async function handleCardSelect(card: CardRead) {
  selectedKard.value = card
  selectedFieldPath.value = null
  selectedFieldPaths.value = []
  fieldPaths.value = []
  try {
    const resp = await getCardSchema(card.id)
    const sch = resp?.effective_schema || resp?.json_schema
    if (sch) fieldPaths.value = generateFieldPaths(sch as any)
  } catch {}
}

async function handleTypeChange() {
  // 根據類型名選取任意同類型卡片以加載其 schema
  selectedFieldPath.value = null
  selectedFieldPaths.value = []
  fieldPaths.value = []
  const sample = props.cards.find(c => c.card_type?.name === selectedTypeName.value)
  if (sample) {
    try {
      const resp = await getCardSchema(sample.id)
      const sch = resp?.effective_schema || resp?.json_schema
      if (sch) fieldPaths.value = generateFieldPaths(sch as any)
    } catch {}
  }
}

function generateFieldPaths(schema: JSONSchema, prefix = 'content'): FieldPath[] {
  const paths: FieldPath[] = []

  const resolveRef = (refStr?: string): any | null => {
    if (!refStr || typeof refStr !== 'string') return null
    const name = refStr.split('/').pop() || ''
    return schemaService.getSchema(name) || null
  }

  const walkObject = (objSchema: any, basePath: string) => {
    const props = (objSchema && objSchema.properties) || {}
    for (const [key, propSchema] of Object.entries(props)) {
      const currentPath = basePath ? `${basePath}.${key}` : key
      const node: FieldPath = { label: (propSchema as any).title || key, path: currentPath }

      if ((propSchema as any).$ref) {
        const refSchema = resolveRef((propSchema as any).$ref)
        if (refSchema) node.children = generateFieldPaths(refSchema as any, currentPath)
      } else if ((propSchema as any).type === 'object' && (propSchema as any).properties) {
        node.children = generateFieldPaths(propSchema as any, currentPath)
      } else if ((propSchema as any).type === 'array') {
        const items = (propSchema as any).items
        if (items && (items.$ref || items.type === 'object')) {
          const itemSchema = items.$ref ? resolveRef(items.$ref) : items
          const arrayPath = `${currentPath}[]`
          const arrayNode: FieldPath = { label: (propSchema as any).title || key, path: arrayPath, children: [] }
          arrayNode.children = itemSchema ? generateFieldPaths(itemSchema as any, arrayPath) : []
          node.children = node.children || []
          node.children.push(arrayNode)
        }
      }

      paths.push(node)
    }
  }

  if (schema && (schema as any).properties) walkObject(schema as any, prefix)
  return paths
}

function handleFieldSelect(data: FieldPath) {
  if (multiMode.value) return // 多選模式下靠複選框
  // 單選：允許非葉子節點
  selectedFieldPath.value = data.path
}

function handleTreeCheck() {
  try {
    const nodes = (treeRef.value as any)?.getCheckedNodes?.(false) || []
    selectedFieldPaths.value = nodes.map((n: any) => n.path)
  } catch (e) {
    // ignore
  }
}

function handleConfirm() {
  if (selectionPreview.value) {
    emit('confirm', selectionPreview.value)
    emit('update:modelValue', false)
  }
}
</script>

<style scoped>
.selector-container { display: flex; gap: 20px; height: 60vh; border-top: 1px solid var(--el-border-color); border-bottom: 1px solid var(--el-border-color); padding: 10px 0; }
.column { flex: 1; display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid var(--el-border-color); padding-right: 20px; }
.column:last-child { border-right: none; padding-right: 0; }
.column.left { width: 60%; max-width: 780px; }
.list-container { margin-top: 10px; flex-grow: 1; }
.card-list { list-style: none; padding: 0; margin: 0; }
.card-list li { padding: 8px 12px; cursor: pointer; border-radius: 4px; }
.card-list li:hover { background-color: var(--el-fill-color-light); }
.card-list li.selected { background-color: var(--el-color-primary-light-9); color: var(--el-color-primary); font-weight: bold; }
.field-tree { margin-top: 10px; flex-grow: 1; overflow: auto; }
.empty-state { margin-top: 10px; color: var(--el-text-color-secondary); text-align: center; padding-top: 20px; }
.footer-container { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.selection-preview { font-size: 14px; color: var(--el-text-color-secondary); }
.mt8 { margin-top: 8px; }
.row-head { display: flex; align-items: center; justify-content: space-between; }
.right-tools { display: flex; align-items: center; gap: 8px; }
.adv-grid { display: flex; gap: 8px; align-items: center; }
.cond-list { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.cond-item { display: flex; gap: 8px; align-items: center; }
.hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
</style> 