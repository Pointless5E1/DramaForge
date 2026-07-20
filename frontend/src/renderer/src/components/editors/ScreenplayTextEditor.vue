<template>
  <div
    ref="screenplayEditorRef"
    class="screenplay-editor"
    tabindex="-1"
    @click.capture="handleEditorClickCapture"
    @keydown="handleEditorKeydown"
  >
    <div class="screenplay-toolbar">
      <div class="toolbar-left">
        <label class="waterfall-toggle">
          <el-switch
            v-model="waterfallEnabled"
            size="small"
            aria-label="跨片段捲動"
          />
          <span>跨片段捲動</span>
        </label>
        <div v-if="selectedBlockCount" class="selection-actions" aria-live="polite">
          <span>已選 {{ selectedBlockCount }} 段</span>
        </div>
      </div>
      <div class="toolbar-right">
        <el-button size="small" plain :icon="Download" @click="exportWordDocument">匯出 Word</el-button>
        <span class="line-count">{{ blocks.length }} 段 · {{ screenplayWordCount }} 字 · {{ screenplayPageCount }} 頁</span>
      </div>
    </div>

    <div
      v-if="selectionDragging && selectedBlockCount"
      class="drag-selection-badge"
      :style="{ left: `${selectionPointer.x + 16}px`, top: `${selectionPointer.y + 16}px` }"
      aria-hidden="true"
    >
      {{ selectionPointerMode === 'move' ? '移動' : '已選' }} {{ selectedBlockCount }} 段
    </div>

    <div v-if="scrollHintVisible" class="waterfall-scroll-hint" aria-hidden="true">
      <span
        v-for="tick in scrollHintTickCount"
        :key="tick"
        class="waterfall-scroll-hint__tick"
        :class="{ 'is-current': tick - 1 === activeScrollHintTick }"
      />
    </div>

    <div
      ref="editorPaneRef"
      class="block-editor-pane"
      @click="deactivateBlock"
      @scroll.passive="handleWaterfallScroll"
    >
      <section
        v-for="segment in previousSegments"
        :key="`previous-segment-${segment.id}`"
        :ref="el => setWaterfallPreviewRef('previous', segment.id, el)"
        class="segment-preview segment-preview-previous"
        :aria-label="`${segment.title}（唯讀）`"
      >
        <header class="segment-divider">
          <span class="segment-title">{{ segment.title }}</span>
          <span class="readonly-label">唯讀</span>
        </header>
        <div class="screenplay-preview waterfall-preview">
          <pre
            v-for="(block, index) in segment.blocks"
            :key="`previous-${segment.id}-${index}`"
            class="preview-line"
            :class="[`block-${block.type}`, { 'has-auto-gap-before': previewHasAutoBlankBefore(segment.blocks, index) }]"
          >{{ renderBlockText(block) }}</pre>
        </div>
      </section>

      <div ref="activeSegmentRef" class="active-segment-marker">
      <header class="segment-divider segment-divider-active">
        <span class="segment-title">{{ props.card.title }}</span>
        <span class="segment-state segment-state-active">編輯中</span>
      </header>
      <div v-if="!blocks.length" class="empty-state" @click.stop>
        <el-button type="primary" plain @click="addBlock('scene_heading')">新增第一個場景</el-button>
      </div>

      <div
        v-else
        class="block-list"
        :class="{
          'is-drag-selecting': selectionDragging && selectionPointerMode === 'select',
          'is-moving-blocks': selectionDragging && selectionPointerMode === 'move',
        }"
        @click="deactivateBlock"
      >
        <template v-for="(block, index) in blocks" :key="block.id">
          <div
            class="insert-row"
            :data-insert-index="index"
            :class="{
              'is-expanded': visibleInsertIndex === index,
              'is-move-target': selectionPointerMode === 'move' && moveDropIndex === index,
            }"
            @click.stop
          >
            <div class="insert-control-zone">
            <el-dropdown
              v-if="activeInsertIndex === index"
              :ref="element => setInsertDropdownRef(index, element)"
              class="insert-dropdown insert-trigger"
              trigger="click"
              placement="bottom"
              popper-class="screenplay-insert-dropdown-popper"
              :teleported="true"
              @command="command => handleInsertDropdownCommand(index, command)"
              @visible-change="visible => handleInsertDropdownVisibility(index, visible)"
            >
              <el-button
                class="insert-button"
                circle
                size="small"
                :icon="Plus"
                title="在此新增段落"
              />
              <template #dropdown>
                <el-dropdown-menu class="insert-dropdown-menu">
                  <template v-for="option in insertBlockMenuOptions" :key="option.value">
                    <el-popover
                      v-if="option.value === 'character' && option.children?.length"
                      placement="right-start"
                      trigger="hover"
                      width="auto"
                      :offset="8"
                      :show-arrow="false"
                      :show-after="60"
                      :hide-after="100"
                      :teleported="true"
                      popper-class="screenplay-character-submenu-popper"
                      @show="visibleCharacterSubmenuIndex = index"
                      @hide="visibleCharacterSubmenuIndex = null"
                    >
                      <template #reference>
                        <li
                          class="el-dropdown-menu__item insert-character-menu-item"
                          :class="{ 'is-submenu-open': visibleCharacterSubmenuIndex === index }"
                          role="menuitem"
                          tabindex="-1"
                        >
                          <span>{{ option.label }}</span>
                          <el-icon class="insert-submenu-arrow"><ArrowRight /></el-icon>
                        </li>
                      </template>
                      <div class="insert-character-popover-menu" role="menu">
                        <button
                          v-for="character in option.children"
                          :key="character.value"
                          type="button"
                          class="insert-character-option"
                          @click.stop="handleInsertDropdownCommand(index, character.value)"
                        >
                          {{ character.label }}
                        </button>
                      </div>
                    </el-popover>
                    <el-dropdown-item v-else :command="option.value">
                      {{ option.label }}
                    </el-dropdown-item>
                  </template>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-else
              class="insert-button insert-trigger"
              circle
              size="small"
              :icon="Plus"
              title="在此新增段落"
              @click="openInsertDropdown(index)"
            />
            </div>
          </div>

          <section
            class="screenplay-block"
            :data-block-id="block.id"
            :class="[
              `block-${block.type}`,
              {
                'is-active': activeBlockId === block.id,
                'is-selected': selectedBlockIds.has(block.id),
                'has-auto-gap-before': hasAutoBlankBefore(index),
              },
            ]"
            :aria-selected="selectedBlockIds.has(block.id)"
            @pointerdown="handleBlockPointerDown(block.id, $event)"
            @click.stop="handleBlockClick(block.id, $event)"
          >
            <template v-if="activeBlockId === block.id">
              <div class="block-topline" @click.stop>
                <el-select
                  v-model="block.type"
                  size="small"
                  class="block-type-select"
                  @change="touch"
                >
                  <el-option
                    v-for="option in blockTypeOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>

                <div class="block-actions">
                  <el-button
                    size="small"
                    text
                    :icon="ArrowUp"
                    :disabled="index === 0"
                    title="上移"
                    @click="moveBlock(index, -1)"
                  />
                  <el-button
                    size="small"
                    text
                    :icon="ArrowDown"
                    :disabled="index === blocks.length - 1"
                    title="下移"
                    @click="moveBlock(index, 1)"
                  />
                  <el-button
                    class="block-delete-button"
                    size="small"
                    text
                    :icon="Delete"
                    title="刪除"
                    @click="removeBlock(index)"
                  />
                </div>
              </div>

              <el-input
                v-if="block.type !== 'blank'"
                v-model="block.text"
                type="textarea"
                resize="none"
                :autosize="{ minRows: block.type === 'dialogue' || block.type === 'action' ? 2 : 1, maxRows: 8 }"
                :placeholder="placeholderFor(block.type)"
                class="block-input"
                @click.stop
                @blur="normalizeBlockText(block)"
                @input="touch"
              />
              <div v-else class="blank-editor-hint">空行</div>
            </template>

            <pre v-else class="block-preview"><span class="block-preview-text">{{ renderBlockText(block) }}</span></pre>
          </section>
        </template>

        <div
          class="insert-row"
          :data-insert-index="blocks.length"
          :class="{
            'is-expanded': visibleInsertIndex === blocks.length,
            'is-move-target': selectionPointerMode === 'move' && moveDropIndex === blocks.length,
          }"
          @click.stop
        >
          <div class="insert-control-zone">
          <el-dropdown
            v-if="activeInsertIndex === blocks.length"
            :ref="element => setInsertDropdownRef(blocks.length, element)"
            class="insert-dropdown insert-trigger"
            trigger="click"
            placement="bottom"
            popper-class="screenplay-insert-dropdown-popper"
            :teleported="true"
            @command="command => handleInsertDropdownCommand(blocks.length, command)"
            @visible-change="visible => handleInsertDropdownVisibility(blocks.length, visible)"
          >
            <el-button
              class="insert-button"
              circle
              size="small"
              :icon="Plus"
              title="在結尾新增段落"
            />
            <template #dropdown>
              <el-dropdown-menu class="insert-dropdown-menu">
                <template v-for="option in insertBlockMenuOptions" :key="option.value">
                  <el-popover
                    v-if="option.value === 'character' && option.children?.length"
                    placement="right-start"
                    trigger="hover"
                    width="auto"
                    :offset="8"
                    :show-arrow="false"
                    :show-after="60"
                    :hide-after="100"
                    :teleported="true"
                    popper-class="screenplay-character-submenu-popper"
                    @show="visibleCharacterSubmenuIndex = blocks.length"
                    @hide="visibleCharacterSubmenuIndex = null"
                  >
                    <template #reference>
                      <li
                        class="el-dropdown-menu__item insert-character-menu-item"
                        :class="{ 'is-submenu-open': visibleCharacterSubmenuIndex === blocks.length }"
                        role="menuitem"
                        tabindex="-1"
                      >
                        <span>{{ option.label }}</span>
                        <el-icon class="insert-submenu-arrow"><ArrowRight /></el-icon>
                      </li>
                    </template>
                    <div class="insert-character-popover-menu" role="menu">
                      <button
                        v-for="character in option.children"
                        :key="character.value"
                        type="button"
                        class="insert-character-option"
                        @click.stop="handleInsertDropdownCommand(blocks.length, character.value)"
                      >
                        {{ character.label }}
                      </button>
                    </div>
                  </el-popover>
                  <el-dropdown-item v-else :command="option.value">
                    {{ option.label }}
                  </el-dropdown-item>
                </template>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button
            v-else
            class="insert-button insert-trigger"
            circle
            size="small"
            :icon="Plus"
            title="在結尾新增段落"
            @click="openInsertDropdown(blocks.length)"
          />
          </div>
        </div>
      </div>
      </div>

      <section
        v-for="segment in nextSegments"
        :key="`next-segment-${segment.id}`"
        :ref="el => setWaterfallPreviewRef('next', segment.id, el)"
        class="segment-preview segment-preview-next"
        :aria-label="`${segment.title}（唯讀）`"
      >
        <header class="segment-divider">
          <span class="segment-title">{{ segment.title }}</span>
          <span class="readonly-label">唯讀</span>
        </header>
        <div class="screenplay-preview waterfall-preview">
          <pre
            v-for="(block, index) in segment.blocks"
            :key="`next-${segment.id}-${index}`"
            class="preview-line"
            :class="[`block-${block.type}`, { 'has-auto-gap-before': previewHasAutoBlankBefore(segment.blocks, index) }]"
          >{{ renderBlockText(block) }}</pre>
        </div>
      </section>
    </div>

    <InitialPromptDialog
      v-model:visible="showInitialPromptDialog"
      card-type-name="劇本片段正文"
      @confirm="handleStartGeneration"
      @cancel="showInitialPromptDialog = false"
    />

    <GenerationPanel
      ref="generationPanelRef"
      :visible="showGenerationPanel"
      @close="handleCloseGenerationPanel"
      @pause="handlePauseGeneration"
      @continue="handleContinueGeneration"
      @stop="handleStopGeneration"
      @restart="handleRestartGeneration"
    />

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowRight, ArrowUp, Delete, Download, Plus } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { generateWithInstructionStream } from '@renderer/api/generation'
import { getCardAIParams, getCardSchema } from '@renderer/api/setting'
import GenerationPanel from '@renderer/components/generation/GenerationPanel.vue'
import InitialPromptDialog from '@renderer/components/generation/InitialPromptDialog.vue'
import { InstructionExecutor } from '@renderer/services/instructionExecutor'
import { getContextTemplateByKind, type ContextTemplateKind, type ContextTemplates } from '@renderer/services/contextSlots'
import { resolveTemplate } from '@renderer/services/contextResolver'
import { useCardStore } from '@renderer/stores/useCardStore'
import { usePerCardAISettingsStore, type PerCardAIParams } from '@renderer/stores/usePerCardAISettingsStore'
import type { ConversationMessage, Instruction } from '@renderer/types/instruction'

