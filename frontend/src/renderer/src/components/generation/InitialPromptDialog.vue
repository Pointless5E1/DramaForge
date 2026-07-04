<template>
  <el-dialog
    v-model="dialogVisible"
    title="開始生成卡片"
    width="500px"
    :close-on-click-modal="false"
  >
    <div class="dialog-content">
      <p class="hint-text">
        你可以提供一些生成偏好或要求（可選）
      </p>
      <p class="hint-subtext">
        直接點擊"開始生成"，AI 會自主決定生成內容
      </p>

      <el-checkbox v-model="useExistingContent" class="content-option">
        基於現有內容繼續生成（如果卡片已有部分內容）
      </el-checkbox>

      <el-input
        v-model="userPrompt"
        type="textarea"
        :rows="4"
        placeholder="例如：年輕武者，擅長劍術，性格沉穩..."
        maxlength="500"
        show-word-limit
        @keyup.ctrl.enter="handleStartGenerate"
      />

      <div class="example-hints">
        <span class="example-label">示例：</span>
        <el-tag
          v-for="example in examples"
          :key="example"
          size="small"
          class="example-tag"
          @click="userPrompt = example"
        >
          {{ example }}
        </el-tag>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">
          取消
        </el-button>
        <el-button @click="handleSkip">
          跳過，直接生成
        </el-button>
        <el-button
          type="primary"
          :disabled="!userPrompt.trim()"
          @click="handleStartGenerate"
        >
          開始生成
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

// ==================== Props & Emits ====================

const props = defineProps<{
  visible: boolean
  cardTypeName?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  confirm: [userPrompt: string, useExistingContent: boolean]
  cancel: []
}>()

// ==================== 狀態管理 ====================

const dialogVisible = ref(false)
const userPrompt = ref('')
const useExistingContent = ref(false)

// 示例提示（根據卡片類型動態調整）
const examples = ref<string[]>([
  '年輕武者，擅長劍術',
  '神祕的魔法師，精通元素魔法',
  '經驗豐富的商人，善於談判'
])

// ==================== 方法 ====================

/**
 * 處理開始生成
 */
function handleStartGenerate() {
  emit('confirm', userPrompt.value.trim(), useExistingContent.value)
  dialogVisible.value = false
  userPrompt.value = ''
  useExistingContent.value = false
}

/**
 * 處理跳過
 */
function handleSkip() {
  emit('confirm', '', useExistingContent.value)
  dialogVisible.value = false
  userPrompt.value = ''
  useExistingContent.value = false
}

/**
 * 處理取消
 */
function handleCancel() {
  emit('cancel')
  dialogVisible.value = false
  userPrompt.value = ''
}

// ==================== 監聽 ====================

watch(() => props.visible, (val) => {
  dialogVisible.value = val
})

watch(dialogVisible, (val) => {
  emit('update:visible', val)
})

// 根據卡片類型調整示例
watch(() => props.cardTypeName, (typeName) => {
  if (!typeName) return

  // 可以根據不同的卡片類型提供不同的示例
  if (typeName.includes('角色') || typeName.includes('Character')) {
    examples.value = [
      '年輕武者，擅長劍術',
      '神祕的魔法師，精通元素魔法',
      '經驗豐富的商人，善於談判'
    ]
  } else if (typeName.includes('章節') || typeName.includes('Chapter')) {
    examples.value = [
      '緊張刺激的戰鬥場景',
      '溫馨的日常對話',
      '關鍵的劇情轉折'
    ]
  } else if (typeName.includes('大綱') || typeName.includes('Outline')) {
    examples.value = [
      '三幕式結構',
      '英雄之旅模式',
      '多線敘事'
    ]
  } else {
    examples.value = [
      '簡潔明瞭',
      '詳細完整',
      '富有創意'
    ]
  }
})
</script>

<style scoped>
.dialog-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hint-text {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.hint-subtext {
  margin: -8px 0 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.example-hints {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.example-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.example-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.example-tag:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
