<template>
  <div class="segment-editor">
    <el-tabs v-model="activePane" class="segment-tabs">
      <el-tab-pane label="片段大綱" name="outline">
        <div class="outline-pane">
          <div class="outline-actions">
            <el-button :loading="summarizing" :disabled="!contentCard" @click="summarizeFromScreenplay">
              從正文更新大綱草稿
            </el-button>
            <span class="outline-hint">結果只更新目前未儲存的大綱草稿，按上方儲存後才會寫入。</span>
          </div>
          <el-input
            v-model="outlineContent.overview"
            type="textarea"
            :autosize="{ minRows: 10, maxRows: 28 }"
            placeholder="描述本片段的主要行動、衝突、變化與結尾狀態"
            @input="markOutlineDirty"
          />
        </div>
      </el-tab-pane>
      <el-tab-pane label="片段正文" name="screenplay">
        <ScreenplayTextEditor
          v-if="contentCard"
          ref="screenplayRef"
          :card="contentCard"
          @update:dirty="handleScreenplayDirty"
          @activate-card="handleWaterfallActivateCard"
        />
        <el-empty v-else description="找不到此片段綁定的正文 facet" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { CardRead, CardUpdate } from '@renderer/api/cards'
import { generateWithInstructionStream } from '@renderer/api/generation'
import { getCardAIParams, getCardSchema } from '@renderer/api/setting'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useEditorStore, type ChapterExtractRunOptions } from '@renderer/stores/useEditorStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InstructionExecutor } from '@renderer/services/instructionExecutor'
import { applyMemoryPreview, extractMemoryPreview, type ParticipantTyped } from '@renderer/api/memory'
import ScreenplayTextEditor from './ScreenplayTextEditor.vue'

type SegmentOutlineContent = Record<string, unknown> & { overview?: string }
type ScreenplayContent = Record<string, unknown> & { blocks?: unknown[] }
type SegmentEditorPane = 'outline' | 'screenplay'

const ACTIVE_PANE_STORAGE_KEY = 'dramaforge:screenplay-segment-active-pane'

function getInitialActivePane(): SegmentEditorPane {
  try {
    const storedPane = localStorage.getItem(ACTIVE_PANE_STORAGE_KEY)
    if (storedPane === 'outline' || storedPane === 'screenplay') return storedPane
  } catch {
    // localStorage unavailable: fall back to the outline pane.
  }
  return 'outline'
}

const props = defineProps<{ card: CardRead }>()
const emit = defineEmits<{
  (e: 'update:dirty', value: boolean): void
  (e: 'activate-card', cardId: number): void
}>()

const cardStore = useCardStore()
const editorStore = useEditorStore()
const projectStore = useProjectStore()
const { cards } = storeToRefs(cardStore)
const activePane = ref<SegmentEditorPane>(getInitialActivePane())
const screenplayRef = ref<InstanceType<typeof ScreenplayTextEditor> | null>(null)
const outlineContent = ref<SegmentOutlineContent>({ ...((props.card.content || {}) as SegmentOutlineContent) })
const outlineDirty = ref(false)
const screenplayDirty = ref(false)
const summarizing = ref(false)

const contentCard = computed(() => (cards.value || []).find(card =>
  card.parent_id === props.card.id && card.card_type?.name === '劇本片段正文'
) || null)

watch(activePane, pane => {
  try {
    localStorage.setItem(ACTIVE_PANE_STORAGE_KEY, pane)
  } catch {
    // Keep the in-memory selection when localStorage is unavailable.
  }
})

watch(contentCard, (card) => {
  const raw = sessionStorage.getItem('dramaforge:screenplay-waterfall-entry')
  if (!raw || !card) return
  try {
    const entry = JSON.parse(raw) as { cardId?: number }
    if (entry.cardId === card.id) activePane.value = 'screenplay'
  } catch {
    // The child editor clears stale waterfall navigation state.
  }
}, { immediate: true })

function handleWaterfallActivateCard(contentCardId: number): void {
  const targetContent = (cards.value || []).find(card => card.id === contentCardId)
  if (!targetContent?.parent_id) return
  emit('activate-card', targetContent.parent_id)
}

function emitDirty(): void {
  emit('update:dirty', outlineDirty.value || screenplayDirty.value)
}

