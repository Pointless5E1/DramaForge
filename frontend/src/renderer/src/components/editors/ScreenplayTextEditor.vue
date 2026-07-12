<template>
  <div class="screenplay-editor">
    <div class="screenplay-toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="mode" :options="modeOptions" size="small" />
      </div>
      <div class="toolbar-right">
        <el-button size="small" plain :icon="Download" @click="exportWordDocument">匯出 Word</el-button>
        <el-button size="small" plain :icon="DocumentCopy" @click="copyPlainText">複製預覽文本</el-button>
        <span class="line-count">{{ blocks.length }} 段</span>
      </div>
    </div>

    <div v-if="mode === 'edit'" class="block-editor-pane" @click="deactivateBlock">
      <div v-if="!blocks.length" class="empty-state" @click.stop>
        <el-button type="primary" plain @click="addBlock('scene_heading')">新增第一個場景</el-button>
      </div>

      <div v-else class="block-list" @click="deactivateBlock">
        <template v-for="(block, index) in blocks" :key="block.id">
          <div class="insert-row" @click.stop>
            <el-dropdown trigger="click" @command="type => insertBlockCommandAt(index, type)">
              <el-button class="insert-button" circle size="small" :icon="Plus" title="在此新增段落" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="option in blockTypeOptions"
                    :key="option.value"
                    :command="option.value"
                  >
                    {{ option.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <section
            class="screenplay-block"
            :class="[
              `block-${block.type}`,
              {
                'is-active': activeBlockId === block.id,
                'has-auto-gap-before': hasAutoBlankBefore(index),
              },
            ]"
            @click.stop="activateBlock(block.id)"
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
                    size="small"
                    text
                    type="danger"
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

            <pre v-else class="block-preview">{{ renderBlockText(block) }}</pre>
          </section>
        </template>

        <div class="insert-row" @click.stop>
          <el-dropdown trigger="click" @command="type => insertBlockCommandAt(blocks.length, type)">
            <el-button class="insert-button" circle size="small" :icon="Plus" title="在結尾新增段落" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="option in blockTypeOptions"
                  :key="option.value"
                  :command="option.value"
                >
                  {{ option.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>

    <div v-else class="preview-pane">
      <div class="screenplay-preview">
        <template v-if="blocks.length">
          <pre
            v-for="(block, index) in blocks"
            :key="block.id"
            class="preview-line"
            :class="[
              `block-${block.type}`,
              { 'has-auto-gap-before': hasAutoBlankBefore(index) },
            ]"
          >{{ renderBlockText(block) }}</pre>
        </template>
        <pre v-else class="preview-line">（暫無劇本正文）</pre>
      </div>
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
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowUp, Delete, DocumentCopy, Download, Plus } from '@element-plus/icons-vue'
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
}>()

const cardStore = useCardStore()
const perCardStore = usePerCardAISettingsStore()
const { cards } = storeToRefs(cardStore)
const mode = ref<'edit' | 'preview'>('edit')
const modeOptions = [
  { label: '編輯', value: 'edit' },
  { label: '預覽', value: 'preview' },
]

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

const blocks = ref<ScreenplayBlock[]>([])
const originalSignature = ref('')
const activeBlockId = ref<string | null>(null)
const showInitialPromptDialog = ref(false)
const showGenerationPanel = ref(false)
const generationPanelRef = ref<InstanceType<typeof GenerationPanel>>()
const instructionExecutor = ref<InstructionExecutor | null>(null)
const conversationHistory = ref<ConversationMessage[]>([])
const currentAbortController = ref<AbortController | null>(null)
const aiGenerating = ref(false)

const screenplayText = computed(() => serializeBlocks(blocks.value))

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
  return lines.map((line): ScreenplayBlock => ({
    id: uid(),
    type: normalizeBlockType(line?.line_type || line?.type),
    text: stripBlockFormat(normalizeBlockType(line?.line_type || line?.type), typeof line?.text === 'string' ? line.text : ''),
    character: line?.character || null,
    scene_id: line?.scene_id || null,
  }))
}

