export interface SectionConfig {
  title: string
  include?: string[]
  exclude?: string[]
  description?: string
  collapsed?: boolean
}

interface LayoutSources {
  schemaMeta?: Record<string, any>
  backendLayout?: SectionConfig[] | undefined
  frontendDefault?: SectionConfig[] | undefined
}

// Built-in schema fields have stable product-facing labels.  This also repairs
// legacy schemas whose title was generated from the first words of description.
const BUILTIN_FIELD_TITLES: Record<string, string> = {
  story_type: '故事線類型',
  name: '名稱',
  overview: '概述',
  main_target: '主線目標',
  branch_line: '輔線',
  new_character_cards: '新增角色卡',
  new_scene_cards: '新增場景卡',
  character_action_list: '角色行動列表',
  entity_snapshot: '實體狀態快照',
}

export function resolveBuiltinFieldTitle(key: string): string | undefined {
  return BUILTIN_FIELD_TITLES[key]
}

// 簡單合併策略：schemaMeta>backend>frontend
export function mergeSections(sources: LayoutSources): SectionConfig[] | undefined {
  if (sources.schemaMeta && Array.isArray(sources.schemaMeta.sections)) {
    return normalizeSections(sources.schemaMeta.sections, sources.schemaMeta)
  }
  if (sources.backendLayout && sources.backendLayout.length) return normalizeSections(sources.backendLayout, sources.schemaMeta)
  if (sources.frontendDefault && sources.frontendDefault.length) return normalizeSections(sources.frontendDefault, sources.schemaMeta)
  return undefined
}

function normalizeSections(sections: any[], schemaLike?: any): SectionConfig[] {
  return sections.map(s => ({
    title: normalizeSectionTitle(String(s.title ?? '分區'), s.include, schemaLike),
    include: s.include ? [...s.include] : undefined,
    exclude: s.exclude ? [...s.exclude] : undefined,
    description: s.description,
    collapsed: !!s.collapsed,
  }))
}

function normalizeSectionTitle(rawTitle: string, include: any, schemaLike?: any): string {
  const title = (rawTitle || '').trim()
  const includeKeys = Array.isArray(include) ? include : []
  if (includeKeys.length !== 1) return title || '分區'

  const key = String(includeKeys[0] || '').trim()
  if (!key) return title || '分區'

  const resolved = resolveSectionTitle(schemaLike, key)
  if (!title || title === key || title.toLowerCase() === key.toLowerCase()) {
    return resolved || key
  }
  return title
}

export function autoGroup(schema: any): SectionConfig[] {
  const props: Record<string, any> = schema?.properties || {}
  const keys = Object.keys(props)
  const objectKeys = keys.filter(k => resolveType(props[k]) === 'object')
  const arrayKeys = keys.filter(k => resolveType(props[k]) === 'array')
  const scalarKeys = keys.filter(k => !['object','array'].includes(resolveType(props[k])))

  const sections: SectionConfig[] = []
  if (scalarKeys.length) sections.push({ title: '基礎信息', include: scalarKeys })
  for (const k of objectKeys) sections.push({ title: resolveSectionTitle(schema, k), include: [k] })
  for (const k of arrayKeys) sections.push({ title: resolveSectionTitle(schema, k), include: [k], collapsed: true })
  return sections
}

function resolveSectionTitle(schema: any, key: string): string {
  const builtinTitle = resolveBuiltinFieldTitle(key)
  if (builtinTitle) return builtinTitle

  const fieldSchema = schema?.properties?.[key]
  const directTitle = typeof fieldSchema?.title === 'string' ? fieldSchema.title.trim() : ''
  if (directTitle) return directTitle

  const ref = typeof fieldSchema?.$ref === 'string' ? fieldSchema.$ref : ''
  if (ref.startsWith('#/$defs/')) {
    const refName = ref.split('/').pop() || ''
    const refTitle = typeof schema?.$defs?.[refName]?.title === 'string'
      ? schema.$defs[refName].title.trim()
      : ''
    if (refTitle) return refTitle
  }

  return key
}

function resolveType(s: any): string {
  if (!s) return 'object'
  if (s.anyOf) {
    const first = s.anyOf.find((x: any) => x && x.type && x.type !== 'null')
    if (first) return first.type
  }
  if (s.$ref) return 'object'
  return s.type || 'object'
} 