function markOutlineDirty(): void {
  outlineDirty.value = true
  emitDirty()
}

function handleScreenplayDirty(value: boolean): void {
  screenplayDirty.value = value
  emitDirty()
}

function getContent(): SegmentOutlineContent {
  return { ...((props.card.content || {}) as SegmentOutlineContent), ...outlineContent.value }
}

function getReviewTarget(): { targetField: string; targetText: string; snapshot: string } {
  const editorTarget = screenplayRef.value?.getReviewTarget()
  const fallbackText = String((contentCard.value?.content as any)?.screenplay_text || '').trim()
  const screenplayText = String(editorTarget?.targetText || fallbackText).trim()
  return {
    targetField: 'screenplay_facet.content.screenplay_text',
    targetText: screenplayText,
    snapshot: screenplayText,
  }
}

async function handleSave(newTitle?: string): Promise<SegmentOutlineContent> {
  const title = newTitle?.trim() || props.card.title
  const nextOutline = getContent()
  const shouldSaveScreenplay = screenplayDirty.value
  const update: CardUpdate = { title, content: nextOutline, needs_confirmation: false }
  // 先保存正文。若先更新大綱，store 刷新會觸發 props watcher 並清掉正文 dirty 狀態。
  if (shouldSaveScreenplay && contentCard.value && screenplayRef.value) {
    await screenplayRef.value.handleSave(title)
  }
  await cardStore.modifyCard(props.card.id, update)
  outlineDirty.value = false
  screenplayDirty.value = false
  emitDirty()
  return nextOutline
}

function startGeneration(): void {
  activePane.value = 'screenplay'
  screenplayRef.value?.startGeneration()
}

function extractionText(): string {
  const screenplay = screenplayRef.value?.getContent() || contentCard.value?.content || {}
  return String((screenplay as any).screenplay_text || '').trim()
}

function extractionParticipants(): ParticipantTyped[] {
  const list = Array.isArray(outlineContent.value.entity_list) ? outlineContent.value.entity_list : []
  const cardTypeByTitle = new Map((cards.value || []).map(card => [String(card.title || '').trim(), card.card_type?.name || '']))
  return list.map((item: any) => {
    const name = String(typeof item === 'string' ? item : item?.name || '').trim()
    const cardType = cardTypeByTitle.get(name) || ''
    let type = typeof item === 'object' ? String(item?.entity_type || '') : ''
    if (!type) {
      if (cardType.includes('角色')) type = 'character'
      else if (cardType.includes('場景')) type = 'scene'
      else if (cardType.includes('組織')) type = 'organization'
      else if (cardType.includes('物品')) type = 'item'
      else if (cardType.includes('概念')) type = 'concept'
      else type = 'unknown'
    }
    return { name, type }
  }).filter(item => item.name)
}

async function runScreenplayExtraction(extractorCode: string, options: ChapterExtractRunOptions): Promise<void> {
  const text = extractionText()
  if (!text) {
    ElMessage.warning('請先建立劇本正文')
    return
  }
  const projectId = Number(projectStore.currentProject?.id || props.card.project_id || 0)
  if (!projectId || typeof options.llm_config_id !== 'number') {
    ElMessage.error('缺少專案或提取模型設定')
    return
  }

  const participants = extractionParticipants()
  const preview = await extractMemoryPreview({
    project_id: projectId,
    extractor_code: extractorCode,
    text,
    participants,
    llm_config_id: options.llm_config_id,
    temperature: options.temperature,
    max_tokens: options.max_tokens,
    timeout: options.timeout,
    extra_context: String(outlineContent.value.overview || ''),
    volume_number: Number(outlineContent.value.episode_number) || undefined,
    chapter_number: Number(outlineContent.value.segment_number) || undefined,
  })

  await ElMessageBox.confirm(
    JSON.stringify(preview.preview_data, null, 2),
    '確認寫入提取結果',
    {
      confirmButtonText: '確認寫入',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'screenplay-extract-preview',
    },
  )

  const result = await applyMemoryPreview({
    project_id: projectId,
    extractor_code: extractorCode,
    data: preview.preview_data,
    participants,
    volume_number: Number(outlineContent.value.episode_number) || undefined,
    chapter_number: Number(outlineContent.value.segment_number) || undefined,
    options: extractorCode === 'character_dynamic' ? { queue_size: 5 } : undefined,
  })
  await cardStore.fetchCards(projectId)
  ElMessage.success(`提取結果已寫入（更新 ${result.updated_card_count} 張卡片、${result.updated_relation_count} 筆關係）`)
}