function blocksFromContent(content: any): ScreenplayBlock[] {
  const normalized = normalizeContent(content)

  if (Array.isArray(normalized.blocks) && normalized.blocks.length) {
    return normalized.blocks.map((block: any): ScreenplayBlock => ({
      id: uid(),
      type: normalizeBlockType(block?.type || block?.block_type || block?.line_type),
      text: stripBlockFormat(normalizeBlockType(block?.type || block?.block_type || block?.line_type), blockTextFromAny(block)),
      character: block?.character || null,
      scene_id: block?.scene_id || null,
    }))
  }

  if (typeof normalized.screenplay_text === 'string' && normalized.screenplay_text.trim()) {
    return parsePlainTextToBlocks(normalized.screenplay_text)
  }

  if (Array.isArray(normalized.lines) && normalized.lines.length) {
    return blocksFromLegacyLines(normalized.lines)
  }

  if (typeof normalized.content === 'string' && normalized.content.trim()) {
    return parsePlainTextToBlocks(normalized.content)
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
    'line-height': '1.2',
    margin: hasGapBefore ? '12pt 0 0 0' : '0',
    'white-space': 'pre-wrap',
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
      paragraphs.push(`<p style="${richParagraphStyle({ type: 'blank', text: '' }, false)}">&nbsp;</p>`)
    }
    const text = block.type === 'blank' ? '&nbsp;' : escapeHtml(renderBlockText(block))
    paragraphs.push(`<p style="${richParagraphStyle(block, false)}">${text || '&nbsp;'}</p>`)
    previous = block
  }

  return [
    '<!doctype html>',
    '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">',
    '<head>',
    '<meta charset="utf-8">',
    '<style>',
    '@page { size: 8.5in 11in; margin: 1in 1in 1in 1.2in; }',
    'body { font-family: "標楷體", "DFKai-SB", BiauKai, serif; font-size: 12pt; line-height: 1.2; color: #111; }',
    'p { margin: 0; }',
    '</style>',
    '</head>',
    '<body style="font-family:\'標楷體\',\'DFKai-SB\',BiauKai,serif;font-size:12pt;line-height:1.2;color:#111;">',
    '<div style="width:6.3in;font-family:\'標楷體\',\'DFKai-SB\',BiauKai,serif;">',
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

function escapeRtf(text: string): string {
  return Array.from(String(text || '')).map((char) => {
    if (char === '\\') return '\\\\'
    if (char === '{') return '\\{'
    if (char === '}') return '\\}'
    if (char === '\n') return '\\line '
    const codePoint = char.codePointAt(0) || 0
    if (codePoint <= 0x7f) return char
    if (codePoint <= 0xffff) {
      const signed = codePoint > 0x7fff ? codePoint - 0x10000 : codePoint
      return `\\u${signed}?`
    }
    return '?'
  }).join('')
}

function rtfParagraphPrefix(block: ScreenplayBlock | PersistedScreenplayBlock, hasGapBefore: boolean) {
  const spacing = hasGapBefore ? '\\sb240' : '\\sb0'
  switch (block.type) {
    case 'character':
      return `\\pard\\qc${spacing}\\f0\\fs24 `
    case 'dialogue':
      return `\\pard\\li1944\\ri1944${spacing}\\f0\\fs24 `
    case 'parenthetical':
      return `\\pard\\qc${spacing}\\f0\\fs24 `
    case 'transition':
      return `\\pard\\qr${spacing}\\b\\f0\\fs24 `
    case 'scene_heading':
      return `\\pard${spacing}\\b\\f0\\fs24 `
    default:
      return `\\pard${spacing}\\f0\\fs24 `
  }
}

function buildScreenplayRtf(source: Array<ScreenplayBlock | PersistedScreenplayBlock>) {
  const lines: string[] = [
    '{\\rtf1\\ansi\\deff0',
    '{\\fonttbl{\\f0\\fnil\\fcharset136 標楷體;}}',
    '\\paperw12240\\paperh15840\\margl1728\\margr1440\\margt1440\\margb1440',
  ]
  let previous: ScreenplayBlock | PersistedScreenplayBlock | undefined

  for (const block of source) {
    const hasGapBefore = shouldInsertBlankBetween(previous, block)
    const text = block.type === 'blank' ? '' : renderBlockText(block)
    const suffix = block.type === 'scene_heading' || block.type === 'transition' ? '\\b0\\par' : '\\par'
    lines.push(`${rtfParagraphPrefix(block, hasGapBefore)}${escapeRtf(text)}${suffix}`)
    previous = block
  }

  lines.push('}')
  return lines.join('\n')
}

function copyTextWithLegacyCommand(text: string) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()

  try {
    return document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
  }
}