type ScreenplayBlockType =
  | 'scene_heading'
  | 'action'
  | 'character'
  | 'parenthetical'
  | 'dialogue'
  | 'transition'
  | 'shot'
  | 'note'
  | 'blank'

interface ScreenplayBlock {
  id: string
  type: ScreenplayBlockType
  text: string
  character?: string | null
  scene_id?: string | null
}

interface PersistedScreenplayBlock {
  type: ScreenplayBlockType
  text: string
  character?: string | null
  scene_id?: string | null
}

const props = defineProps<{
  card: CardRead
  contextTemplates?: ContextTemplates
  generationContextKind?: ContextTemplateKind
}>()

const emit = defineEmits<{
  (e: 'update:dirty', value: boolean): void
  (e: 'activate-card', cardId: number): void
}>()

const cardStore = useCardStore()
const perCardStore = usePerCardAISettingsStore()
const { cards } = storeToRefs(cardStore)
const WATERFALL_PREFERENCE_KEY = 'dramaforge:screenplay-waterfall-enabled'
const waterfallEnabled = ref(localStorage.getItem(WATERFALL_PREFERENCE_KEY) !== 'false')
const scrollHintTickCount = 16
const scrollHintProgress = ref(0)
const scrollHintVisible = ref(false)
const activeScrollHintTick = computed(() => Math.min(
  scrollHintTickCount - 1,
  Math.round(scrollHintProgress.value * (scrollHintTickCount - 1)),
))

watch(waterfallEnabled, async (enabled) => {
  localStorage.setItem(WATERFALL_PREFERENCE_KEY, String(enabled))
  sessionStorage.removeItem('dramaforge:screenplay-waterfall-entry')
  waterfallSwitching = false
  waterfallPositioning = true
  await nextTick()
  const pane = editorPaneRef.value
  const active = activeSegmentRef.value
  if (pane && active) {
    pane.scrollTop = active.offsetTop
    lastWaterfallScrollTop = pane.scrollTop
  }
  requestAnimationFrame(() => {
    updateWaterfallScrollHint()
    waterfallPositioning = false
  })
})

const blockTypeOptions: Array<{ label: string; value: ScreenplayBlockType }> = [
  { label: '場景標題', value: 'scene_heading' },
  { label: '動作', value: 'action' },
  { label: '角色', value: 'character' },
  { label: '括註', value: 'parenthetical' },
  { label: '對白', value: 'dialogue' },
  { label: '轉場', value: 'transition' },
  { label: '鏡頭', value: 'shot' },
  { label: '備註', value: 'note' },
  { label: '空行', value: 'blank' },
]

interface InsertBlockMenuOption {
  label: string
  value: string
  children?: InsertBlockMenuOption[]
}

const participantCharacterNames = computed<string[]>(() => {
  const allCards = cards.value || []
  const outlineCard = allCards.find((card) => card.id === props.card.parent_id)
  const outlineContent = (outlineCard?.content || {}) as Record<string, unknown>
  const entityList = Array.isArray(outlineContent.entity_list) ? outlineContent.entity_list : []
  const cardByName = new Map<string, CardRead>()
  for (const card of allCards) {
    const content = (card.content || {}) as Record<string, unknown>
    const names = [card.title, content.name]
    for (const rawName of names) {
      const name = String(rawName || '').trim()
      if (name && !cardByName.has(name)) cardByName.set(name, card)
    }
  }

  const names: string[] = []
  for (const item of entityList) {
    const record = typeof item === 'object' && item ? (item as Record<string, unknown>) : null
    const name = String(record ? (record.name || record.title || '') : (item || '')).trim()
    if (!name) continue
    const explicitType = String(record?.entity_type || '').trim().toLowerCase()
    const entityCard = cardByName.get(name)
    const cardContent = (entityCard?.content || {}) as Record<string, unknown>
    const cardEntityType = String(cardContent.entity_type || '').trim().toLowerCase()
    const cardTypeName = String(entityCard?.card_type?.name || '')
    const isCharacter = explicitType === 'character'
      || explicitType.includes('角色')
      || cardEntityType === 'character'
      || cardEntityType.includes('角色')
      || cardTypeName.includes('角色')
    if (isCharacter && !names.includes(name)) names.push(name)
  }
  return names
})

const insertBlockMenuOptions = computed<InsertBlockMenuOption[]>(() => blockTypeOptions.map((option) => {
  if (option.value !== 'character' || !participantCharacterNames.value.length) {
    return { label: option.label, value: option.value }
  }
  return {
    label: option.label,
    value: option.value,
    children: participantCharacterNames.value.map((name) => ({
      label: name,
      value: `character-member:${name}`,
    })),
  }
}))

const blocks = ref<ScreenplayBlock[]>([])
const originalSignature = ref('')
const activeBlockId = ref<string | null>(null)
const selectedBlockIds = ref<Set<string>>(new Set())
const selectedBlockCount = computed(() => selectedBlockIds.value.size)
const activeInsertIndex = ref<number | null>(null)
const visibleInsertIndex = ref<number | null>(null)
const visibleCharacterSubmenuIndex = ref<number | null>(null)
const showInitialPromptDialog = ref(false)
const showGenerationPanel = ref(false)
const generationPanelRef = ref<InstanceType<typeof GenerationPanel>>()
const instructionExecutor = ref<InstructionExecutor | null>(null)
const conversationHistory = ref<ConversationMessage[]>([])
const currentAbortController = ref<AbortController | null>(null)
const aiGenerating = ref(false)
const editorPaneRef = ref<HTMLElement | null>(null)
const activeSegmentRef = ref<HTMLElement | null>(null)
const screenplayEditorRef = ref<HTMLElement | null>(null)
const waterfallPreviewRefs = new Map<number, HTMLElement>()
const insertDropdownRefs = new Map<number, { handleOpen?: () => void; handleClose?: () => void }>()
let waterfallSwitching = false
let waterfallPositioning = false
let lastWaterfallScrollTop = 0
let selectionPointerId: number | null = null
let selectionAnchorId: string | null = null
let lastSelectionTargetId: string | null = null
let selectionPointerStart = { x: 0, y: 0 }
let selectionPointerX = 0
let selectionPointerY = 0
let selectionPointerMoveFrame: number | null = null
const selectionPointer = ref({ x: 0, y: 0 })
const selectionDragging = ref(false)
const selectionPointerMode = ref<'select' | 'move' | null>(null)
const moveDropIndex = ref<number | null>(null)
let suppressReleasedDragClick = false
let selectionAutoScrollFrame: number | null = null

