<template>
  <el-form-item :label="label" :prop="prop">
    <div class="tuple-field-wrapper">
      <div v-for="(itemSchema, index) in itemSchemas" :key="index" class="tuple-item">
        <component
          :is="getFieldComponent(itemSchema)"
          :model-value="modelValue ? modelValue[index] : undefined"
          @update:modelValue="updateItem(index, $event)"
          :schema="itemSchema"
          label=""
          prop=""
        />
      </div>
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'

// 避免循環依賴
const StringField = defineAsyncComponent(() => import('./StringField.vue'))
const NumberField = defineAsyncComponent(() => import('./NumberField.vue'))
const BooleanField = defineAsyncComponent(() => import('./BooleanField.vue'))
const FallbackField = defineAsyncComponent(() => import('./FallbackField.vue'))

const props = defineProps<{
  modelValue: any[] | undefined
  label: string
  prop: string
  schema: JSONSchema
}>()

const emit = defineEmits(['update:modelValue'])

// 根據 schema 確定元組每個元素的 schema
const itemSchemas = computed((): JSONSchema[] => {
  return props.schema.prefixItems || props.schema.anyOf || []
})

// 動態獲取元組中每個元素應該使用的字段組件
function getFieldComponent(itemSchema: JSONSchema) {
  if (itemSchema.enum && itemSchema.enum.length > 0) {
    // 雖然元組裏用枚舉不常見，但以防萬一
    // return EnumField - 爲了簡化，暫時不在這裏處理枚舉
  }
  switch (itemSchema.type) {
    case 'string':
      return StringField
    case 'number':
    case 'integer':
      return NumberField
    case 'boolean':
      return BooleanField
    default:
      return FallbackField
  }
}

function updateItem(index: number, value: any) {
  const newTuple = [...(props.modelValue || [])]
  newTuple[index] = value
  emit('update:modelValue', newTuple)
}
</script>

<style scoped>
.tuple-field-wrapper {
  display: flex;
  gap: 10px;
  width: 100%;
}

.tuple-item {
  flex-grow: 1;
}

/* 移除內聯字段的 el-form-item 默認邊距 */
:deep(.el-form-item) {
  margin-bottom: 0;
}
</style> 