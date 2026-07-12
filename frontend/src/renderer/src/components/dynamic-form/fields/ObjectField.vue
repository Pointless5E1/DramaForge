<template>
  <section class="object-field">
    <div v-if="label" class="object-field-title">{{ label }}</div>
    <ModelDrivenForm
      :schema="effectiveSchema"
      :modelValue="modelValue || {}"
      @update:modelValue="emit('update:modelValue', $event)"
    />
  </section>
</template>

<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

// 使用前向聲明來處理遞歸組件。
// 這在模塊級別打破了循環依賴。
const ModelDrivenForm = defineAsyncComponent(() => import('../ModelDrivenForm.vue'))

const props = defineProps<{
  modelValue: Record<string, any> | undefined
  label: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

// 當 schema 未聲明 properties 但資料存在時，按資料鍵名動態補齊，保證可渲染
const effectiveSchema = computed<JSONSchema>(() => {
  const sch = props.schema || { type: 'object' }
  const hasProps = sch && typeof sch === 'object' && (sch as any).properties && Object.keys((sch as any).properties as any).length > 0
  if (hasProps) return sch
  const dataKeys = Object.keys(props.modelValue || {})
  if (dataKeys.length === 0) return sch
  const itemSchema: JSONSchema = {
    type: 'object',
    title: 'Item',
    properties: {
      id: { type: 'integer', title: 'id' },
      info: { type: 'string', title: 'info' }
    },
  }
  const propsMap: Record<string, JSONSchema> = {}
  for (const k of dataKeys) {
    propsMap[k] = { type: 'array', items: itemSchema, title: k }
  }
  return { ...sch, type: 'object', properties: propsMap }
})
</script>

<style scoped>
.object-field {
  margin: 0;
}
.object-field-title {
  margin-bottom: 14px;
  color: var(--el-text-color-primary);
  font-size: 15px;
  font-weight: 600;
}
</style>