type WaterfallSegment = {
  id: number
  title: string
  blocks: ScreenplayBlock[]
}

const orderedScreenplayCards = computed(() => {
  const allCards = cards.value || []
  const byId = new Map(allCards.map(card => [card.id, card]))
  const currentParent = byId.get(props.card.parent_id || -1)
  const currentEpisode = Number((currentParent?.content as any)?.episode_number)

  const orderedCards = allCards
    .filter(card => card.card_type?.name === '劇本片段正文')
    .map(card => {
      const parent = byId.get(card.parent_id || -1)
      const parentContent = (parent?.content || {}) as any
      return {
        card,
        episode: Number(parentContent.episode_number),
        segment: Number(parentContent.segment_number),
        order: Number((card as any).display_order ?? 0),
      }
    })
    .filter(item => !Number.isFinite(currentEpisode) || item.episode === currentEpisode)
    .sort((a, b) => {
      const segmentDelta = (Number.isFinite(a.segment) ? a.segment : Number.MAX_SAFE_INTEGER)
        - (Number.isFinite(b.segment) ? b.segment : Number.MAX_SAFE_INTEGER)
      return segmentDelta || a.order - b.order || a.card.id - b.card.id
    })
    .map(item => item.card)

  const hasContent = (card: CardRead) => blocksFromContent(card.content).some(block =>
    block.type !== 'blank' && String(block.text || '').trim().length > 0
  )
  const firstContentIndex = orderedCards.findIndex(hasContent)
  if (firstContentIndex < 0) return []

  let lastContentIndex = orderedCards.length - 1
  while (lastContentIndex > firstContentIndex && !hasContent(orderedCards[lastContentIndex])) {
    lastContentIndex -= 1
  }
  return orderedCards.slice(firstContentIndex, lastContentIndex + 1)
})

const currentWaterfallIndex = computed(() => orderedScreenplayCards.value.findIndex(card => card.id === props.card.id))

function waterfallSegmentAt(index: number): WaterfallSegment | null {
  const card = orderedScreenplayCards.value[index]
  if (!card) return null
  return {
    id: card.id,
    title: card.title,
    blocks: blocksFromContent(card.content),
  }
}

const previousSegment = computed(() => !waterfallEnabled.value || currentWaterfallIndex.value < 0
  ? null
  : waterfallSegmentAt(currentWaterfallIndex.value - 1))
const nextSegment = computed(() => !waterfallEnabled.value || currentWaterfallIndex.value < 0
  ? null
  : waterfallSegmentAt(currentWaterfallIndex.value + 1))
const previousSegments = computed(() => {
  if (!waterfallEnabled.value || currentWaterfallIndex.value < 0) return []
  return Array.from(
    { length: Math.max(0, currentWaterfallIndex.value) },
    (_, index) => waterfallSegmentAt(index),
  ).filter((segment): segment is WaterfallSegment => Boolean(segment))
})
const nextSegments = computed(() => !waterfallEnabled.value || currentWaterfallIndex.value < 0
  ? []
  : Array.from(
    { length: Math.max(0, orderedScreenplayCards.value.length - currentWaterfallIndex.value - 1) },
    (_, offset) => waterfallSegmentAt(currentWaterfallIndex.value + offset + 1),
  ).filter((segment): segment is WaterfallSegment => Boolean(segment)))

function setWaterfallPreviewRef(_direction: 'previous' | 'next', cardId: number, element: any) {
  if (element instanceof HTMLElement) waterfallPreviewRefs.set(cardId, element)
  else waterfallPreviewRefs.delete(cardId)
}

function previewHasAutoBlankBefore(source: ScreenplayBlock[], index: number) {
  return shouldInsertBlankBetween(source[index - 1], source[index])
}

function visualLineHeight() {
  const pane = editorPaneRef.value
  if (!pane) return 24
  const sample = pane.querySelector<HTMLElement>('.preview-line, .block-preview')
  const parsed = sample ? Number.parseFloat(getComputedStyle(sample).lineHeight) : 0
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 24
}

function requestWaterfallCard(cardId: number, direction: 'previous' | 'next') {
  if (waterfallSwitching) return
  const pane = editorPaneRef.value
  const paneTop = pane?.getBoundingClientRect().top || 0
  const targetPreview = waterfallPreviewRefs.get(cardId)
  const anchorOffset = direction === 'next'
    ? (targetPreview?.getBoundingClientRect().top || paneTop) - paneTop
    : (targetPreview?.getBoundingClientRect().bottom || paneTop) - paneTop
  waterfallSwitching = true
  sessionStorage.setItem('dramaforge:screenplay-waterfall-entry', JSON.stringify({ cardId, direction, anchorOffset }))
  emit('activate-card', cardId)
}

function handleWaterfallScroll() {
  const pane = editorPaneRef.value
  updateWaterfallScrollHint()
  if (!waterfallEnabled.value || !pane || waterfallSwitching || waterfallPositioning) return
  const currentScrollTop = pane.scrollTop
  const direction = currentScrollTop > lastWaterfallScrollTop
    ? 'next'
    : currentScrollTop < lastWaterfallScrollTop
      ? 'previous'
      : null
  lastWaterfallScrollTop = currentScrollTop
  if (!direction) return
  const paneRect = pane.getBoundingClientRect()
  const threshold = visualLineHeight() * 10

  const nextPreview = nextSegment.value ? waterfallPreviewRefs.get(nextSegment.value.id) : null
  if (direction === 'next' && nextSegment.value && nextPreview) {
    const nextTop = nextPreview.getBoundingClientRect().top
    if (nextTop <= paneRect.bottom - threshold) {
      requestWaterfallCard(nextSegment.value.id, 'next')
      return
    }
  }

  const previousPreview = previousSegment.value ? waterfallPreviewRefs.get(previousSegment.value.id) : null
  if (direction === 'previous' && previousSegment.value && previousPreview) {
    const previousBottom = previousPreview.getBoundingClientRect().bottom
    if (previousBottom >= paneRect.top + threshold) {
      requestWaterfallCard(previousSegment.value.id, 'previous')
    }
  }
}

function updateWaterfallScrollHint() {
  const pane = editorPaneRef.value
  if (!pane) {
    scrollHintVisible.value = false
    scrollHintProgress.value = 0
    return
  }
  const maxScrollTop = Math.max(0, pane.scrollHeight - pane.clientHeight)
  scrollHintVisible.value = maxScrollTop > 1
  scrollHintProgress.value = maxScrollTop > 0
    ? Math.min(1, Math.max(0, pane.scrollTop / maxScrollTop))
    : 0
}

async function restoreWaterfallEntryPosition() {
  const raw = sessionStorage.getItem('dramaforge:screenplay-waterfall-entry')
  if (raw) sessionStorage.removeItem('dramaforge:screenplay-waterfall-entry')
  waterfallPositioning = true
  try {
    await nextTick()
    const pane = editorPaneRef.value
    const active = activeSegmentRef.value
    if (!pane || !active) return
    if (!raw) {
      pane.scrollTop = active.offsetTop
      return
    }
    const entry = JSON.parse(raw) as { cardId?: number; direction?: 'previous' | 'next'; anchorOffset?: number }
    if (entry.cardId !== props.card.id) {
      pane.scrollTop = active.offsetTop
      return
    }
    const anchorOffset = Number.isFinite(entry.anchorOffset) ? Number(entry.anchorOffset) : 0
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    const paneTop = pane.getBoundingClientRect().top
    const activeRect = active.getBoundingClientRect()
    const renderedAnchorOffset = entry.direction === 'next'
      ? activeRect.top - paneTop
      : activeRect.bottom - paneTop
    pane.scrollTop = Math.max(0, pane.scrollTop + renderedAnchorOffset - anchorOffset)
    lastWaterfallScrollTop = pane.scrollTop
  } catch {
    // Ignore stale navigation state and use the normal initial position.
  } finally {
    waterfallSwitching = false
    requestAnimationFrame(() => {
      if (editorPaneRef.value) lastWaterfallScrollTop = editorPaneRef.value.scrollTop
      updateWaterfallScrollHint()
      waterfallPositioning = false
    })
  }
}

const screenplayText = computed(() => serializeBlocks(blocks.value))
const screenplayWordCount = computed(() => blocks.value.reduce(
  (total, block) => total + (block.type === 'blank' ? 0 : String(block.text || '').replace(/\s/g, '').length),
  0,
))

function screenplayTextUnits(text: string): number {
  return Array.from(text).reduce((total, char) => {
    if (/\s/.test(char)) return total
    return total + (/^[\x00-\xff]$/.test(char) ? 0.5 : 1)
  }, 0)
}

function wrappedLineCount(text: string, charactersPerLine: number): number {
  const logicalLines = String(text || '').split(/\r?\n/)
  return logicalLines.reduce((total, line) => {
    const units = screenplayTextUnits(line)
    return total + Math.max(1, Math.ceil(units / charactersPerLine))
  }, 0)
}

const screenplayLineCount = computed(() => {
  let total = 0
  let previous: ScreenplayBlock | undefined

  for (const block of blocks.value) {
    if (shouldInsertBlankBetween(previous, block)) total += 1
    if (block.type === 'blank') {
      total += 1
    } else {
      const charactersPerLine = block.type === 'dialogue' ? 24 : 40
      total += wrappedLineCount(renderBlockText(block), charactersPerLine)
    }
    previous = block
  }

  return total
})

const screenplayPageCount = computed(() => Math.max(1, Math.ceil(screenplayLineCount.value / 45)))