editorStore.setTriggerExtractDynamicInfo(options => runScreenplayExtraction('character_dynamic', options))
editorStore.setTriggerExtractRelations(options => runScreenplayExtraction('relation', options))
editorStore.setTriggerExtractSceneState(options => runScreenplayExtraction('scene_state', options))
editorStore.setTriggerExtractOrganizationState(options => runScreenplayExtraction('organization_state', options))
editorStore.setTriggerExtractItemState(options => runScreenplayExtraction('item_state', options))
editorStore.setTriggerExtractConceptState(options => runScreenplayExtraction('concept_state', options))

onUnmounted(() => {
  editorStore.setTriggerExtractDynamicInfo(null)
  editorStore.setTriggerExtractRelations(null)
  editorStore.setTriggerExtractSceneState(null)
  editorStore.setTriggerExtractOrganizationState(null)
  editorStore.setTriggerExtractItemState(null)
  editorStore.setTriggerExtractConceptState(null)
})

async function summarizeFromScreenplay(): Promise<void> {
  if (!contentCard.value || !screenplayRef.value) return
  const screenplay = screenplayRef.value.getContent() as ScreenplayContent
  const blocks = Array.isArray(screenplay.blocks) ? screenplay.blocks : []
  if (!blocks.length) {
    ElMessage.warning('請先建立劇本正文')
    return
  }
  const params = await getCardAIParams(props.card.id)
  const effectiveParams = params?.effective_params || {}
  if (!effectiveParams.llm_config_id) {
    ElMessage.error('請先設定有效的模型ID')
    return
  }
  const schemaResp = await getCardSchema(props.card.id)
  const schema = schemaResp?.effective_schema || schemaResp?.json_schema
  if (!schema) {
    ElMessage.error('未找到片段大綱 Schema')
    return
  }
  summarizing.value = true
  const executor = new InstructionExecutor(getContent())
  try {
    await generateWithInstructionStream({
      llm_config_id: effectiveParams.llm_config_id,
      user_prompt: '請忠實根據以下劇本正文更新片段大綱。',
      response_model_schema: schema,
      current_data: getContent(),
      conversation_context: [],
      context_info: `【劇本正文】\n${JSON.stringify(screenplay, null, 2)}`,
      prompt_template: '劇本片段正文摘要',
      temperature: effectiveParams.temperature,
      max_tokens: effectiveParams.max_tokens,
      timeout: effectiveParams.timeout,
    }, {
      onInstruction: instruction => {
        executor.execute(instruction)
        outlineContent.value = { ...executor.getData() }
        markOutlineDirty()
      },
      onError: text => ElMessage.error(text || '大綱摘要失敗'),
      onDone: (success, message, finalData) => {
        if (success && finalData) {
          outlineContent.value = { ...finalData }
          markOutlineDirty()
          ElMessage.success('已產生大綱草稿，尚未儲存')
        } else if (!success) {
          ElMessage.error(message || '大綱摘要失敗')
        }
      },
    })
  } finally {
    summarizing.value = false
  }
}

async function restoreContent(versionContent: unknown): Promise<void> {
  outlineContent.value = { ...((versionContent || {}) as SegmentOutlineContent) }
  outlineDirty.value = true
  emitDirty()
}

watch(() => props.card, card => {
  outlineContent.value = { ...((card.content || {}) as SegmentOutlineContent) }
  outlineDirty.value = false
  screenplayDirty.value = false
  emitDirty()
})

defineExpose({ handleSave, getContent, getReviewTarget, restoreContent, startGeneration })
</script>

<style scoped>
.segment-editor { height: 100%; min-height: 0; }
.segment-tabs { height: 100%; display: flex; flex-direction: column; }
.segment-tabs :deep(.el-tabs__content) { flex: 1; min-height: 0; }
.segment-tabs :deep(.el-tab-pane) { height: 100%; }
.outline-pane { padding: 16px; max-width: 960px; margin: 0 auto; }
.outline-actions { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.outline-hint { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
