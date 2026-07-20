import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { getProjects, type ProjectRead } from '@renderer/api/projects'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'
import type {
  AssistantRef,
  AssistantCardRef,
  AssistantRefSource,
  ChapterExcerptRef,
  ReviewResultRef,
} from '@renderer/api/ai'

export type InjectRef = AssistantRef
export type AssistantMessage = { role: 'user' | 'assistant'; content: string; ts?: number }

function getInjectedRefKey(ref: InjectRef): string {
  if (ref.refType === 'card') return `card:${ref.projectId}:${ref.cardId}`
  if (ref.refType === 'chapter_excerpt') {
    return `chapter_excerpt:${ref.projectId}:${ref.cardId}:${ref.fieldPath}:${ref.startLine}:${ref.endLine}:${ref.snapshotHash}`
  }
  return `review_result:${ref.projectId}:${ref.reviewCardId}`
}

function normalizeInjectedRef(ref: Partial<InjectRef> & Record<string, any>, source: AssistantRefSource): InjectRef | null {
  if (!ref) return null
  const refType = (ref.refType || 'card') as InjectRef['refType']

  if (refType === 'card') {
    if (!ref.projectId || !ref.cardId) return null
    return {
      refType: 'card',
      projectId: Number(ref.projectId),
      projectName: String(ref.projectName || ''),
      cardId: Number(ref.cardId),
      cardTitle: String(ref.cardTitle || ''),
      content: ref.content ?? {},
      source,
    }
  }

  if (refType === 'chapter_excerpt') {
    if (!ref.projectId || !ref.cardId || !ref.startLine || !ref.endLine || !ref.snapshotHash) return null
    return {
      refType: 'chapter_excerpt',
      projectId: Number(ref.projectId),
      projectName: String(ref.projectName || ''),
      cardId: Number(ref.cardId),
      cardTitle: String(ref.cardTitle || ''),
      fieldPath: String(ref.fieldPath || 'content'),
      startLine: Number(ref.startLine),
      endLine: Number(ref.endLine),
      text: String(ref.text || ''),
      numberedText: String(ref.numberedText || ''),
      snapshotHash: String(ref.snapshotHash),
      source,
    }
  }

  if (!ref.projectId || !ref.reviewCardId || !ref.targetId) return null
  return {
    refType: 'review_result',
    projectId: Number(ref.projectId),
    reviewCardId: Number(ref.reviewCardId),
    targetId: Number(ref.targetId),
    targetTitle: String(ref.targetTitle || ''),
    reviewType: String(ref.reviewType || 'card'),
    reviewProfile: ref.reviewProfile ?? null,
    qualityGate: String(ref.qualityGate || 'revise'),
    resultText: String(ref.resultText || ''),
    contentSnapshot: ref.contentSnapshot ?? null,
    source,
  }
}

// 卡片上下文資訊接口
export interface CardContextInfo {
  card_id: number
  title: string
  card_type: string
  parent_id: number | null
  project_id: number
  first_seen: number  // timestamp
  last_seen: number   // timestamp
  access_count: number
}

// 用戶操作記錄接口
export interface UserOperation {
  timestamp: number
  type: 'create' | 'edit' | 'delete' | 'move'  // 增加 'move' 類型
  cardId: number
  cardTitle: string
  cardType: string
  detail?: string  // 操作詳情（如層級變化、移動位置等）
}

// 項目結構化上下文接口
export interface ProjectStructureContext {
  project_id: number
  project_name: string
  total_cards: number
  stats: Record<string, number>  // 卡片類型 -> 數量
  tree_text: string              // 樹形文本
  available_card_types: string[] // 可用卡片類型
  last_updated: number           // 最後更新時間戳
  version: number                // 資料版本（用於緩存失效）
}

// 爲避免開發/打包共用本地緩存，對話歷史 key 加上環境前綴
// dev → 'development'，打包 → 'production'
const ENV_PREFIX = (import.meta as any)?.env?.MODE || 'production'
const HISTORY_KEY_PREFIX = `nf:${ENV_PREFIX}:assistant:history:`
const STRUCTURE_KEY_PREFIX = `nf:${ENV_PREFIX}:assistant:structure:`
const OPERATIONS_KEY_PREFIX = `nf:${ENV_PREFIX}:assistant:operations:`