function normalizeContent(content: any) {
  return typeof content === 'object' && content ? content : {}
}

function uid() {
  return `sp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function normalizeBlockType(value: any): ScreenplayBlockType {
  const allowed = new Set<ScreenplayBlockType>(blockTypeOptions.map(option => option.value))
  return allowed.has(value) ? value : 'action'
}

function makeBlock(type: ScreenplayBlockType = 'action', text = ''): ScreenplayBlock {
  return { id: uid(), type, text: stripBlockFormat(type, text) }
}

function persistedBlocks(): PersistedScreenplayBlock[] {
  return blocks.value.map((block) => ({
    type: block.type,
    text: block.type === 'blank' ? '' : stripBlockFormat(block.type, String(block.text || '').trimEnd()),
    character: block.character || undefined,
    scene_id: block.scene_id || undefined,
  }))
}

function signatureFromBlocks(source: ScreenplayBlock[]) {
  return JSON.stringify(source.map(block => ({
    type: block.type,
    text: block.type === 'blank' ? '' : stripBlockFormat(block.type, String(block.text || '').trimEnd()),
    character: block.character || null,
    scene_id: block.scene_id || null,
  })))
}

function blockTextFromAny(block: any) {
  if (typeof block?.text === 'string') return block.text
  if (typeof block?.name === 'string') return block.name
  if (typeof block?.content === 'string') return block.content
  return ''
}

function blocksFromLegacyLines(lines: any[]): ScreenplayBlock[] {
  if (!Array.isArray(lines)) return []
  return lines.map((line, index): ScreenplayBlock => ({
    id: `sp-loaded-${index}`,
    type: normalizeBlockType(line?.line_type || line?.type),
    text: stripBlockFormat(normalizeBlockType(line?.line_type || line?.type), typeof line?.text === 'string' ? line.text : ''),
    character: line?.character || null,
    scene_id: line?.scene_id || null,
  }))
}

function blocksFromContent(content: any): ScreenplayBlock[] {
  const normalized = normalizeContent(content)

  if (Array.isArray(normalized.blocks) && normalized.blocks.length) {
    return normalized.blocks.map((block: any, index: number): ScreenplayBlock => ({
      id: `sp-loaded-${index}`,
      type: normalizeBlockType(block?.type || block?.block_type || block?.line_type),
      text: stripBlockFormat(normalizeBlockType(block?.type || block?.block_type || block?.line_type), blockTextFromAny(block)),
      character: block?.character || null,
      scene_id: block?.scene_id || null,
    }))
  }

  if (typeof normalized.screenplay_text === 'string' && normalized.screenplay_text.trim()) {
    return parsePlainTextToBlocks(normalized.screenplay_text).map((block, index) => ({
      ...block,
      id: `sp-loaded-${index}`,
    }))
  }

  if (Array.isArray(normalized.lines) && normalized.lines.length) {
    return blocksFromLegacyLines(normalized.lines)
  }

  if (typeof normalized.content === 'string' && normalized.content.trim()) {
    return parsePlainTextToBlocks(normalized.content).map((block, index) => ({
      ...block,
      id: `sp-loaded-${index}`,
    }))
  }

  return []
}

function leadingSpaceCount(line: string): number {
  const match = line.match(/^ */)
  return match ? match[0].length : 0
}

function isSceneHeading(text: string): boolean {
  return /^(INT\.|EXT\.|INT\/EXT\.|I\/E\.|內景|外景)[\s.]/i.test(text)
}

function isTransition(text: string): boolean {
  return /^[A-Z \u4e00-\u9fff]+(TO:|：)$/.test(text) || /^(CUT TO:|FADE OUT\.|FADE IN:|DISSOLVE TO:)$/i.test(text)
}

function isLikelyCharacter(text: string): boolean {
  if (!text || text.length > 24) return false
  if (/[\。！？.!?，,]/.test(text)) return false
  return text === text.toUpperCase() || /^[\u4e00-\u9fffA-Z0-9（）()·\s]+$/.test(text)
}

function stripMatchingWrap(text: string, pairs: Array<[string, string]>): string {
  let normalized = String(text || '').trim()

  for (const [open, close] of pairs) {
    if (normalized.startsWith(open) && normalized.endsWith(close)) {
      return normalized.slice(open.length, normalized.length - close.length).trim()
    }
  }

  return normalized
}

function stripBlockFormat(type: ScreenplayBlockType, text: string): string {
  if (type === 'parenthetical') {
    return stripMatchingWrap(text, [
      ['（', '）'],
      ['(', ')'],
    ])
  }

  if (type === 'dialogue') {
    return stripMatchingWrap(text, [
      ['「', '」'],
    ])
  }

  return String(text || '').trimEnd()
}

function parsePlainTextToBlocks(text: string): ScreenplayBlock[] {
  const parsed: ScreenplayBlock[] = []
  let currentCharacter: string | null = null

  for (const rawLine of (text || '').split(/\r?\n/)) {
    const indent = leadingSpaceCount(rawLine)
    const trimmed = rawLine.trim()

    if (!trimmed) {
      parsed.push(makeBlock('blank'))
      continue
    }

    if (/^\[\[.*\]\]$/.test(trimmed)) {
      parsed.push(makeBlock('note', trimmed.replace(/^\[\[|\]\]$/g, '')))
      continue
    }

    if (trimmed.startsWith('# ')) {
      parsed.push(makeBlock('shot', trimmed.slice(2)))
      continue
    }

    if (isSceneHeading(trimmed)) {
      currentCharacter = null
      parsed.push(makeBlock('scene_heading', trimmed))
      continue
    }

    if (isTransition(trimmed)) {
      currentCharacter = null
      parsed.push(makeBlock('transition', trimmed))
      continue
    }

    if (indent >= 18 && isLikelyCharacter(trimmed)) {
      currentCharacter = trimmed
      parsed.push(makeBlock('character', trimmed))
      continue
    }

    if (indent >= 12 && /^[（(].+[）)]$/.test(trimmed)) {
      parsed.push({ ...makeBlock('parenthetical', stripBlockFormat('parenthetical', trimmed)), character: currentCharacter })
      continue
    }

    if (indent >= 8) {
      parsed.push({ ...makeBlock('dialogue', stripBlockFormat('dialogue', trimmed)), character: currentCharacter })
      continue
    }

    currentCharacter = null
    parsed.push(makeBlock('action', trimmed))
  }

  return parsed
}

function formatBlock(block: ScreenplayBlock | PersistedScreenplayBlock): string {
  const text = stripBlockFormat(block.type, String(block.text || '').trimEnd())
  switch (block.type) {
    case 'blank':
      return ''
    case 'scene_heading':
      return text.toUpperCase()
    case 'character':
      return `                    ${text.toUpperCase()}`
    case 'parenthetical':
      return `                    （${text}）`
    case 'dialogue':
      return `          「${text}」`
    case 'transition':
      return `                              ${text.toUpperCase()}`
    case 'shot':
      return `# ${text}`
    case 'note':
      return `[[${text}]]`
    case 'action':
    default:
      return text
  }
}

function renderBlockText(block: ScreenplayBlock | PersistedScreenplayBlock) {
  const text = stripBlockFormat(block.type, String(block.text || '').trimEnd())
  switch (block.type) {
    case 'blank':
      return ' '
    case 'scene_heading':
      return text.toUpperCase()
    case 'character':
      return text.toUpperCase()
    case 'transition':
      return text.toUpperCase()
    case 'shot':
      return `# ${text}`
    case 'note':
      return `[[${text}]]`
    case 'parenthetical':
      return `（${text}）`
    case 'dialogue':
      return `「${text}」`
    case 'action':
    default:
      return text
  }
}

function shouldInsertBlankBetween(
  previous: ScreenplayBlock | PersistedScreenplayBlock | undefined,
  current: ScreenplayBlock | PersistedScreenplayBlock
) {
  if (!previous || previous.type === 'blank' || current.type === 'blank') return false
  if (previous.type === 'action' && current.type === 'action') return false
  if (previous.type === 'character' && (current.type === 'parenthetical' || current.type === 'dialogue')) return false
  if (
    (previous.type === 'parenthetical' || previous.type === 'dialogue') &&
    (current.type === 'parenthetical' || current.type === 'dialogue')
  ) {
    return false
  }
  return true
}

function hasAutoBlankBefore(index: number) {
  if (index <= 0) return false
  return shouldInsertBlankBetween(blocks.value[index - 1], blocks.value[index])
}

function serializeBlocks(source: Array<ScreenplayBlock | PersistedScreenplayBlock>): string {
  const lines: string[] = []
  let previous: ScreenplayBlock | PersistedScreenplayBlock | undefined

  for (const block of source) {
    if (shouldInsertBlankBetween(previous, block)) lines.push('')
    lines.push(formatBlock(block))
    previous = block
  }

  return lines.join('\n').trimEnd()
}

function buildLegacyLines(source: PersistedScreenplayBlock[]) {
  const textLines = serializeBlocks(source).split('\n')
  const lineTypes: Array<{ line_type: ScreenplayBlockType; character?: string | null; scene_id?: string | null }> = []
  let previous: PersistedScreenplayBlock | undefined

  for (const block of source) {
    if (shouldInsertBlankBetween(previous, block)) {
      lineTypes.push({ line_type: 'blank' })
    }
    lineTypes.push({ line_type: block.type, character: block.character || null, scene_id: block.scene_id || null })
    previous = block
  }

  return textLines.map((_, index) => ({
    line_number: index + 1,
    line_type: lineTypes[index]?.line_type || 'action',
    character: lineTypes[index]?.character || null,
    scene_id: lineTypes[index]?.scene_id || null,
  }))
}

