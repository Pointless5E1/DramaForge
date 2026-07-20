<template>
  <div class="editor-header">
    <div class="header-main">
      <div class="left">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item>{{ projectName }}</el-breadcrumb-item>
          <el-breadcrumb-item>{{ cardType }}</el-breadcrumb-item>
          <el-breadcrumb-item>
            <el-input
              v-if="isEditingTitle"
              ref="titleInputRef"
              v-model="titleProxy"
              size="small"
              class="title-input"
              @blur="finishTitleEditing"
              @keydown.enter.prevent="finishTitleEditing"
              @keydown.esc.prevent="cancelTitleEditing"
            />
            <span
              v-else
              class="title-text"
              title="雙擊編輯卡片名稱"
              @dblclick="startTitleEditing"
            >
              {{ title }}
            </span>
          </el-breadcrumb-item>
        </el-breadcrumb>
        <el-tag :type="statusTag.type" size="small">{{ statusTag.label }}</el-tag>
        <span v-if="lastSavedAt" class="last-saved">上次儲存：{{ lastSavedAt }}</span>
      </div>
      <div class="right">
        <div class="action-group content-actions">
          <el-button v-if="showGenerateButton" type="primary" class="header-action" @click="$emit('generate')">生成</el-button>
          <el-dropdown
            v-if="showReviewButton"
            split-button
            class="review-action"
            :loading="reviewing"
            :disabled="reviewing"
            @click="$emit('review')"
            @command="(prompt: string) => $emit('select-review-prompt', prompt)"
          >
            {{ reviewing ? '審核中' : '審核' }}
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="prompt in reviewPrompts"
                  :key="prompt"
                  :command="prompt"
                >
                  <span>{{ prompt }}</span>
                  <el-icon v-if="prompt === currentReviewPrompt" class="review-check"><Select /></el-icon>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <span class="action-divider" aria-hidden="true"></span>
        <div class="action-group document-actions">
          <el-button
            class="header-action"
            :type="needsConfirmation ? 'warning' : undefined"
            :disabled="!canSaveComputed"
            :loading="saving"
            :class="{ 'needs-confirmation-btn': needsConfirmation }"
            @click="$emit('save')"
          >
            {{ needsConfirmation ? '確認並儲存' : '儲存' }}
          </el-button>
          <el-dropdown trigger="click" @command="handleSettingsCommand">
            <el-button class="header-action settings-action">
              設定
              <el-icon class="settings-arrow"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="generation-context">生成上下文設定</el-dropdown-item>
                <el-dropdown-item command="review-context">審核上下文設定</el-dropdown-item>
                <el-dropdown-item command="ai-params" divided>模型與生成參數</el-dropdown-item>
                <el-dropdown-item command="schema">內容結構</el-dropdown-item>
                <el-dropdown-item command="versions" divided>歷史版本</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, watch, ref } from 'vue'
import { ArrowDown, Select } from '@element-plus/icons-vue'

const props = defineProps<{
  projectName?: string
  cardType: string
  title: string
  dirty: boolean
  saving: boolean
  lastSavedAt?: string
  canSave?: boolean
  isChapterContent?: boolean
  reviewing?: boolean
  reviewPrompts?: string[]
  currentReviewPrompt?: string
  needsConfirmation?: boolean  // AI 修改需要確認
}>()

// 計算是否可以儲存：如果需要確認，即使沒有修改也可以儲存
const canSaveComputed = computed(() => {
  if (props.needsConfirmation) return !props.saving
  return props.canSave
})

const showGenerateButton = computed(() => {
  if (!props.isChapterContent) return true
  return props.cardType === '劇本片段大綱'
})
const showReviewButton = computed(() => (
  !props.isChapterContent
  || props.cardType === '劇本片段正文'
  || props.cardType === '劇本片段大綱'
))

const emit = defineEmits([
  'update:title',
  'save',
  'generate',
  'review',
  'select-review-prompt',
  'open-versions',
  'open-generation-context',
  'open-review-context',
  'open-ai-settings',
  'open-schema',
])

const titleProxy = ref(props.title)
const isEditingTitle = ref(false)
const titleInputRef = ref()

watch(() => props.title, v => {
  if (!isEditingTitle.value) titleProxy.value = v
})

