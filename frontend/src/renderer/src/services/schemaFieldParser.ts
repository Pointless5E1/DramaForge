/**
 * Schema字段解析服務
 * 用於解析JSON Schema的字段結構，支持嵌套對象、引用和anyOf
 * 與現有的schemaService集成，提供統一的Schema解析能力
 * 
 * 統一解析入口：
 * - 卡片渲染時：ModelDrivenForm.vue -> resolveActualSchema()
 * - 工作流預覽時：WorkflowParamPanel.vue -> parseSchemaFields()
 * - 數組字段解析：ArrayField.vue -> resolveActualSchema() + createDefaultValue()
 * - 設置界面編輯：使用獨立的outputModelSchemaUtils.ts（專門用於Schema編輯器）
 */

import { schemaService } from '@renderer/api/schema'


export interface ParsedField {
  name: string
  title: string
  type: string
  path: string
  description: string
  required: boolean
  expanded: boolean
  children?: ParsedField[]
  expandable?: boolean
  arrayItemType?: string
  hasChildren?: boolean
}

/**
 * 解析JSON Schema字段結構
 * @param schema JSON Schema對象
 * @param path 字段路徑前綴
 * @param maxDepth 最大遞歸深度
 * @returns 解析後的字段列表
 */
export function parseSchemaFields(schema: any, path = '$.content', maxDepth = 5): ParsedField[] {
  if (maxDepth <= 0) return []
  
  const fields: ParsedField[] = []
  try {
    const properties = schema.properties || {}
    const defs = schema.$defs || {}
    const required = schema.required || []
    
    for (const [fieldName, fieldSchema] of Object.entries(properties)) {
      if (typeof fieldSchema !== 'object' || !fieldSchema) continue
      
      // 解析引用和anyOf
      const resolvedSchema = resolveSchemaRef(fieldSchema as any, defs)
      
      const fieldType = resolvedSchema.type || 'unknown'
      const fieldTitle = resolvedSchema.title || fieldName
      const fieldDescription = resolvedSchema.description || ''
      const fieldPath = `${path}.${fieldName}`
      
      const fieldInfo: ParsedField = {
        name: fieldName,
        title: fieldTitle,
        type: fieldType,
        path: fieldPath,
        description: fieldDescription,
        required: required.includes(fieldName),
        expanded: false
      }
      
      // 處理嵌套對象
      if (fieldType === 'object' && resolvedSchema.properties) {
        const children = parseSchemaFields(resolvedSchema, fieldPath, maxDepth - 1)
        if (children.length > 0) {
          fieldInfo.children = children
          fieldInfo.expandable = true
          fieldInfo.hasChildren = true
        }
      }
      
      // 處理數組類型
      else if (fieldType === 'array' && resolvedSchema.items) {
        const itemsSchema = resolveSchemaRef(resolvedSchema.items, defs)
        if (itemsSchema.type === 'object' && itemsSchema.properties) {
          const children = parseSchemaFields(itemsSchema, `${fieldPath}[0]`, maxDepth - 1)
          if (children.length > 0) {
            fieldInfo.children = children
            fieldInfo.expandable = true
            fieldInfo.hasChildren = true
            fieldInfo.arrayItemType = 'object'
          }
        } else {
          fieldInfo.arrayItemType = itemsSchema.type || 'unknown'
        }
      }
      
      fields.push(fieldInfo)
    }
  } catch (e) {
    console.warn('解析Schema字段失敗:', e)
  }
  
  return fields
}

/**
 * 解析Schema引用，支持本地$defs和全局schemaService
 * @param schema Schema對象
 * @param localDefs 本地$defs定義
 * @returns 解析後的Schema對象
 */
