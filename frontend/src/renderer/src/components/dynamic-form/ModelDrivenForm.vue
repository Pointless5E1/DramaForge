<template>
  <div v-if="schema && modelValue !== undefined && typeof modelValue === 'object'" class="model-driven-form">
    <el-form :model="modelValue" label-position="top">
      <div
        v-for="(propSchema, propName) in visibleProperties"
        :key="propName"
        class="form-field"
        :class="{
          'form-field--complex': isComplexField(propSchema),
          'form-field--section-root': isHiddenSectionRoot(propSchema),
        }"
      >
        <component
          :is="getFieldComponent(propSchema)"
          :label="getFieldLabel(String(propName), propSchema)"
          :prop="String(propName)"
          :schema="resolveActualSchema(propSchema)"
          :display-name-map="displayNameMap"
          :model-value="modelValue[propName]"
          :readonly="readonlyFields.includes(String(propName))"
          :contextData="modelValue"
          :owner-id="ownerId"
          @update:modelValue="updateModel(String(propName), $event)"
        />
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import type { JSONSchema } from '@renderer/api/schema'
import { schemaService } from '@renderer/api/schema'
import { resolveActualSchema as resolveSchemaUnified } from '@renderer/services/schemaFieldParser'

// --- 組件導入 ---
const StringField = defineAsyncComponent(() => import('./fields/StringField.vue'))
const NumberField = defineAsyncComponent(() => import('./fields/NumberField.vue'))
const BooleanField = defineAsyncComponent(() => import('./fields/BooleanField.vue'))
const ObjectField = defineAsyncComponent(() => import('./fields/ObjectField.vue'))
const ArrayField = defineAsyncComponent(() => import('./fields/ArrayField.vue'))
const EnumField = defineAsyncComponent(() => import('./fields/EnumField.vue'))
const TupleField = defineAsyncComponent(() => import('./fields/TupleField.vue'))
// 用於不支持類型的預設回退組件
const FallbackField = defineAsyncComponent(() => import('./fields/FallbackField.vue'))

// --- Props & Emits ---
const props = defineProps<{
  schema: JSONSchema | undefined
  modelValue: Record<string, any>
  displayNameMap?: Record<string, string>
  readonlyFields?: string[]
  contextData?: Record<string, any>
  ownerId?: number | null
  includeFields?: string[]
  excludeFields?: string[]
  hideSingleComplexFieldLabel?: boolean
}>()

const emit = defineEmits(['update:modelValue'])

// --- 預設值 ---
const readonlyFields = props.readonlyFields || []

const visibleProperties = computed(() => {
  const all = (props.schema?.properties || {}) as Record<string, JSONSchema>
  const entries = Object.entries(all)
  const included = props.includeFields && props.includeFields.length > 0
    ? entries.filter(([k]) => props.includeFields!.includes(k))
    : entries
  const excluded = props.excludeFields && props.excludeFields.length > 0
    ? included.filter(([k]) => !props.excludeFields!.includes(k))
    : included
  return Object.fromEntries(excluded)
})

// --- 邏輯 ---
function resolveActualSchema(schema: JSONSchema): JSONSchema {
  // 使用統一的Schema解析服務
  return resolveSchemaUnified(schema, props.schema) as JSONSchema
}

function getFieldComponent(propSchema: JSONSchema) {
  const actualSchema = resolveActualSchema(propSchema);
  if (
    (actualSchema.enum && actualSchema.enum.length > 0)
    || actualSchema['x-knowledge-source']
  ) {
    return EnumField
  }
  if (actualSchema.type === 'array' && (actualSchema.prefixItems || actualSchema.anyOf)) {
    if (actualSchema.anyOf && !actualSchema.prefixItems) {
       return TupleField
    }
    if(actualSchema.prefixItems){
      return TupleField
    }
  }
  switch (actualSchema.type) {
    case 'string':
      return StringField
    case 'number':
    case 'integer':
      return NumberField
    case 'boolean':
      return BooleanField
    case 'object':
      return ObjectField
    case 'array':
      return ArrayField
    default:
      console.warn(`不支持的字段類型: ${actualSchema.type} (屬性: ${actualSchema.title}). 已使用回退組件。`)
      return FallbackField
  }
}

function getFieldLabel(propName: string, propSchema: JSONSchema): string {
  const actualSchema = resolveActualSchema(propSchema)
  if (
    props.hideSingleComplexFieldLabel
    && props.includeFields?.length === 1
    && (actualSchema.type === 'object' || actualSchema.type === 'array')
  ) return ''
  return (props.displayNameMap && props.displayNameMap[propName])
    || (propSchema as any).title
    || (actualSchema as any).title
    || propName
}

function isComplexField(propSchema: JSONSchema): boolean {
  const type = resolveActualSchema(propSchema).type
  return type === 'object' || type === 'array'
}

function isHiddenSectionRoot(propSchema: JSONSchema): boolean {
  return !!(
    props.hideSingleComplexFieldLabel
    && props.includeFields?.length === 1
    && isComplexField(propSchema)
  )
}

function updateModel(propName: string, value: any) {
  const newModel = { ...props.modelValue, [propName]: value }
  emit('update:modelValue', newModel)
}
</script>

<style scoped>
.form-field + .form-field { margin-top: 22px; }
.form-field--complex:not(.form-field--section-root) {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--nf-divider-subtle, var(--el-border-color-lighter));
}
.model-driven-form { padding: 0; min-width: 0; }
.model-driven-form :deep(.el-form-item__label) {
  padding-bottom: 7px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
}
.model-driven-form :deep(.el-form-item) { margin-bottom: 22px; }
.model-driven-form :deep(.el-form-item:last-child) { margin-bottom: 0; }
</style>