async function startTitleEditing(): Promise<void> {
  titleProxy.value = props.title
  isEditingTitle.value = true
  await nextTick()
  titleInputRef.value?.focus()
  titleInputRef.value?.select()
}

function finishTitleEditing(): void {
  if (!isEditingTitle.value) return
  isEditingTitle.value = false
  if (titleProxy.value !== props.title) emit('update:title', titleProxy.value)
}

function cancelTitleEditing(): void {
  titleProxy.value = props.title
  isEditingTitle.value = false
}

const statusTag = computed(() => {
  if (props.needsConfirmation) return { type: 'warning', label: 'AI 已修改' }
  if (props.saving) return { type: 'success', label: '儲存中' }
  if (props.dirty) return { type: 'info', label: '未儲存' }
  return { type: 'success', label: '已儲存' }
})

function handleSettingsCommand(command: string): void {
  switch (command) {
    case 'generation-context':
      emit('open-generation-context')
      break
    case 'review-context':
      emit('open-review-context')
      break
    case 'ai-params':
      emit('open-ai-settings')
      break
    case 'schema':
      emit('open-schema')
      break
    case 'versions':
      emit('open-versions')
      break
  }
}
</script>

<style scoped>
.editor-header { 
  flex-shrink: 0; /* 固定：防止被壓縮 */
}

.header-main {
  display: flex; 
  align-items: center; 
  justify-content: space-between; 
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px; 
  border-bottom: 0;
  background: transparent;
}

.left {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  min-width: 0;
  box-sizing: border-box;
  padding: 0 12px;
  border-radius: 999px;
  background: var(--nf-surface-control, var(--el-fill-color));
  font-size: 13px;
  white-space: nowrap;
}
.left :deep(.el-breadcrumb),
.left :deep(.el-breadcrumb__inner),
.left :deep(.el-breadcrumb__separator) {
  font-size: 13px;
}
.left :deep(.el-tag) {
  height: auto;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  font-size: 13px;
}
.right { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; }
.action-group { display: inline-flex; align-items: center; gap: 8px; }
.action-group :deep(.el-button + .el-button) { margin-left: 0; }
.header-action {
  min-width: 0;
  height: 30px;
  padding: 0 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}
:deep(.review-action .el-button) {
  height: 30px;
  font-size: 13px;
  font-weight: 500;
}
:deep(.review-action .el-button-group) {
  display: inline-flex;
  overflow: hidden;
  border-radius: 6px;
}
:deep(.review-action .el-button-group > .el-button) {
  margin: 0 !important;
  border-radius: 0 !important;
}
:deep(.review-action .el-button:first-child) {
  padding: 0 12px;
  border-radius: 6px 0 0 6px !important;
}
:deep(.review-action .el-dropdown__caret-button) {
  width: 30px;
  padding: 0;
  margin-left: 0;
  border-left: 1px solid var(--nf-divider-strong, var(--el-border-color));
  border-radius: 0 6px 6px 0 !important;
}
.right :deep(.el-button:not(.el-button--primary):not(.el-button--warning)) {
  border: 0;
  background: var(--nf-surface-control, var(--el-fill-color));
  color: var(--el-text-color-primary);
}
.right :deep(.el-button:not(.el-button--primary):not(.el-button--warning):hover),
.right :deep(.el-button:not(.el-button--primary):not(.el-button--warning):focus-visible) {
  border: 0;
  background: var(--nf-surface-raised, var(--el-fill-color-light));
  color: var(--el-text-color-primary);
}
.review-check { margin-left: 12px; color: var(--el-color-primary); }
.settings-action { min-width: 0; }
.action-divider { width: 1px; height: 20px; background: var(--nf-divider-strong, var(--el-border-color)); }
.settings-arrow { margin-left: 4px; }
.title-input { width: 280px; }
.title-text {
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
  white-space: nowrap;
  cursor: default;
  user-select: none;
}
.last-saved { color: var(--el-text-color-secondary); font-size: 13px; }

.needs-confirmation-btn {
  animation: pulse 2s infinite;
  box-shadow: 0 0 0 3px rgba(255, 193, 7, 0.3) !important;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
</style> 