export function resolveSchemaRef(schema: any, localDefs?: any): any {
  if (!schema || typeof schema !== 'object') return schema
  
  // 處理anyOf類型 - 優先處理
  if (schema.anyOf && Array.isArray(schema.anyOf)) {
    for (const anySchema of schema.anyOf) {
      if (anySchema.type === 'null') continue
      
      // 遞歸解析anyOf中的引用
      const resolved = resolveSchemaRef(anySchema, localDefs)
      if (resolved && resolved.type && resolved.type !== 'null') {
        return {
          ...resolved,
          title: schema.title || resolved.title,
          description: schema.description || resolved.description
        }
      }
    }
  }
  
  // 處理$ref引用
  if (schema.$ref && typeof schema.$ref === 'string') {
    const refPath = schema.$ref
    if (refPath.startsWith('#/$defs/')) {
      const refName = refPath.replace('#/$defs/', '')
      
      // 優先使用本地$defs
      let resolved = localDefs && localDefs[refName] ? localDefs[refName] : null
      
      // 如果本地沒有，嘗試從全局schemaService獲取
      if (!resolved) {
        resolved = schemaService.getSchema(refName)
      }
      
      if (resolved) {
        // 遞歸解析引用的定義（可能還包含其他引用）
        const finalResolved = resolveSchemaRef(resolved, localDefs)
        return {
          ...finalResolved,
          title: schema.title || finalResolved.title,
          description: schema.description || finalResolved.description
        }
      }
    }
  }
  
  return schema
}

/**
 * 獲取字段類型對應的圖標
 * @param type 字段類型
 * @returns 圖標字符
 */
export function getFieldIcon(type: string): string {
  switch (type) {
    case 'object': return '📁'
    case 'array': return '📊'
    case 'string': return '📄'
    case 'number': 
    case 'integer': return '🔢'
    case 'boolean': return '☑️'
    default: return '📄'
  }
}

/**
 * 切換字段的展開/摺疊狀態
 * @param fields 字段列表
 * @param targetPath 目標字段路徑
 */
export function toggleFieldExpanded(fields: ParsedField[], targetPath: string): void {
  for (const field of fields) {
    if (field.path === targetPath) {
      field.expanded = !field.expanded
      return
    }
    if (field.children) {
      toggleFieldExpanded(field.children, targetPath)
    }
  }
}

/**
 * 從解析的字段中提取所有字段路徑選項
 * @param fields 解析後的字段列表
 * @param options 累積的選項數組
 * @returns 字段路徑選項數組
 */
export function extractFieldPathOptions(fields: ParsedField[], options: Array<{ label: string; value: string }> = []): Array<{ label: string; value: string }> {
  for (const field of fields) {
    // 只添加非對象類型的字段，或者沒有子字段的對象
    if (field.type !== 'object' || !field.children?.length) {
      // 移除 $.content 前綴，顯示相對路徑
      const label = field.path.replace(/^\$\.content\.?/, '') || field.name
      options.push({
        label: label,
        value: field.path
      })
    }
    
    // 遞歸處理子字段
    if (field.children?.length) {
      extractFieldPathOptions(field.children, options)
    }
  }
  
  return options
}

/**
 * 爲ModelDrivenForm等組件提供的Schema解析函數
 * 與原有的resolveActualSchema邏輯兼容
 * @param schema Schema對象
 * @param parentSchema 父級Schema（用於獲取$defs）
 * @returns 解析後的Schema對象
 */
export function resolveActualSchema(schema: any, parentSchema?: any): any {
  const localDefs = parentSchema?.$defs || {}
  // 先解析當前節點自身（處理直接的 anyOf / $ref）
  const base = resolveSchemaRef(schema, localDefs)

  // 對於非對象或空值，直接返回解析結果
  if (!base || typeof base !== 'object') return base

  // 創建淺拷貝，避免意外修改原始 Schema
  const resolved: any = { ...base }

  // 遞歸解析 properties 中的子字段（保持與根級 $defs 一致）
  if (resolved.properties && typeof resolved.properties === 'object') {
    const nextProps: Record<string, any> = {}
    for (const [key, val] of Object.entries(resolved.properties)) {
      nextProps[key] = resolveSchemaRef(val as any, localDefs)
    }
    resolved.properties = nextProps
  }

  // 遞歸解析數組 items（特別是 items.$ref → #/$defs/ModelName 的場景）
  if (resolved.items) {
    resolved.items = resolveSchemaRef(resolved.items, localDefs)
  }

  // 遞歸解析元組 prefixItems
  if (Array.isArray(resolved.prefixItems)) {
    resolved.prefixItems = resolved.prefixItems.map((it: any) => resolveSchemaRef(it, localDefs))
  }

  // 遞歸解析 anyOf 中的子 schema
  if (Array.isArray(resolved.anyOf)) {
    resolved.anyOf = resolved.anyOf.map((it: any) => resolveSchemaRef(it, localDefs))
  }

  return resolved
}

