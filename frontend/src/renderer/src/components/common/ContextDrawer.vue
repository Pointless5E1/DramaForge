<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="720px"
    append-to-body
    align-center
  >
    <div class="dialog-wrapper">
      <div class="section">
        <p class="context-help">設定此卡片在{{ activeContextTemplateKind === 'generation' ? '生成內容' : '審核內容' }}時注入的背景資料與引用。</p>
        <el-input v-model="aiContext" type="textarea" :rows="8" placeholder="在此編輯上下文模板，支持 @ 引用" class="context-area" :spellcheck="false" />
        <div class="chips">
          <el-tag v-for="(t, i) in tokens" :key="i" closable @close="removeToken(t)">@{{ t }}</el-tag>
        </div>
      </div>
    </div>
    <template #footer>
      <div class="actions">
        <el-button @click="visible = false">取消</el-button>
        <el-button @click="$emit('open-selector', { kind: activeContextTemplateKind, text: aiContext })">插入引用 @</el-button>
        <el-button type="primary" @click="apply">應用到卡片</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { ContextTemplateKind, ContextTemplates } from '@renderer/services/contextSlots'

const props = defineProps<{
  modelValue: boolean
  contextTemplates: ContextTemplates
  activeContextTemplateKind: ContextTemplateKind
  previewText?: string
}>()
const emit = defineEmits(['update:modelValue','update:activeContextTemplateKind','apply-context','open-selector'])

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => visible.value = v)
watch(visible, v => emit('update:modelValue', v))

const dialogTitle = computed(() => props.activeContextTemplateKind === 'generation'
  ? '生成上下文設定'
  : '審核上下文設定')
const activeContextTemplateKind = ref<ContextTemplateKind>(props.activeContextTemplateKind)
watch(() => props.activeContextTemplateKind, v => activeContextTemplateKind.value = v)
watch(activeContextTemplateKind, v => emit('update:activeContextTemplateKind', v))

const localTemplates = ref<ContextTemplates>({ ...props.contextTemplates })
watch(
  () => props.contextTemplates,
  v => {
    localTemplates.value = { ...v }
  },
  { deep: true }
)

const aiContext = computed({
  get: () => localTemplates.value[activeContextTemplateKind.value] || '',
  set: (value: string) => {
    localTemplates.value = {
      ...localTemplates.value,
      [activeContextTemplateKind.value]: value,
    }
  },
})

const tokenRegex = /@([^\s]+)/g
const tokens = computed(() => {
  const out: string[] = []
  const text = aiContext.value || ''
  let m: RegExpExecArray | null
  while ((m = tokenRegex.exec(text))) out.push(m[1])
  return out
})

function removeToken(token: string): void {
  const full = '@' + token
  aiContext.value = (aiContext.value || '').split(full).join('')
}

function apply(): void { emit('apply-context', { kind: activeContextTemplateKind.value, text: aiContext.value }) }

// 在抽屜中輸入 @ 時彈出選擇器
let drawerTextarea: HTMLTextAreaElement | null = null
watch(() => visible.value, (v) => {
  if (v) {
    setTimeout(() => {
      drawerTextarea = document.querySelector('.context-area textarea') as HTMLTextAreaElement | null
      drawerTextarea?.addEventListener('input', handleDrawerInput)
    }, 0)
  } else {
    drawerTextarea?.removeEventListener('input', handleDrawerInput)
    drawerTextarea = null
  }
})

function handleDrawerInput(ev: Event): void {
  const textarea = ev.target as HTMLTextAreaElement
  const cursorPos = textarea.selectionStart
  const lastChar = textarea.value.substring(cursorPos - 1, cursorPos)
  if (lastChar === '@') {
    emit('open-selector', { kind: activeContextTemplateKind.value, text: textarea.value })
  }
}
</script>

<style scoped>
.dialog-wrapper { display: flex; flex-direction: column; gap: 16px; }
.section { display: flex; flex-direction: column; gap: 8px; }
.context-help { margin: 0 0 4px; color: var(--el-text-color-secondary); }
.context-area { width: 100%; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
</style> 