function projectHistoryKey(projectId: number) { return `${HISTORY_KEY_PREFIX}${projectId}` }
function projectStructureKey(projectId: number) { return `${STRUCTURE_KEY_PREFIX}${projectId}` }
function projectOperationsKey(projectId: number) { return `${OPERATIONS_KEY_PREFIX}${projectId}` }

export const useAssistantStore = defineStore('assistant', () => {
  const projects = ref<ProjectRead[]>([])
  // 使用 shallowRef 避免深度響應式包裝卡片內容，提升性能
  const cardsByProject = shallowRef<Record<number, CardRead[]>>({})
  const injectedRefs = shallowRef<InjectRef[]>([])
  
  const activeCardContext = ref<CardContextInfo | null>(null)
  const cardRegistry = ref<Map<number, CardContextInfo>>(new Map())
  const projectCardTypes = ref<string[]>([])
  
  // 項目結構化上下文
  const projectStructure = ref<ProjectStructureContext | null>(null)
  
  // 用戶操作歷史（最多3條）
  const recentOperations = ref<UserOperation[]>([])

  async function loadProjects() {
    projects.value = await getProjects()
  }

  async function loadCardsForProject(pid: number) {
    const list = await getCardsForProject(pid)
    // 創建新對象以觸發 shallowRef 更新
    cardsByProject.value = { ...cardsByProject.value, [pid]: list }
    return list
  }

  function addInjectedRefs(pid: number, pname: string, ids: number[]) {
    const list = cardsByProject.value[pid] || []
    const map = new Map<number, CardRead>()
    list.forEach(c => map.set(c.id, c))
    
    // 創建新數組以觸發 shallowRef 更新
    const newRefs = [...injectedRefs.value]
    
    for (const id of ids) {
      const c = map.get(id)
      if (!c) continue
      const nextRef: AssistantCardRef = {
        refType: 'card',
        projectId: pid,
        projectName: pname,
        cardId: id,
        cardTitle: c.title,
        content: (c as any).content,
        source: 'manual',
      }
      const key = getInjectedRefKey(nextRef)
      const existingIdx = newRefs.findIndex(r => getInjectedRefKey(r) === key)
      if (existingIdx >= 0) {
        // 升級爲 manual（若原爲 auto）並刷新標題/內容
        const prev = newRefs[existingIdx]
        newRefs[existingIdx] = { ...prev, ...nextRef, source: 'manual' } as InjectRef
        continue
      }
      newRefs.push(nextRef)
    }
    
    injectedRefs.value = newRefs
  }

  function addInjectedRefDirect(ref: InjectRef | (Partial<InjectRef> & Record<string, any>), source: AssistantRefSource = 'manual') {
    const normalizedRef = normalizeInjectedRef(ref as any, source)
    if (!normalizedRef) return
    
    // 創建新數組以觸發 shallowRef 更新
    const newRefs = [...injectedRefs.value]
    const key = getInjectedRefKey(normalizedRef)
    const idx = newRefs.findIndex(r => getInjectedRefKey(r) === key)
    const prev = idx >= 0 ? newRefs[idx] : null
    
    // 規則：manual 永遠不被 auto 覆蓋；manual 會覆蓋 auto；同源則更新內容
    if (idx >= 0) {
      if (prev?.source === 'manual' && source === 'auto') {
        // 保留 manual，不做降級，僅更新顯示資訊/內容
        newRefs[idx] = { ...prev, ...normalizedRef, source: 'manual' } as InjectRef
      } else {
        newRefs[idx] = { ...prev, ...normalizedRef, source } as InjectRef
      }
    } else {
      newRefs.push(normalizedRef)
    }
    
    injectedRefs.value = newRefs
  }

  function clearAutoRefs() {
    injectedRefs.value = injectedRefs.value.filter(r => r.source !== 'auto')
  }

  function addAutoRef(ref: InjectRef) {
    // 僅清除其他 auto；若相同卡片已被標記爲 manual，則不會被覆蓋
    clearAutoRefs()
    addInjectedRefDirect(ref, 'auto')
  }

  function addChapterExcerptRef(ref: ChapterExcerptRef, source: AssistantRefSource = 'manual') {
    addInjectedRefDirect(ref, source)
  }

  function addReviewResultRef(ref: ReviewResultRef, source: AssistantRefSource = 'manual') {
    addInjectedRefDirect(ref, source)
  }

  function removeInjectedRefAt(index: number) { 
    // 創建新數組以觸發 shallowRef 更新
    injectedRefs.value = injectedRefs.value.filter((_, i) => i !== index)
  }
  function clearInjectedRefs() { injectedRefs.value = [] }

  // --- 對話歷史（按項目持久化到 localStorage）---
  function getHistory(projectId: number): AssistantMessage[] {
    try {
      const raw = localStorage.getItem(projectHistoryKey(projectId))
      if (!raw) return []
      const arr = JSON.parse(raw)
      if (!Array.isArray(arr)) return []
      return arr as AssistantMessage[]
    } catch { return [] }
  }

  function setHistory(projectId: number, history: AssistantMessage[]) {
    try {
      localStorage.setItem(projectHistoryKey(projectId), JSON.stringify(history || []))
    } catch {}
  }

  function appendHistory(projectId: number, msg: AssistantMessage) {
    const hist = getHistory(projectId)
    hist.push({ ...msg, ts: msg.ts ?? Date.now() })
    setHistory(projectId, hist)
  }

  function clearHistory(projectId: number) {
    try { localStorage.removeItem(projectHistoryKey(projectId)) } catch {}
  }
  
  // 卡片上下文管理方法
  function updateActiveCard(card: CardRead | null, projectId: number) {
    if (!card) {
      activeCardContext.value = null
      console.log('📋 [AssistantStore] 清空活動卡片')
      return
    }
    
    const now = Date.now()
    const info: CardContextInfo = {
      card_id: card.id,
      title: card.title,
      card_type: (card as any).card_type?.name || 'Unknown',  // 修復：使用 card_type.name
      parent_id: (card as any).parent_id || null,
      project_id: projectId,
      first_seen: now,
      last_seen: now,
      access_count: 1
    }
    
    console.log('📋 [AssistantStore] 更新活動卡片:', info)
    
    // 更新活動卡片
    activeCardContext.value = info
    
    // 註冊到卡片註冊表（如果已存在則更新訪問資訊）
    registerCard(info)
  }
  
  function registerCard(info: CardContextInfo) {
    const existing = cardRegistry.value.get(info.card_id)
    if (existing) {
      // 更新已存在的卡片資訊
      cardRegistry.value.set(info.card_id, {
        ...existing,
        title: info.title,  // 更新標題（可能改變）
        card_type: info.card_type,
        last_seen: Date.now(),
        access_count: existing.access_count + 1
      })
    } else {
      // 新卡片
      cardRegistry.value.set(info.card_id, info)
    }
  }
  
  function updateProjectCardTypes(types: string[]) {
    projectCardTypes.value = types
  }
  
  function getContextForAssistant(): {
    active_card: CardContextInfo | null
    recent_cards: CardContextInfo[]
    card_types: string[]
  } {
    // 獲取最近訪問的卡片（最多10個，按last_seen排序）
    const recent = Array.from(cardRegistry.value.values())
      .sort((a, b) => b.last_seen - a.last_seen)
      .slice(0, 10)
    
    return {
      active_card: activeCardContext.value,
      recent_cards: recent,
      card_types: projectCardTypes.value
    }
  }
  
  function clearCardContext() {
    activeCardContext.value = null
    cardRegistry.value.clear()
    projectCardTypes.value = []
  }
  
  //  ========== 項目結構化上下文管理 ==========
  
  /**
   * 從 localStorage 載入項目結構緩存
   */
  function loadProjectStructureFromCache(projectId: number): ProjectStructureContext | null {
    try {
      const raw = localStorage.getItem(projectStructureKey(projectId))
      if (!raw) return null
      const data = JSON.parse(raw)
      return data as ProjectStructureContext
    } catch {
      return null
    }
  }
  
  /**
   * 儲存項目結構到 localStorage
   */
  function saveProjectStructureToCache(structure: ProjectStructureContext) {
    try {
      localStorage.setItem(projectStructureKey(structure.project_id), JSON.stringify(structure))
    } catch (e) {
      console.warn('儲存項目結構緩存失敗', e)
    }
  }

  let projectStructureSourceKey = ''

  function getProjectStructureSourceKey(projectId: number, cards: CardRead[], cardTypes: any[]): string {
    const cardKey = cards.map(card => [
      card.id,
      card.parent_id ?? '',
      card.display_order ?? '',
      card.title || '',
      card.card_type?.name || '',
      (card as any).updated_at || '',
    ].join(':')).join('|')
    const typeKey = cardTypes.map(type => `${type.id ?? ''}:${type.name ?? ''}`).join('|')
    return `${projectId}::${cardKey}::${typeKey}`
  }

  function markCurrentCardInTreeText(treeText: string, currentCardId?: number): string {
    const withoutMarker = String(treeText || '').replace(/ ⭐當前/g, '')
    if (!currentCardId) return withoutMarker
    const cardToken = `{id:${currentCardId} |`
    return withoutMarker
      .split('\n')
      .map(line => line.includes(cardToken) ? line.replace(/}$/, ' ⭐當前}') : line)
      .join('\n')
  }
  
  /**
   * 構建卡片樹形文本（遞歸）
   */
  function buildCardTreeText(cards: CardRead[], parentId: number | null = null, depth: number = 0, currentCardId?: number): string {
    const indent = depth === 0 ? '' : '│  '.repeat(depth - 1) + '├─ '
    const children = cards.filter(c => (c as any).parent_id === parentId)
      .sort((a, b) => ((a as any).display_order || 0) - ((b as any).display_order || 0))
    
    const lines: string[] = []
    
    for (let i = 0; i < children.length; i++) {
      const card = children[i]
      const typeName = (card as any).card_type?.name || 'Unknown'
      const updatedAt = (card as any).updated_at
      const updatedDate = updatedAt ? new Date(updatedAt).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) : ''
      const isCurrent = currentCardId && card.id === currentCardId
      const marker = isCurrent ? ' ⭐當前' : ''
      
      lines.push(`${indent}[${typeName}] ${card.title} {id:${card.id} | 更新:${updatedDate}${marker}}`)
      
      // 遞歸處理子卡片
      const childText = buildCardTreeText(cards, card.id, depth + 1, currentCardId)
      if (childText) {
        lines.push(childText)
      }
    }
    
    return lines.join('\n')
  }
  
  /**
   * 從卡片資料生成項目結構化上下文
   * @param projectId 項目ID
   * @param projectName 項目名稱
   * @param cards 所有卡片資料（來自 useCardStore）
   * @param cardTypes 所有卡片類型（來自 useCardStore）
   * @param currentCardId 當前激活的卡片ID（可選）
   */
  function buildProjectStructure(
    projectId: number,
    projectName: string,
    cards: CardRead[],
    cardTypes: any[],
    currentCardId?: number
  ): ProjectStructureContext {
    // 統計各類型卡片數量
    const stats: Record<string, number> = {}
    for (const card of cards) {
      const typeName = (card as any).card_type?.name || '未分類'
      stats[typeName] = (stats[typeName] || 0) + 1
    }
    
    // 生成樹形文本
    const treeText = buildCardTreeText(cards, null, 0, currentCardId)
    
    // 可用卡片類型
    const availableTypes = cardTypes.map(ct => ct.name)
    
    return {
      project_id: projectId,
      project_name: projectName,
      total_cards: cards.length,
      stats,
      tree_text: treeText || 'ROOT\n(暫無卡片)',
      available_card_types: availableTypes,
      last_updated: Date.now(),
      version: cards.length  // 簡單用卡片數量作爲版本號
    }
  }
  
  /**
   * 更新項目結構（自動構建+緩存）
   * @param projectId 項目ID
   * @param projectName 項目名稱
   * @param cards 所有卡片資料
   * @param cardTypes 所有卡片類型
   * @param currentCardId 當前卡片ID
   * @param forceRebuild 是否強制重建（忽略緩存）
   */
  function updateProjectStructure(
    projectId: number,
    projectName: string,
    cards: CardRead[],
    cardTypes: any[],
    currentCardId?: number,
    forceRebuild: boolean = false
  ) {
    const sourceKey = getProjectStructureSourceKey(projectId, cards, cardTypes)
    if (!forceRebuild && projectStructure.value && projectStructureSourceKey === sourceKey) {
      // 單純切換目前卡片時，結構本身沒有改變，只更新標記即可。
      projectStructure.value = {
        ...projectStructure.value,
        tree_text: markCurrentCardInTreeText(projectStructure.value.tree_text, currentCardId),
        last_updated: Date.now(),
      }
      return
    }

    // 檢查緩存是否有效
    if (!forceRebuild) {
      const cached = loadProjectStructureFromCache(projectId)
      if (cached && cached.version === cards.length) {
        // 來源內容可能已更新，因此首次仍重建；後續切卡會走上方快速路徑。
        const updated = buildProjectStructure(projectId, projectName, cards, cardTypes, currentCardId)
        projectStructure.value = updated
        projectStructureSourceKey = sourceKey
        saveProjectStructureToCache(updated)
        console.log('📋 [AssistantStore] 使用緩存的項目結構（已更新當前卡片）')
        return
      }
    }
    
    // 重新構建
    const structure = buildProjectStructure(projectId, projectName, cards, cardTypes, currentCardId)
    projectStructure.value = structure
    projectStructureSourceKey = sourceKey
    saveProjectStructureToCache(structure)
    console.log('📋 [AssistantStore] 已構建項目結構:', structure)
  }
  
  /**
   * 清除項目結構緩存
   */
  function clearProjectStructure() {
    projectStructure.value = null
  }
  
  // ========== 用戶操作歷史管理 ==========
  
  /**
   * 從 localStorage 載入操作歷史
   */
  function loadOperationsFromCache(projectId: number): UserOperation[] {
    try {
      const raw = localStorage.getItem(projectOperationsKey(projectId))
      if (!raw) return []
      const arr = JSON.parse(raw)
      if (!Array.isArray(arr)) return []
      return arr as UserOperation[]
    } catch {
      return []
    }
  }
  
  /**
   * 儲存操作歷史到 localStorage
   */
  function saveOperationsToCache(projectId: number, operations: UserOperation[]) {
    try {
      localStorage.setItem(projectOperationsKey(projectId), JSON.stringify(operations))
    } catch (e) {
      console.warn('儲存操作歷史失敗', e)
    }
  }
  
  /**
   * 記錄用戶操作
   */
  function recordOperation(projectId: number, op: Omit<UserOperation, 'timestamp'>) {
    const operation: UserOperation = {
      ...op,
      timestamp: Date.now()
    }
    
    // 添加到內存
    recentOperations.value.unshift(operation)
    
    // 保持最多3條
    if (recentOperations.value.length > 3) {
      recentOperations.value = recentOperations.value.slice(0, 3)
    }
    
    // 儲存到緩存
    saveOperationsToCache(projectId, recentOperations.value)
    
    console.log('📝 [AssistantStore] 記錄操作:', operation)
  }
  
  /**
   * 載入操作歷史
   */
  function loadOperations(projectId: number) {
    recentOperations.value = loadOperationsFromCache(projectId)
  }
  
  /**
   * 格式化操作歷史爲文本
   */
  function formatRecentOperations(): string {
    if (recentOperations.value.length === 0) return ''
    
    const lines = recentOperations.value.map((op, idx) => {
      const time = new Date(op.timestamp).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
      const emoji = op.type === 'create' ? '➕' : 
                    op.type === 'edit' ? '✏️' : 
                    op.type === 'move' ? '📦' : 
                    '🗑️'
      const action = op.type === 'create' ? '創建' : 
                     op.type === 'edit' ? '編輯' : 
                     op.type === 'move' ? '移動' : 
                     '刪除'
      
      let line = `${idx + 1}. [${time}] ${emoji} ${action} "${op.cardTitle}" (${op.cardType} #${op.cardId})`
      
      // 如果有詳細資訊，添加到下一行
      if (op.detail) {
        line += `\n   詳情: ${op.detail}`
      }
      
      return line
    })
    
    return lines.join('\n')
  }
  
  /**
   * 清除操作歷史
   */
  function clearOperations(projectId: number) {
    recentOperations.value = []
    try {
      localStorage.removeItem(projectOperationsKey(projectId))
    } catch {}
  }

  return { 
    projects, cardsByProject, injectedRefs, 
    loadProjects, loadCardsForProject, 
    addInjectedRefs, addInjectedRefDirect, addAutoRef, addChapterExcerptRef, addReviewResultRef, clearAutoRefs, removeInjectedRefAt, clearInjectedRefs, 
    getHistory, setHistory, appendHistory, clearHistory,
    // 卡片上下文方法
    updateActiveCard, registerCard, updateProjectCardTypes, getContextForAssistant, clearCardContext,
    activeCardContext, cardRegistry, projectCardTypes,
    // 項目結構化上下文方法
    projectStructure,
    updateProjectStructure,
    clearProjectStructure,
    //  操作歷史方法
    recentOperations,
    recordOperation,
    loadOperations,
    formatRecentOperations,
    clearOperations
  }
}) 
