<template>
  <el-form-item :label="label" :prop="prop">
    <el-input
      v-if="!isLongText"
      :model-value="modelValue"
      @update:modelValue="emit('update:modelValue', $event)"
      :placeholder="placeholder"
      clearable
    />
    <el-input
      v-else
      type="textarea"
      :model-value="modelValue"
      @update:modelValue="emit('update:modelValue', $event)"
      :placeholder="placeholder"
      :autosize="{ minRows: 3, maxRows: 10 }"
      clearable
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

const props = defineProps<{
  modelValue: string | undefined
  label: string
  prop: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

// 一個簡單的啓發式方法：如果描述或標題表明它是一個長文本字段，則使用文本區域。
// 一個更健 robuste 解決方案可能是在 schema 中包含一個自定義屬性，比如 `x-ui-control: 'textarea'`。
const isLongText = computed(() => {
  // 新增規則：如果 schema 中定義了 minLength 且大於 50，則視爲長文本。
  if (props.schema.minLength !== undefined && props.schema.minLength > 50) {
    return true
  }
  const description = props.schema.description?.toLowerCase() || ''
  const title = props.schema.title?.toLowerCase() || ''
  // 如果字段名爲overview，強制用textarea
  if (props.prop === 'overview'||props.prop==='content') return true
  return (
    description.includes('思考') ||
    description.includes('過程') ||
    description.includes('描述') ||
    description.includes('概述') ||
    title.includes('thinking')
  )
})

const placeholder = computed(() => {
  return props.schema.description || `請輸入 ${props.label}`
})
</script>