function escapeHtml(text: string): string {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function inlineCss(style: Record<string, string>) {
  return Object.entries(style)
    .map(([key, value]) => `${key}:${value}`)
    .join(';')
}

function richParagraphStyle(block: ScreenplayBlock | PersistedScreenplayBlock, hasGapBefore: boolean) {
  const base: Record<string, string> = {
    'font-family': "'標楷體', 'DFKai-SB', BiauKai, serif",
    'font-size': '12pt',
    'line-height': '15.68pt',
    margin: hasGapBefore ? '12pt 0 0 0' : '0',
    'white-space': 'pre-wrap',
    'mso-line-height-rule': 'exactly',
    'mso-pagination': 'none',
  }

  switch (block.type) {
    case 'character':
      return inlineCss({
        ...base,
        'text-align': 'center',
        'text-transform': 'uppercase',
      })
    case 'dialogue':
      return inlineCss({
        ...base,
        'margin-left': '1.35in',
        'margin-right': '1.35in',
        'text-align': 'center',
      })
    case 'parenthetical':
      return inlineCss({
        ...base,
        'text-align': 'center',
      })
    case 'transition':
      return inlineCss({
        ...base,
        'text-align': 'right',
        'font-weight': '700',
      })
    case 'scene_heading':
      return inlineCss({
        ...base,
        'font-weight': '700',
        'text-transform': 'uppercase',
      })
    default:
      return inlineCss(base)
  }
}

function buildScreenplayHtml(source: Array<ScreenplayBlock | PersistedScreenplayBlock>) {
  const paragraphs: string[] = []
  let previous: ScreenplayBlock | PersistedScreenplayBlock | undefined

  for (const block of source) {
    if (shouldInsertBlankBetween(previous, block)) {
      paragraphs.push(`<p style="${richParagraphStyle({ type: 'blank', text: '' }, false)}"><br></p>`)
    }
    const text = block.type === 'blank'
      ? '<br>'
      : escapeHtml(renderBlockText(block)).replace(/\r?\n/g, '<br>')
    paragraphs.push(`<p style="${richParagraphStyle(block, false)}">${text}</p>`)
    previous = block
  }

  return [
    '<!doctype html>',
    '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">',
    '<head>',
    '<meta charset="utf-8">',
    '<style>',
    '@page Section1 { size: 595.3pt 841.9pt; margin: 63.8pt 56.7pt 63.8pt 56.7pt; mso-header-margin: 0pt; mso-footer-margin: 0pt; }',
    'div.Section1 { page: Section1; }',
    'body { margin: 0; font-family: "標楷體", "DFKai-SB", BiauKai, serif; font-size: 12pt; line-height: 15.68pt; color: #111; }',
    'p { margin: 0; }',
    '</style>',
    '</head>',
    '<body style="margin:0;font-family:\'標楷體\',\'DFKai-SB\',BiauKai,serif;font-size:12pt;line-height:15.68pt;color:#111;">',
    '<div class="Section1" style="width:17cm;font-family:\'標楷體\',\'DFKai-SB\',BiauKai,serif;">',
    paragraphs.join(''),
    '</div>',
    '</body>',
    '</html>',
  ].join('')
}

function safeFilenameSegment(value: string) {
  return (value || 'screenplay')
    .trim()
    .replace(/[<>:"/\\|?*]/g, '_')
    .replace(/\s+/g, '_')
    .slice(0, 80) || 'screenplay'
}

function triggerDocumentDownload(content: string, filename: string) {
  const blob = new Blob([content], { type: 'application/msword;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

function placeholderFor(type: ScreenplayBlockType) {
  switch (type) {
    case 'scene_heading':
      return 'INT. 觀瀾大樓測評室 - 日'
    case 'character':
      return '林知夏'
    case 'parenthetical':
      return '壓低聲音'
    case 'dialogue':
      return '所以，這份測評不是評估我，而是在替你們找藉口？'
    case 'transition':
      return 'CUT TO:'
    case 'shot':
      return '近景：測評單上的紅色標記'
    case 'note':
      return '必要製作備註'
    case 'action':
    default:
      return '林知夏把測評單推回桌面，紙角碰到錄音筆。'
  }
}

function touch() {
  emit('update:dirty', signatureFromBlocks(blocks.value) !== originalSignature.value)
}

function clearBlockSelection(): void {
  selectedBlockIds.value = new Set()
  selectionAnchorId = null
  lastSelectionTargetId = null
}

function selectionRange(anchorId: string, targetId: string): Set<string> {
  const anchorIndex = blocks.value.findIndex(block => block.id === anchorId)
  const targetIndex = blocks.value.findIndex(block => block.id === targetId)
  if (anchorIndex < 0 || targetIndex < 0) return new Set()
  const start = Math.min(anchorIndex, targetIndex)
  const end = Math.max(anchorIndex, targetIndex)
  return new Set(blocks.value.slice(start, end + 1).map(block => block.id))
}

function isBlockControl(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return Boolean(
    target.closest('input, textarea, select, button, [contenteditable="true"], .el-select')
  )
}

function blockIdAtPoint(x: number, y: number): string | null {
  const paneRect = editorPaneRef.value?.getBoundingClientRect()
  const listRect = activeSegmentRef.value
    ?.querySelector<HTMLElement>('.block-list')
    ?.getBoundingClientRect()
  const hitX = listRect ? Math.max(listRect.left + 1, Math.min(listRect.right - 1, x)) : x
  const hitY = paneRect ? Math.max(paneRect.top + 1, Math.min(paneRect.bottom - 1, y)) : y
  const element = document.elementFromPoint(hitX, hitY)
  const block = element?.closest<HTMLElement>('.screenplay-block[data-block-id]')
  if (!block || !activeSegmentRef.value?.contains(block)) return null
  return block.dataset.blockId || null
}

function updateDraggedSelection(x: number, y: number): void {
  if (!selectionAnchorId) return
  const targetId = blockIdAtPoint(x, y)
  if (!targetId || targetId === lastSelectionTargetId) return
  lastSelectionTargetId = targetId
  selectedBlockIds.value = selectionRange(selectionAnchorId, targetId)
}

function moveInsertionIndexAtPoint(y: number): number {
  const blockElements = activeSegmentRef.value?.querySelectorAll<HTMLElement>(
    '.screenplay-block[data-block-id]'
  )
  if (!blockElements?.length) return 0
  for (const element of blockElements) {
    const id = element.dataset.blockId
    const index = blocks.value.findIndex((block) => block.id === id)
    if (index < 0) continue
    const rect = element.getBoundingClientRect()
    if (y < rect.top + rect.height / 2) return index
  }
  return blocks.value.length
}

function updateMoveDropIndex(y: number): void {
  const nextIndex = moveInsertionIndexAtPoint(y)
  if (moveDropIndex.value !== nextIndex) moveDropIndex.value = nextIndex
}

function flushBlockPointerMove(): void {
  selectionPointerMoveFrame = null
  selectionPointer.value = { x: selectionPointerX, y: selectionPointerY }
  if (selectionPointerMode.value === 'move') updateMoveDropIndex(selectionPointerY)
  else updateDraggedSelection(selectionPointerX, selectionPointerY)
}

function scheduleBlockPointerMove(): void {
  if (selectionPointerMoveFrame !== null) return
  selectionPointerMoveFrame = requestAnimationFrame(flushBlockPointerMove)
}

function applySelectedBlockMove(): void {
  const rawDropIndex = moveDropIndex.value
  const selected = selectedBlockIds.value
  if (rawDropIndex === null || !selected.size) return
  const moving = blocks.value.filter((block) => selected.has(block.id))
  const remaining = blocks.value.filter((block) => !selected.has(block.id))
  const removedBeforeDrop = blocks.value
    .slice(0, rawDropIndex)
    .filter((block) => selected.has(block.id)).length
  const insertionIndex = Math.max(0, Math.min(remaining.length, rawDropIndex - removedBeforeDrop))
  const reordered = [
    ...remaining.slice(0, insertionIndex),
    ...moving,
    ...remaining.slice(insertionIndex),
  ]
  const orderChanged = reordered.some((block, index) => block.id !== blocks.value[index]?.id)
  if (!orderChanged) return
  blocks.value = reordered
  touch()
}

function stopSelectionAutoScroll(): void {
  if (selectionAutoScrollFrame !== null) cancelAnimationFrame(selectionAutoScrollFrame)
  selectionAutoScrollFrame = null
}

function runSelectionAutoScroll(): void {
  stopSelectionAutoScroll()
  const step = (): void => {
    const pane = editorPaneRef.value
    if (!selectionDragging.value || !pane) {
      selectionAutoScrollFrame = null
      return
    }
    const rect = pane.getBoundingClientRect()
    const edge = 52
    let delta = 0
    if (selectionPointerY < rect.top + edge) {
      delta = -Math.ceil((rect.top + edge - selectionPointerY) / 5)
    } else if (selectionPointerY > rect.bottom - edge) {
      delta = Math.ceil((selectionPointerY - (rect.bottom - edge)) / 5)
    }
    if (delta) {
      pane.scrollTop += Math.max(-18, Math.min(18, delta))
      if (selectionPointerMode.value === 'move') updateMoveDropIndex(selectionPointerY)
      else updateDraggedSelection(selectionPointerX, selectionPointerY)
    }
    selectionAutoScrollFrame = requestAnimationFrame(step)
  }
  selectionAutoScrollFrame = requestAnimationFrame(step)
}

function finishBlockPointerSelection(event?: PointerEvent): void {
  if (selectionPointerId === null || (event && event.pointerId !== selectionPointerId)) return
  if (event) {
    selectionPointerX = event.clientX
    selectionPointerY = event.clientY
  }
  window.removeEventListener('pointermove', handleBlockPointerMove)
  window.removeEventListener('pointerup', finishBlockPointerSelection)
  window.removeEventListener('pointercancel', finishBlockPointerSelection)
  stopSelectionAutoScroll()
  if (selectionPointerMoveFrame !== null) cancelAnimationFrame(selectionPointerMoveFrame)
  selectionPointerMoveFrame = null
  selectionPointerId = null
  lastSelectionTargetId = null
  if (selectionDragging.value) {
    flushBlockPointerMove()
    if (selectionPointerMode.value === 'move') applySelectedBlockMove()
    suppressReleasedDragClick = true
    activeBlockId.value = null
    activeInsertIndex.value = null
    visibleInsertIndex.value = null
  }
  selectionDragging.value = false
  selectionPointerMode.value = null
  moveDropIndex.value = null
}

function handleBlockPointerMove(event: PointerEvent): void {
  if (event.pointerId !== selectionPointerId || !selectionAnchorId) return
  selectionPointerX = event.clientX
  selectionPointerY = event.clientY
  if (!selectionDragging.value) {
    const distance = Math.hypot(
      event.clientX - selectionPointerStart.x,
      event.clientY - selectionPointerStart.y
    )
    if (distance < 6) return
    selectionDragging.value = true
    window.getSelection()?.removeAllRanges()
    if (selectionPointerMode.value === 'move') updateMoveDropIndex(event.clientY)
    else selectedBlockIds.value = new Set([selectionAnchorId])
    runSelectionAutoScroll()
  }
  event.preventDefault()
  scheduleBlockPointerMove()
}

function handleBlockPointerDown(blockId: string, event: PointerEvent): void {
  if (event.button !== 0 || isBlockControl(event.target)) return
  finishBlockPointerSelection()
  suppressReleasedDragClick = false
  screenplayEditorRef.value?.focus({ preventScroll: true })
  selectionPointerId = event.pointerId
  selectionAnchorId = blockId
  lastSelectionTargetId = blockId
  selectionPointerMode.value = selectedBlockIds.value.has(blockId) ? 'move' : 'select'
  moveDropIndex.value = null
  selectionPointerStart = { x: event.clientX, y: event.clientY }
  selectionPointerX = event.clientX
  selectionPointerY = event.clientY
  selectionPointer.value = { x: event.clientX, y: event.clientY }
  selectionDragging.value = false
  window.addEventListener('pointermove', handleBlockPointerMove, { passive: false })
  window.addEventListener('pointerup', finishBlockPointerSelection)
  window.addEventListener('pointercancel', finishBlockPointerSelection)
}

function handleBlockClick(blockId: string, event: MouseEvent): void {
  if (suppressReleasedDragClick) {
    suppressReleasedDragClick = false
    return
  }
  if (event.ctrlKey || event.metaKey) {
    const next = new Set(selectedBlockIds.value)
    if (next.has(blockId)) next.delete(blockId)
    else next.add(blockId)
    selectedBlockIds.value = next
    selectionAnchorId = blockId
    activeBlockId.value = null
    return
  }
  if (event.shiftKey && selectionAnchorId) {
    selectedBlockIds.value = selectionRange(selectionAnchorId, blockId)
    activeBlockId.value = null
    return
  }
  if (selectedBlockIds.value.has(blockId)) return
  clearBlockSelection()
  activateBlock(blockId)
}

function handleEditorClickCapture(event: MouseEvent): void {
  if (!suppressReleasedDragClick) return
  suppressReleasedDragClick = false
  event.preventDefault()
  event.stopPropagation()
}

function handleOutsideSelectionPointerDown(event: PointerEvent): void {
  if (selectionPointerId === null) suppressReleasedDragClick = false
  if (!selectedBlockIds.value.size || selectionDragging.value) return
  if (!(event.target instanceof Element)) return
  if (event.target.closest('.screenplay-block.is-selected, .selection-actions')) return
  clearBlockSelection()
}

function activateBlock(blockId: string) {
  activeBlockId.value = blockId
}

function deactivateBlock() {
  activeBlockId.value = null
  clearBlockSelection()
}

function normalizeBlockText(block: ScreenplayBlock) {
  if (block.type === 'blank') return
  const normalized = stripBlockFormat(block.type, block.text)
  if (normalized === block.text) return
  block.text = normalized
  touch()
}

function addBlock(type: ScreenplayBlockType) {
  const block = makeBlock(type)
  blocks.value.push(block)
  activeBlockId.value = block.id
  touch()
}

function insertBlockAt(index: number, type: ScreenplayBlockType, text = '') {
  const block = makeBlock(type, text)
  if (type === 'character' && text) block.character = text
  blocks.value.splice(index, 0, block)
  activeBlockId.value = block.id
  touch()
}

function insertBlockCommandAt(index: number, command: unknown) {
  insertBlockAt(index, normalizeBlockType(command))
}

function setInsertDropdownRef(index: number, element: unknown): void {
  const dropdown = element as { handleOpen?: () => void; handleClose?: () => void } | null
  if (dropdown) insertDropdownRefs.set(index, dropdown)
  else insertDropdownRefs.delete(index)
}

async function openInsertDropdown(index: number): Promise<void> {
  activeInsertIndex.value = index
  await nextTick()
  insertDropdownRefs.get(index)?.handleOpen?.()
}

function handleInsertDropdownCommand(index: number, value: unknown): void {
  insertDropdownRefs.get(index)?.handleClose?.()
  activeInsertIndex.value = null
  visibleInsertIndex.value = null
  visibleCharacterSubmenuIndex.value = null
  const command = String(value || '')
  if (!command) return
  if (command.startsWith('character-member:')) {
    insertBlockAt(index, 'character', command.slice('character-member:'.length))
    return
  }
  insertBlockCommandAt(index, command)
}

function handleInsertDropdownVisibility(index: number, visible: boolean): void {
  visibleInsertIndex.value = visible ? index : null
  if (!visible) {
    activeInsertIndex.value = null
    visibleCharacterSubmenuIndex.value = null
  }
}

function removeBlock(index: number) {
  const removed = blocks.value[index]
  blocks.value.splice(index, 1)
  if (removed && selectedBlockIds.value.has(removed.id)) {
    const next = new Set(selectedBlockIds.value)
    next.delete(removed.id)
    selectedBlockIds.value = next
  }
  if (removed?.id === activeBlockId.value) {
    activeBlockId.value = blocks.value[index]?.id || blocks.value[index - 1]?.id || null
  }
  touch()
}

function removeSelectedBlocks(): void {
  if (!selectedBlockIds.value.size) return
  const selected = selectedBlockIds.value
  blocks.value = blocks.value.filter(block => !selected.has(block.id))
  if (activeBlockId.value && selected.has(activeBlockId.value)) activeBlockId.value = null
  activeInsertIndex.value = null
  visibleInsertIndex.value = null
  clearBlockSelection()
  touch()
  screenplayEditorRef.value?.focus({ preventScroll: true })
}

function handleEditorKeydown(event: KeyboardEvent): void {
  if (!selectedBlockIds.value.size || (event.key !== 'Delete' && event.key !== 'Backspace')) return
  if (isBlockControl(event.target)) return
  event.preventDefault()
  removeSelectedBlocks()
}

function moveBlock(index: number, delta: number) {
  const nextIndex = index + delta
  if (nextIndex < 0 || nextIndex >= blocks.value.length) return
  const [block] = blocks.value.splice(index, 1)
  blocks.value.splice(nextIndex, 0, block)
  clearBlockSelection()
  activeBlockId.value = block.id
  touch()
}

function exportWordDocument() {
  try {
    const html = buildScreenplayHtml(blocks.value)
    const filename = `${safeFilenameSegment(props.card.title)}.doc`
    triggerDocumentDownload(html, filename)
    ElMessage.success('已匯出劇本 Word 文件')
  } catch (error) {
    console.error('Export screenplay document failed:', error)
    ElMessage.error('匯出失敗')
  }
}

function contentFromBlocks() {
  const nextBlocks = persistedBlocks()
  const text = serializeBlocks(nextBlocks)
  return {
    ...normalizeContent(props.card.content),
    format_version: 'screenplay-doc-v1',
    blocks: nextBlocks,
    screenplay_text: text,
    lines: buildLegacyLines(nextBlocks),
  }
}

function applyGeneratedContent(content: any) {
  const nextContent = {
    ...normalizeContent(props.card.content),
    ...normalizeContent(content),
  }
  blocks.value = blocksFromContent(nextContent)
  activeBlockId.value = null
  clearBlockSelection()
  touch()
}

function getContent() {
  return contentFromBlocks()
}

function getReviewTarget() {
  const text = screenplayText.value.trim()
  return {
    targetField: 'content.screenplay_text',
    targetText: text,
    snapshot: text,
  }
}

function buildInitialGenerationData(useExistingContent: boolean) {
  const base = {
    ...normalizeContent(props.card.content),
    ...contentFromBlocks(),
    format_version: 'screenplay-doc-v1',
  }

  if (!useExistingContent) {
    delete (base as any).blocks
    delete (base as any).screenplay_text
    delete (base as any).lines
  }

  return base
}

function getResolvedGenerationContext() {
  const template = getContextTemplateByKind(
    props.card,
    props.contextTemplates,
    props.generationContextKind,
    'generation',
  )
  const currentCardForResolve = { ...props.card, content: contentFromBlocks() }
  return resolveTemplate({ template, cards: cards.value, currentCard: currentCardForResolve as any })
}

function getRelationGraphScope() {
  const outlineCard = (cards.value || []).find(card => card.id === props.card.parent_id)
  const outlineContent = (outlineCard?.content || {}) as Record<string, unknown>
  const rawEntityList = Array.isArray(outlineContent.entity_list) ? outlineContent.entity_list : []
  const participants = rawEntityList
    .map((item) => String(
      typeof item === 'object' && item
        ? ((item as Record<string, unknown>).name || (item as Record<string, unknown>).title || '')
        : (item || ''),
    ).trim())
    .filter((name, index, all) => Boolean(name) && all.indexOf(name) === index)

  const episodeNumber = Number(outlineContent.episode_number)
  const segmentNumber = Number(outlineContent.segment_number)
  return {
    project_id: Number(props.card.project_id) || undefined,
    volume_number: Number.isFinite(episodeNumber) ? episodeNumber : undefined,
    chapter_number: Number.isFinite(segmentNumber) ? segmentNumber : undefined,
    participants,
  }
}

function wrapReferenceContext(contextInfo: string) {
  const trimmed = String(contextInfo || '').trim()
  if (!trimmed) return ''
  const structuredMarks = ['【引用上下文】', '【參考上下文】', '【事實子圖】', '【已知事實子圖】']
  if (structuredMarks.some(mark => trimmed.includes(mark))) return trimmed
  return `【引用上下文】\n${trimmed}`
}

async function resolveAIParams(): Promise<PerCardAIParams> {
  const cached = perCardStore.getByCardId(props.card.id)
  if (cached?.llm_config_id) return cached

  const resp = await getCardAIParams(props.card.id)
  const effective = resp?.effective_params || {}
  if (effective && Object.keys(effective).length) {
    perCardStore.setForCard(props.card.id, { ...effective })
  }
  return effective
}

function formatInstructionAction(instruction: Instruction): string {
  if (instruction.op === 'set') return `設置 ${instruction.path}`
  if (instruction.op === 'append') return `添加到 ${instruction.path}`
  if (instruction.op === 'done') return '生成完成'
  return '執行指令'
}

function startGeneration() {
  showInitialPromptDialog.value = true
}

async function handleStartGeneration(userPrompt: string, useExistingContent: boolean) {
  const params = await resolveAIParams()
  if (!params?.llm_config_id) {
    ElMessage.error('請先設定有效的模型ID')
    return
  }

  const schemaResp = await getCardSchema(props.card.id)
  const effectiveSchema = schemaResp?.effective_schema || schemaResp?.json_schema
  if (!effectiveSchema) {
    ElMessage.error('未找到此卡片的結構（Schema）')
    return
  }

  const initialData = buildInitialGenerationData(useExistingContent)
  instructionExecutor.value = new InstructionExecutor(initialData)
  conversationHistory.value = []
  showGenerationPanel.value = true
  await nextTick()
  generationPanelRef.value?.reset()
  if (userPrompt) generationPanelRef.value?.addMessage('user', userPrompt)
  generationPanelRef.value?.startGeneration()

  await performScreenplayGeneration(userPrompt, effectiveSchema, params, useExistingContent)
}

async function performScreenplayGeneration(
  userPrompt: string,
  schema: any,
  params: PerCardAIParams,
  useExistingContent: boolean,
) {
  currentAbortController.value = new AbortController()
  aiGenerating.value = true

  try {
    const relationGraphScope = getRelationGraphScope()
    await generateWithInstructionStream(
      {
        llm_config_id: params.llm_config_id!,
        user_prompt: userPrompt,
        response_model_schema: schema,
        current_data: instructionExecutor.value?.getData() || buildInitialGenerationData(useExistingContent),
        conversation_context: conversationHistory.value,
        generation_config: {
          mode: 'instruction_stream',
          custom: { pipeline: 'screenplay_text_then_normalize' },
        },
        context_info: wrapReferenceContext(getResolvedGenerationContext()),
        ...relationGraphScope,
        prompt_template: params.prompt_name,
        temperature: params.temperature,
        max_tokens: params.max_tokens,
        timeout: params.timeout,
      },
      {
        onThinking: text => generationPanelRef.value?.addMessage('thinking', text),
        onInstruction: (instruction: Instruction) => {
          instructionExecutor.value?.execute(instruction)
          generationPanelRef.value?.addMessage('action', formatInstructionAction(instruction))
          generationPanelRef.value?.incrementCompletedFields()
        },
        onWarning: text => generationPanelRef.value?.addMessage('warning', text),
        onError: text => {
          generationPanelRef.value?.addMessage('error', text)
          generationPanelRef.value?.finishGeneration(false, text)
          ElMessage.error(text || '生成失敗')
        },
        onDone: (success, message, finalData) => {
          if (success) {
            if (finalData) applyGeneratedContent(finalData)
            generationPanelRef.value?.finishGeneration(true, message || '生成完成')
            ElMessage.success('劇本片段正文生成完成')
          } else {
            generationPanelRef.value?.finishGeneration(false, message || '生成失敗')
          }
        },
      },
      currentAbortController.value.signal,
    )
  } finally {
    aiGenerating.value = false
    currentAbortController.value = null
  }
}

function handleCloseGenerationPanel() {
  showGenerationPanel.value = false
  currentAbortController.value?.abort()
  currentAbortController.value = null
  aiGenerating.value = false
}

function handlePauseGeneration() {
  currentAbortController.value?.abort()
  currentAbortController.value = null
  aiGenerating.value = false
}

async function handleContinueGeneration(userMessage: string) {
  conversationHistory.value.push({ role: 'user', content: userMessage })
  const params = await resolveAIParams()
  if (!params?.llm_config_id) {
    ElMessage.error('請先設定有效的模型ID')
    return
  }
  const schemaResp = await getCardSchema(props.card.id)
  const effectiveSchema = schemaResp?.effective_schema || schemaResp?.json_schema
  if (!effectiveSchema) {
    ElMessage.error('未找到此卡片的結構（Schema）')
    return
  }
  await performScreenplayGeneration(userMessage, effectiveSchema, params, true)
}

function handleStopGeneration() {
  handleCloseGenerationPanel()
}

function handleRestartGeneration() {
  instructionExecutor.value = new InstructionExecutor(buildInitialGenerationData(true))
  conversationHistory.value = []
  showGenerationPanel.value = false
  showInitialPromptDialog.value = true
}

watch(
  () => props.card,
  (nextCard) => {
    finishBlockPointerSelection()
    blocks.value = blocksFromContent(nextCard?.content)
    activeBlockId.value = null
    activeInsertIndex.value = null
    visibleInsertIndex.value = null
    clearBlockSelection()
    originalSignature.value = signatureFromBlocks(blocks.value)
    emit('update:dirty', false)
    void restoreWaterfallEntryPosition()
  },
  { immediate: true }
)

watch(
  blocks,
  () => {
    touch()
  },
  { deep: true }
)

async function handleSave(newTitle?: string) {
  const effectiveTitle = typeof newTitle === 'string' && newTitle.trim()
    ? newTitle.trim()
    : props.card.title

  const nextContent = contentFromBlocks()
  const updatePayload: CardUpdate = {
    title: effectiveTitle,
    content: nextContent as any,
    needs_confirmation: false,
  }

  await cardStore.modifyCard(props.card.id, updatePayload)
  originalSignature.value = signatureFromBlocks(blocks.value)
  emit('update:dirty', false)
  return updatePayload.content
}

async function restoreContent(versionContent: any) {
  finishBlockPointerSelection()
  blocks.value = blocksFromContent(versionContent)
  activeBlockId.value = null
  clearBlockSelection()
  originalSignature.value = signatureFromBlocks(blocks.value)
  emit('update:dirty', false)
}

onMounted(() => {
  document.addEventListener('pointerdown', handleOutsideSelectionPointerDown, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleOutsideSelectionPointerDown, true)
  finishBlockPointerSelection()
  stopSelectionAutoScroll()
})

defineExpose({
  handleSave,
  restoreContent,
  applyGeneratedContent,
  getContent,
  getReviewTarget,
  startGeneration,
})
</script>

<style scoped>
.screenplay-editor {
  height: 100%;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  outline: none;
}

.waterfall-scroll-hint {
  position: absolute;
  z-index: 6;
  top: 58px;
  left: 6px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  pointer-events: none;
}

.waterfall-scroll-hint__tick {
  display: block;
  width: 7px;
  height: 2px;
  border-radius: 999px;
  background: var(--el-text-color-placeholder);
  opacity: 0.36;
  transition: width 0.12s ease, opacity 0.12s ease, background-color 0.12s ease;
}

.waterfall-scroll-hint__tick.is-current {
  width: 10px;
  background: var(--el-text-color-primary);
  opacity: 0.9;
}

.screenplay-toolbar {
  flex: 0 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-lighter);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.waterfall-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  user-select: none;
}

.selection-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 26px;
  padding: 0 10px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 38%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--el-color-primary) 9%, var(--el-bg-color));
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgb(0 0 0 / 8%);
}

.drag-selection-badge {
  position: fixed;
  z-index: 20;
  pointer-events: none;
  padding: 5px 10px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 55%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--el-color-primary) 88%, #111);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
  box-shadow: 0 6px 18px rgb(0 0 0 / 24%);
  animation: drag-badge-in 0.12s ease-out;
}

@keyframes drag-badge-in {
  from {
    opacity: 0;
    transform: translateY(3px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.line-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.block-editor-pane {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.block-editor-pane {
  padding: 18px;
  background: var(--el-fill-color-light);
  overflow-anchor: none;
}

.active-segment-marker { width: 100%; }

.segment-preview {
  width: 100%;
  max-width: 760px;
  margin: 0 auto;
}

.segment-divider {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: fit-content;
  max-width: calc(100% - 32px);
  height: 30px;
  margin: 8px auto;
  padding: 0 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 999px;
  background: var(--el-fill-color);
  color: var(--el-text-color-regular);
  font-size: 13px;
  font-weight: 600;
  line-height: 28px;
  box-sizing: border-box;
  box-shadow: 0 2px 8px rgb(0 0 0 / 8%);
}

.segment-divider-active {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.segment-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.readonly-label,
.segment-state {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 400;
}

.segment-state-active { color: var(--el-color-primary); }

.screenplay-preview.waterfall-preview {
  max-width: 712px;
  min-height: 0;
  padding: 24px 40px;
  box-sizing: border-box;
}

.waterfall-preview .preview-line {
  width: auto;
  padding: 2px 8px;
  border: 1px solid transparent;
  box-sizing: content-box;
}

.empty-state {
  height: 100%;
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.block-list {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 712px;
  margin: 0 auto;
  min-height: 0;
  padding: 24px 40px;
  border: 0;
  background: var(--el-fill-color-blank);
  box-sizing: border-box;
}

.insert-row {
  position: relative;
  height: 8px;
  margin: -4px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    height 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    margin 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.insert-row::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  border-top: 1px solid var(--el-color-primary-light-5);
  opacity: 0;
  transition:
    opacity 0.14s ease,
    border-color 0.14s ease,
    box-shadow 0.14s ease;
}

.insert-row:has(.insert-control-zone:hover)::before,
.insert-row:has(.insert-control-zone:focus-within)::before,
.insert-row.is-expanded::before,
.insert-row.is-move-target::before {
  opacity: 1;
}

.insert-row.is-expanded {
  height: 40px;
  margin: 4px 0;
}

.insert-control-zone {
  position: relative;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20%;
  min-width: 72px;
  height: 28px;
}

.insert-control-zone .insert-trigger {
  opacity: 0;
  pointer-events: none;
  transform: scale(0.94);
  transition:
    opacity 0.12s ease,
    transform 0.12s ease;
}

.insert-control-zone:hover .insert-trigger,
.insert-control-zone:focus-within .insert-trigger,
.insert-row.is-expanded .insert-trigger {
  opacity: 1;
  pointer-events: auto;
  transform: scale(1);
}

.block-list.is-moving-blocks .insert-control-zone {
  visibility: hidden;
}

.insert-row.is-move-target::before,
.insert-row.is-expanded::before {
  border-top: 2px solid var(--el-color-primary);
  box-shadow: 0 0 8px color-mix(in srgb, var(--el-color-primary) 45%, transparent);
}

.insert-button {
  position: relative;
  z-index: 1;
  --el-button-size: 24px;
  box-shadow: var(--el-box-shadow-light);
}

.insert-dropdown {
  position: relative;
  z-index: 2;
}

.insert-dropdown-menu {
  min-width: 148px;
  padding: 6px;
}

.insert-character-menu-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-radius: 5px;
}

.insert-submenu-arrow {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
}

.insert-character-popover-menu {
  width: max-content;
  min-width: 112px;
  max-width: 220px;
}

.insert-character-option {
  display: block;
  width: 100%;
  height: 34px;
  padding: 0 12px;
  overflow: hidden;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--el-text-color-regular);
  font: inherit;
  line-height: 34px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.insert-character-option:hover,
.insert-character-option:focus-visible {
  background: var(--el-dropdown-menuItem-hover-fill);
  color: var(--el-dropdown-menuItem-hover-color);
  outline: none;
}

:global(.screenplay-insert-dropdown-popper) {
  z-index: 9999 !important;
  overflow: visible !important;
}

:global(.screenplay-insert-dropdown-popper .insert-dropdown-menu),
:global(.screenplay-insert-dropdown-popper .el-scrollbar__view) {
  width: max-content !important;
  min-width: 148px;
}

:global(.screenplay-insert-dropdown-popper .el-scrollbar),
:global(.screenplay-insert-dropdown-popper .el-scrollbar__wrap),
:global(.screenplay-insert-dropdown-popper .el-popper__content) {
  max-height: none !important;
  overflow: visible !important;
}

:global(.screenplay-insert-dropdown-popper .el-scrollbar__wrap) {
  scrollbar-width: none !important;
}

:global(.screenplay-insert-dropdown-popper .el-scrollbar__wrap::-webkit-scrollbar) {
  display: none !important;
  width: 0 !important;
  height: 0 !important;
}

:global(.screenplay-insert-dropdown-popper .el-scrollbar__bar) {
  display: none !important;
}

:global(.screenplay-insert-dropdown-popper .el-dropdown-menu__item:not(.is-disabled):focus:not(:hover):not(.is-submenu-open)) {
  background: transparent !important;
  color: var(--el-text-color-regular) !important;
}

:global(.screenplay-insert-dropdown-popper .insert-character-menu-item.is-submenu-open) {
  background: var(--el-dropdown-menuItem-hover-fill) !important;
  color: var(--el-dropdown-menuItem-hover-color) !important;
}

:global(.screenplay-character-submenu-popper.el-popover) {
  z-index: 10000 !important;
  width: max-content !important;
  min-width: 112px !important;
  max-width: 220px;
  padding: 6px !important;
  overflow: visible !important;
}

.screenplay-block {
  border: 0;
  border-radius: 6px;
  background: transparent;
  padding: 2px 8px;
  cursor: text;
  transition: background 0.16s ease;
}

.screenplay-block.has-auto-gap-before {
  margin-top: 1.2em;
}

.screenplay-block:hover {
  background: var(--el-fill-color);
}

.screenplay-block.is-selected {
  background: transparent;
  box-shadow: none;
  cursor: default;
}

.screenplay-block.is-selected .block-preview-text {
  padding: 1px 2px;
  margin: -1px -2px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--el-text-color-primary) 16%, transparent);
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}

.block-list.is-drag-selecting .screenplay-block.is-selected {
  animation: selected-block-in 0.14s ease-out;
}

@keyframes selected-block-in {
  from {
    opacity: 0.72;
    transform: scale(0.997);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.block-list.is-drag-selecting,
.block-list.is-drag-selecting .screenplay-block,
.block-list.is-drag-selecting .block-preview {
  cursor: crosshair;
  user-select: none;
}

.block-list.is-moving-blocks,
.block-list.is-moving-blocks .screenplay-block,
.block-list.is-moving-blocks .block-preview {
  cursor: grabbing;
  user-select: none;
}

.block-list.is-moving-blocks .screenplay-block.is-selected {
  opacity: 0.56;
  transform: scale(0.997);
}

.screenplay-block.is-active {
  padding: 16px 18px;
  background: var(--el-fill-color-blank);
  box-shadow: none;
  cursor: default;
}

@media (max-width: 760px) {
  .screenplay-toolbar {
    align-items: flex-start;
  }
  .toolbar-left {
    flex-wrap: wrap;
  }
}

.block-topline {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.block-type-select {
  width: 132px;
}

.block-type-select :deep(.el-select__wrapper) {
  background: var(--el-fill-color);
}

.block-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.block-delete-button,
.block-delete-button:hover,
.block-delete-button:focus-visible {
  color: #fff;
}

.block-input :deep(.el-textarea__inner) {
  background: var(--el-fill-color);
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.55;
  padding: 10px 12px;
}

.block-character.is-active .block-input,
.block-dialogue.is-active .block-input,
.block-parenthetical.is-active .block-input {
  display: block;
  width: 100%;
  margin: 0 auto;
}

.block-character.is-active .block-input :deep(.el-textarea__inner) {
  text-align: center;
  text-transform: uppercase;
}

.block-dialogue.is-active .block-input :deep(.el-textarea__inner) {
  text-align: center;
}

.block-parenthetical.is-active .block-input :deep(.el-textarea__inner) {
  text-align: center;
}

.block-preview {
  margin: 0;
  min-height: 1.2em;
  width: 100%;
  color: var(--el-text-color-primary);
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.2;
  white-space: pre-wrap;
  overflow-wrap: normal;
  user-select: text;
}

.blank-editor-hint {
  min-height: 28px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
}

.block-scene_heading .block-preview,
.block-transition .block-preview {
  font-weight: 700;
}

.block-character .block-preview,
.block-dialogue .block-preview,
.block-parenthetical .block-preview {
  margin-left: auto;
  margin-right: auto;
}

.block-character .block-preview {
  max-width: 28ch;
  text-align: center;
}

.block-dialogue .block-preview {
  max-width: 46ch;
  text-align: center;
}

.block-parenthetical .block-preview {
  max-width: 28ch;
  text-align: center;
}

.block-transition .block-preview {
  text-align: right;
}

.screenplay-preview {
  min-height: 100%;
  width: 100%;
  max-width: 680px;
  margin: 0 auto;
  padding: 32px 40px;
  border: 0;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.2;
  user-select: text;
}


.preview-line {
  margin: 0;
  min-height: 1.2em;
  width: 100%;
  color: var(--el-text-color-primary);
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.2;
  white-space: pre-wrap;
  overflow-wrap: normal;
}

.preview-line.has-auto-gap-before {
  margin-top: 1.2em;
}

.preview-line.block-scene_heading,
.preview-line.block-transition {
  font-weight: 700;
}

.preview-line.block-character,
.preview-line.block-dialogue,
.preview-line.block-parenthetical {
  margin-left: auto;
  margin-right: auto;
}

.preview-line.block-character {
  max-width: 28ch;
  text-align: center;
}

.preview-line.block-dialogue {
  max-width: 46ch;
  text-align: center;
}

.preview-line.block-parenthetical {
  max-width: 28ch;
  text-align: center;
}

.preview-line.block-transition {
  text-align: right;
}
</style>
