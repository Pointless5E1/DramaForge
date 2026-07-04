import request from './request'
import { ref } from 'vue'

// --- 類型定義 ---
// 基礎的 JSON Schema 類型定義。可以根據需要進行擴展。
export interface JSONSchema {
  // Common properties
  type?: string | string[]
  title?: string
  description?: string
  default?: any
  examples?: any[]
  enum?: any[]
  const?: any
  minLength?: number
  'x-knowledge-source'?: string

  // Object properties
  properties?: { [key: string]: JSONSchema }
  required?: string[]
  // 用於數組
  items?: JSONSchema
  // 用於 Pydantic v2+ 的元組（Tuple）
  prefixItems?: JSONSchema[]
  // 用於 Pydantic v1 的元組（Tuple）或聯合類型（Union）
  anyOf?: JSONSchema[]
  // 用於 Literal 轉換來的枚舉
  // 用於對象引用
  $ref?: string
}

// --- 狀態 ---
const schemas = ref<Map<string, JSONSchema>>(new Map())
const isLoading = ref(false)
const error = ref<any>(null)

// --- 邏輯 ---

/**
 * 解析 $ref 引用，找到其對應的 schema 定義。
 * @param refPath 引用路徑 (例如, '#/components/schemas/MyModel')
 * @param openapiSpec 完整的 OpenAPI 規範對象。
 * @returns 解析後的 JSONSchema，如果未找到則返回 null。
 */
function resolveRef(refPath: string, allSchemas: Map<string, JSONSchema>): JSONSchema | null {
  // 我們只處理指向 allSchemas 中其他定義的引用
  // 假設格式爲 '#/$defs/MyModel' or 'MyModel'
  const refName = refPath.split('/').pop()
  if (!refName) {
    console.error('無效的 $ref 路徑:', refPath)
    return null
  }
  const resolved = allSchemas.get(refName)
  if (!resolved) {
    console.error(`無法在 allSchemas 中解析 $ref: ${refName}`)
        return null
      }
  return resolved
}

/**
 * 遞歸地解析 schema 中的所有 $ref 引用。
 * @param schema 要解析的 JSONSchema。
 * @param allSchemas 包含所有可用 schema 定義的 Map。
 * @param visited 已訪問的引用路徑，用於防止循環引用。
 * @returns 解析後的 JSONSchema。
 */
function dereferenceSchema(
  schema: JSONSchema,
  allSchemas: Map<string, JSONSchema>,
  visited = new Set<string>()
): JSONSchema {
  if (typeof schema !== 'object' || schema === null) {
    return schema
  }

  if (schema.$ref) {
    if (visited.has(schema.$ref)) {
      console.warn('檢測到循環引用:', schema.$ref)
      return { type: 'object', title: 'Circular Reference' }
    }
    visited.add(schema.$ref)
    const resolved = resolveRef(schema.$ref, allSchemas)
    if (resolved) {
      // 遞歸地解析解析後的 schema
      return dereferenceSchema(resolved, allSchemas, visited)
    } else {
      return { type: 'string', title: `Unresolved Reference: ${schema.$ref}` }
    }
  }

  const newSchema = { ...schema }
  if (newSchema.properties) {
    newSchema.properties = Object.fromEntries(
      Object.entries(newSchema.properties).map(([key, propSchema]) => [
        key,
        dereferenceSchema(propSchema, allSchemas, new Set(visited))
      ])
    )
  }

  if (newSchema.items) {
    newSchema.items = dereferenceSchema(newSchema.items, allSchemas, new Set(visited))
  }
  
  if (newSchema.prefixItems) {
    newSchema.prefixItems = newSchema.prefixItems.map(itemSchema => 
      dereferenceSchema(itemSchema, allSchemas, new Set(visited))
    );
  }

  if (newSchema.anyOf) {
    newSchema.anyOf = newSchema.anyOf.map(itemSchema => 
      dereferenceSchema(itemSchema, allSchemas, new Set(visited))
    );
  }

  return newSchema
}


/**
 * 獲取完整的 OpenAPI 規範並填充 schemas Map。
 * 這個函數應該在應用啓動時被調用一次。
 */
async function loadSchemas() {
  if (schemas.value.size > 0 || isLoading.value) {
    return
  }
  isLoading.value = true
  error.value = null
  try {
    // 改爲從專用端點獲取所有 schema, 並使用默認的 /api 前綴
    const allSchemas = await request.get<Record<string, JSONSchema>>('/ai/schemas')
    if (allSchemas) {
      const schemaMap = new Map<string, JSONSchema>(Object.entries(allSchemas))
      
      // 創建一個新的 Map 用於存儲解引用後的 schema
      const dereferencedSchemaMap = new Map<string, JSONSchema>()

      // 第一步：先填充所有 schema 到 Map 中
      for (const [name, schema] of schemaMap.entries()) {
        dereferencedSchemaMap.set(name, schema);
      }
      
      // 第二步：遍歷並解引用每一個 schema
      for (const [name, schema] of dereferencedSchemaMap.entries()) {
        dereferencedSchemaMap.set(name, dereferenceSchema(schema, dereferencedSchemaMap));
      }

      // DEBUG: Log all the schema keys that were loaded
      console.log('[SchemaService] All schema keys loaded from /ai/schemas:', Array.from(dereferencedSchemaMap.keys()));

      schemas.value = dereferencedSchemaMap
    }
  } catch (e) {
    console.error('Failed to load schemas from /ai/schemas:', e)
    error.value = e
  } finally {
    isLoading.value = false
  }
}

// 強制刷新（清空緩存並重新加載）
async function refreshSchemas() {
  try {
    schemas.value = new Map()
    isLoading.value = false
    await loadSchemas()
  } catch (e) {
    console.error('Failed to refresh schemas:', e)
  }
}

/**
 * 獲取 schema 的名稱。
 * @param name schema 的名稱 (例如, 'VolumeOutline').
 * @returns 如果找到則返回 JSONSchema，否則返回 undefined。
 */
function getSchema(name: string): JSONSchema | undefined {
  return schemas.value.get(name)
}

// --- 導出 ---
// 導出一個單例對象用於與 schema 交互。
export const schemaService = {
  schemas,
  isLoading,
  error,
  loadSchemas,
  refreshSchemas,
  getSchema
} 
