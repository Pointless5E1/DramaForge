<template>
  <div class="agent-composer" :class="{ 'agent-composer--surface': appearance === 'surface' }">
    <el-input
      v-model="innerValue"
      type="textarea"
      :rows="rows"
      :resize="resize"
      :placeholder="placeholder"
      :disabled="disabled"
      @keydown="handleKeydown"
      :class="['composer-input', inputClass]"
    />
    <div class="composer-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  disabled?: boolean
  rows?: number
  resize?: 'none' | 'both' | 'horizontal' | 'vertical'
  inputClass?: string
  appearance?: 'default' | 'surface'
}>(), {
  placeholder: '請輸入內容',
  disabled: false,
  rows: 3,
  resize: 'none',
  inputClass: '',
  appearance: 'default',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'keydown', event: KeyboardEvent): void
}>()

const innerValue = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})

function handleKeydown(event: KeyboardEvent) {
  emit('keydown', event)
}
</script>

<style scoped>
.agent-composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.composer-input {
  width: 100%;
}

.agent-composer--surface :deep(.el-textarea__inner) {
  border: none !important;
  border-radius: 8px;
  background: transparent !important;
  box-shadow: none !important;
  transition: none !important;
}
.agent-composer--surface :deep(.el-textarea__inner:hover) {
  background: transparent !important;
  box-shadow: none !important;
}
.agent-composer--surface :deep(.el-textarea__inner:focus) {
  background: transparent !important;
  box-shadow: none !important;
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