async function copyPlainTextFallback(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return
  } catch (plainCopyError) {
    console.warn('Plain screenplay copy failed, falling back to legacy copy:', plainCopyError)
  }

  if (!copyTextWithLegacyCommand(text)) {
    throw new Error('Legacy copy command failed')
  }
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

function activateBlock(blockId: string) {
  activeBlockId.value = blockId
}

function deactivateBlock() {
  activeBlockId.value = null
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

function insertBlockAt(index: number, type: ScreenplayBlockType) {
  const block = makeBlock(type)
  blocks.value.splice(index, 0, block)
  activeBlockId.value = block.id
  touch()
}

function insertBlockCommandAt(index: number, command: unknown) {
  insertBlockAt(index, normalizeBlockType(command))
}

function removeBlock(index: number) {
  const removed = blocks.value[index]
  blocks.value.splice(index, 1)
  if (removed?.id === activeBlockId.value) {
    activeBlockId.value = blocks.value[index]?.id || blocks.value[index - 1]?.id || null
  }
  touch()
}

function moveBlock(index: number, delta: number) {
  const nextIndex = index + delta
  if (nextIndex < 0 || nextIndex >= blocks.value.length) return
  const [block] = blocks.value.splice(index, 1)
  blocks.value.splice(nextIndex, 0, block)
  activeBlockId.value = block.id
  touch()
}

async function copyPlainText() {
  try {
    const plainText = screenplayText.value
    const richHtml = buildScreenplayHtml(blocks.value)
    const richRtf = buildScreenplayRtf(blocks.value)

    if (typeof ClipboardItem !== 'undefined' && navigator.clipboard.write) {
      try {
        const clipboardData: Record<string, Blob> = {
          'text/plain': new Blob([plainText], { type: 'text/plain' }),
          'text/html': new Blob([richHtml], { type: 'text/html' }),
        }
        const supportsRtf = typeof (ClipboardItem as any).supports === 'function'
          ? (ClipboardItem as any).supports('text/rtf')
          : false
        if (supportsRtf) {
          clipboardData['text/rtf'] = new Blob([richRtf], { type: 'text/rtf' })
        }
        await navigator.clipboard.write([
          new ClipboardItem(clipboardData),
        ])
      } catch (richCopyError) {
        console.warn('Rich screenplay copy failed, falling back to plain text:', richCopyError)
        await copyPlainTextFallback(plainText)
      }
    } else {
      await copyPlainTextFallback(plainText)
    }

    ElMessage.success('已複製劇本文本')
  } catch (error) {
    console.error('Copy screenplay text failed:', error)
    ElMessage.error('複製失敗')
  }
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
  touch()
}

function getContent() {
  return contentFromBlocks()
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
    await generateWithInstructionStream(
      {
        llm_config_id: params.llm_config_id!,
        user_prompt: userPrompt,
        response_model_schema: schema,
        current_data: instructionExecutor.value?.getData() || buildInitialGenerationData(useExistingContent),
        conversation_context: conversationHistory.value,
        context_info: wrapReferenceContext(getResolvedGenerationContext()),
        prompt_template: params.prompt_name,
        temperature: params.temperature,
        max_tokens: params.max_tokens,
        timeout: params.timeout,
      },
      {
        onThinking: text => generationPanelRef.value?.addMessage('thinking', text),
        onInstruction: (instruction: Instruction) => {
          instructionExecutor.value?.execute(instruction)
          const data = instructionExecutor.value?.getData()
          if (data) applyGeneratedContent(data)
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
    blocks.value = blocksFromContent(nextCard?.content)
    activeBlockId.value = null
    originalSignature.value = signatureFromBlocks(blocks.value)
    emit('update:dirty', false)
  },
  { immediate: true, deep: true }
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
  blocks.value = blocksFromContent(versionContent)
  activeBlockId.value = null
  originalSignature.value = signatureFromBlocks(blocks.value)
  emit('update:dirty', false)
}

defineExpose({
  handleSave,
  restoreContent,
  applyGeneratedContent,
  getContent,
  startGeneration,
})
</script>

<style scoped>
.screenplay-editor {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
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

.line-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.block-editor-pane,
.preview-pane {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.block-editor-pane {
  padding: 18px;
  background: var(--el-fill-color-light);
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
  max-width: 82ch;
  margin: 0 auto;
  min-height: 100%;
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
  opacity: 0;
  transition: opacity 0.16s ease, height 0.16s ease, margin 0.16s ease;
}

.insert-row::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  border-top: 1px solid var(--el-color-primary-light-5);
}

.insert-row:hover,
.insert-row:focus-within {
  height: 28px;
  margin: 2px 0;
  opacity: 1;
}

.insert-button {
  position: relative;
  z-index: 1;
  box-shadow: var(--el-box-shadow-light);
}

.screenplay-block {
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  padding: 2px 8px;
  cursor: text;
  transition: border-color 0.16s ease, background 0.16s ease, box-shadow 0.16s ease;
}

.screenplay-block.has-auto-gap-before {
  margin-top: 1.55em;
}

.screenplay-block:hover {
  background: var(--el-fill-color-extra-light);
}

.screenplay-block.is-active {
  padding: 10px;
  border-color: var(--el-border-color);
  background: var(--el-fill-color-blank);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-9);
  cursor: default;
}

.block-topline {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.block-type-select {
  width: 132px;
}

.block-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.block-input :deep(.el-textarea__inner) {
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.55;
}

.block-character.is-active .block-input,
.block-dialogue.is-active .block-input,
.block-parenthetical.is-active .block-input {
  display: block;
  margin: 0 auto;
}

.block-character.is-active .block-input {
  max-width: 28ch;
}

.block-dialogue.is-active .block-input {
  max-width: 46ch;
}

.block-parenthetical.is-active .block-input {
  max-width: 28ch;
}

.block-character.is-active .block-input :deep(.el-textarea__inner) {
  text-align: center;
  text-transform: uppercase;
}

.block-parenthetical.is-active .block-input :deep(.el-textarea__inner) {
  text-align: center;
}

.block-preview {
  margin: 0;
  min-height: 1.55em;
  width: 100%;
  color: var(--el-text-color-primary);
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.55;
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
}

.block-parenthetical .block-preview {
  max-width: 28ch;
  text-align: center;
}

.block-transition .block-preview {
  text-align: right;
}

.preview-pane {
  padding: 18px;
  background: var(--el-fill-color-light);
}

.screenplay-preview {
  min-height: 100%;
  max-width: 82ch;
  margin: 0 auto;
  padding: 32px 40px;
  border: 0;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.55;
  user-select: text;
}


.preview-line {
  margin: 0;
  min-height: 1.55em;
  width: 100%;
  color: var(--el-text-color-primary);
  font-family: "Courier New", Courier, monospace;
  font-size: 15px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: normal;
}

.preview-line.has-auto-gap-before {
  margin-top: 1.55em;
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
}

.preview-line.block-parenthetical {
  max-width: 28ch;
  text-align: center;
}

.preview-line.block-transition {
  text-align: right;
}
</style>
