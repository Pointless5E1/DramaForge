<template>
  <div class="editor-layout">
    <!-- 左側卡片導航樹 -->
    <el-aside class="sidebar card-navigation-sidebar" :style="{ width: leftSidebarDisplayWidth + 'px' }" @contextmenu.prevent="onSidebarContextMenu">
      <div class="sidebar-header">
        <h3 class="sidebar-title">創作卡片</h3>
        
      </div>

      <!-- 上半區（類型列表 + 自由卡片庫） -->
      <div class="types-pane" :style="{ height: typesPaneHeight + 'px' }" @dragover.prevent @drop="onTypesPaneDrop">
        <div class="pane-title">已有卡片類型</div>
        <el-scrollbar class="types-scroll">
          <ul class="types-list">
            <li v-for="t in cardStore.cardTypes" :key="t.id" class="type-item" draggable="true"
                @dragstart="onTypeDragStart(t)">
              <span class="type-name">{{ t.name }}</span>
            </li>
          </ul>
        </el-scrollbar>
      </div>
      <!-- 內部分割條（垂直） -->
      <div class="inner-resizer" @mousedown="startResizingInner"></div>

      <!-- 下半區：項目卡片樹 -->
      <div class="cards-pane" :style="{ height: `calc(100% - ${typesPaneHeight + innerResizerThickness}px)` }" @dragover.prevent @drop="onCardsPaneDrop">
        <div class="cards-title">
          <div class="cards-title-head">
            <div class="cards-title-text">當前項目：{{ projectStore.currentProject?.name }}</div>
            <div v-if="selectedCardIds.length > 0" class="cards-selection-chip">已選 {{ selectedCardIds.length }}</div>
          </div>
          <div class="cards-title-actions">
            <el-button
              class="toolbar-action"
              :class="selectedCardIds.length > 0 ? 'toolbar-action-create-split' : 'toolbar-action-create-full'"
              size="small"
              type="primary"
              :icon="Plus"
              @click="openCreateRoot"
            >
              新建卡片
            </el-button>
            <el-button
              v-if="selectedCardIds.length > 0"
              class="toolbar-action toolbar-action-danger toolbar-action-danger-split"
              size="small"
              type="danger"
              :icon="Delete"
              @click="batchDeleteCards"
            >
              刪除選中 ({{ selectedCardIds.length }})
            </el-button>
            <el-button v-if="!isFreeProject" class="toolbar-action toolbar-action-secondary" size="small" :icon="Upload" @click="openImportFreeCards">導入卡片</el-button>
            <el-button class="toolbar-action toolbar-action-secondary" :class="{ 'toolbar-action-secondary--solo': isFreeProject }" size="small" :icon="Download" @click="openExportDialog">導出卡片</el-button>
          </div>
        </div>
        
        <!-- 搜索框 -->
        <div class="search-box" style="padding: 0 8px 8px;">
           <el-input 
             v-model="searchQuery" 
             placeholder="搜索卡片..." 
             :prefix-icon="Search"
             clearable
             @input="handleSearch"
           />
        </div>

        <!-- 搜索結果 -->
        <div v-if="isSearching" class="search-results-list" v-loading="searchLoading">
           <div 
             v-for="card in searchResults" 
             :key="card.id" 
             class="search-item" 
             @click="handleNodeClick({ id: card.id, title: card.title, card_type: card.card_type })"
           >
              <el-icon class="card-icon"><component :is="getIconByCardType(card.card_type?.name)" /></el-icon>
              <span class="search-item-title">{{ card.title }}</span>
           </div>
           <el-empty v-if="!searchLoading && searchResults.length === 0" description="無搜索結果" :image-size="60" />
        </div>

        <template v-else>
          <el-tree
            v-if="groupedTree.length > 0"
            ref="treeRef"
            :data="groupedTree"
            node-key="id"
            :default-expanded-keys="expandedKeys"
            :expand-on-click-node="false"
            @node-click="handleNodeClick"
            @node-expand="onNodeExpand"
            @node-collapse="onNodeCollapse"
            draggable
            :allow-drop="handleAllowDrop"
            :allow-drag="handleAllowDrag"
            @node-drop="handleNodeDrop"
            class="card-tree"
          >
            <template #default="{ node, data }">
              <el-dropdown class="full-row-dropdown" trigger="contextmenu" @command="(cmd:string) => handleContextCommand(cmd, data)">
                <div 
                  class="custom-tree-node full-row" 
                  :class="{ 'selected': isCardSelected(data.id) }"
                  @click.stop="handleCardClick($event, data)"
                  @dragover.prevent 
                  @drop="(e:any) => onExternalDropToNode(e, data)" 
                  @dragenter.prevent
                >
                  <el-icon class="card-icon"> 
                    <component :is="getIconByCardType(data.card_type?.name || data.__groupType)" />
                  </el-icon>
                  <span class="label">{{ node.label || data.title }}</span>
                  <span v-if="data.children && data.children.length > 0" class="child-count">{{ data.children.length }}</span>
                </div>
                <template #dropdown>
                  <el-dropdown-menu>
                    <template v-if="!data.__isGroup">
                      <el-dropdown-item command="create-child" :disabled="selectedCardIds.length > 1">新建子卡片</el-dropdown-item>
                      <el-dropdown-item command="rename" :disabled="selectedCardIds.length > 1">重命名</el-dropdown-item>
                      <el-dropdown-item command="edit-structure" :disabled="selectedCardIds.length > 1">結構編輯</el-dropdown-item>
                      <el-dropdown-item command="add-as-reference" :disabled="selectedCardIds.length > 1">添加爲引用</el-dropdown-item>
                      <el-dropdown-item v-if="selectedCardIds.length > 1" command="batch-delete" divided>刪除選中的卡片 ({{ selectedCardIds.length }})</el-dropdown-item>
                      <el-dropdown-item v-else command="delete" divided>刪除卡片</el-dropdown-item>
                    </template>
                    <template v-else>
                      <el-dropdown-item command="create-child-in-group">新建子卡片</el-dropdown-item>
                      <el-dropdown-item command="delete-group" divided>刪除該分組下所有卡片</el-dropdown-item>
                    </template>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-tree>
          <el-empty v-else description="暫無卡片" :image-size="80"></el-empty>
        </template>
      </div>

      <!-- 空白區域右鍵菜單（手動觸發） -->
      <span ref="blankMenuRef" class="blank-menu-ref" :style="{ position: 'fixed', left: blankMenuX + 'px', top: blankMenuY + 'px', width: '1px', height: '1px' }"></span>
      <el-dropdown v-model:visible="blankMenuVisible" trigger="manual">
        <span></span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="openCreateRoot">新建卡片</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </el-aside>
    
    <!-- 拖拽條 -->
    <div v-if="isLeftSidebarVisible" class="resizer left-resizer" @mousedown="startResizing('left')"></div>

    <!-- 中欄主內容區 -->
    <el-main class="main-content">
      <el-tabs v-model="activeTab" type="border-card" class="main-tabs">
        <el-tab-pane label="卡片庫" name="market">
          <CardMarket @edit-card="handleEditCard" />
        </el-tab-pane>
        <el-tab-pane label="編輯器" name="editor">
          <template v-if="activeCard">
            <CardEditorHost :card="activeCard" :prefetched="prefetchedContext" />
          </template>
          <el-empty v-else description="請從左側選擇一個卡片進行編輯" />
        </el-tab-pane>
        <el-tab-pane label="關係圖管理" name="relation-graph">
          <RelationGraphPanel :refresh-seq="relationGraphRefreshSeq" />
        </el-tab-pane>
      </el-tabs>
    </el-main>

    <!-- 右側助手面板分隔條與面板 -->
    <div class="resizer right-resizer" @mousedown="startResizing('right')"></div>
    <el-aside class="sidebar assistant-sidebar" :style="{ width: rightSidebarWidth + 'px' }">
      <!-- 章節正文卡片：顯示4個Tab -->
      <template v-if="showRightSidebarTabs">
        <el-tabs v-model="activeRightTab" type="card" class="right-tabs">
          <el-tab-pane label="助手" name="assistant">
            <AssistantPanel
              :resolved-context="assistantResolvedContext"
              :llm-config-id="assistantParams.llm_config_id as any"
              :prompt-name="'靈感對話'"
              :temperature="assistantParams.temperature as any"
              :max_tokens="assistantParams.max_tokens as any"
              :timeout="assistantParams.timeout as any"
              :effective-schema="assistantEffectiveSchema"
              :generation-prompt-name="assistantParams.prompt_name as any"
              :current-card-title="assistantSelectionCleared ? '' : (activeCard?.title as any)"
              :current-card-content="assistantSelectionCleared ? null : (activeCard?.content as any)"
              @refresh-context="refreshAssistantContext"
              @reset-selection="resetAssistantSelection"
              @finalize="assistantFinalize"
              @jump-to-card="handleJumpToCard"
            />
          </el-tab-pane>
          
          <template v-if="isChapterContent">
          <el-tab-pane label="參與實體" name="context">
            <ContextPanel 
              :project-id="projectStore.currentProject?.id"
              :prefetched="prefetchedContext"
              :volume-number="chapterVolumeNumber"
              :chapter-number="chapterChapterNumber"
              :participants="chapterParticipants"
              @update:participants="handleContextParticipantsUpdate"
              @context-updated="handleContextAssembledUpdate"
            />
          </el-tab-pane>
          
          <el-tab-pane label="提取" name="extract">
            <ChapterToolsPanel />
          </el-tab-pane>
          
          <el-tab-pane label="大綱" name="outline">
            <OutlinePanel 
              :active-card="activeCard"
              :volume-number="chapterVolumeNumber"
              :chapter-number="chapterChapterNumber"
            />
          </el-tab-pane>
          </template>
          
          <el-tab-pane label="審核結果" name="review-history">
            <ReviewHistoryPanel
              :target-card-id="reviewTargetCardIdForSidebar"
            />
          </el-tab-pane>
        </el-tabs>
      </template>
      
      <!-- 其他卡片：僅顯示助手 -->
      <AssistantPanel
        v-else
        :resolved-context="assistantResolvedContext"
        :llm-config-id="assistantParams.llm_config_id as any"
        :prompt-name="'靈感對話'"
        :temperature="assistantParams.temperature as any"
        :max_tokens="assistantParams.max_tokens as any"
        :timeout="assistantParams.timeout as any"
        :effective-schema="assistantEffectiveSchema"
        :generation-prompt-name="assistantParams.prompt_name as any"
        :current-card-title="assistantSelectionCleared ? '' : (activeCard?.title as any)"
        :current-card-content="assistantSelectionCleared ? null : (activeCard?.content as any)"
        @refresh-context="refreshAssistantContext"
        @reset-selection="resetAssistantSelection"
        @finalize="assistantFinalize"
        @jump-to-card="handleJumpToCard"
      />
    </el-aside>
    <el-tooltip :content="isLeftSidebarVisible ? '收起左側導航' : '展開左側導航'" placement="right">
      <button
        type="button"
        class="sidebar-edge-toggle"
        :class="{ 'is-collapsed': !isLeftSidebarVisible }"
        :style="{ left: `${leftSidebarToggleOffset}px` }"
        :aria-label="isLeftSidebarVisible ? '收起左側導航' : '展開左側導航'"
        @click="toggleLeftSidebar"
      >
        <el-icon class="sidebar-edge-toggle__icon">
          <component :is="isLeftSidebarVisible ? ArrowLeft : ArrowRight" />
        </el-icon>
      </button>
    </el-tooltip>
  </div>

  <!-- 新建卡片對話框 -->
  <el-dialog v-model="isCreateCardDialogVisible" title="新建創作卡片" width="500px">
    <el-form :model="newCardForm" label-position="top">
      <el-form-item label="卡片標題">
        <el-input v-model="newCardForm.title" placeholder="請輸入卡片標題"></el-input>
      </el-form-item>
      <el-form-item label="卡片類型">
        <el-select v-model="newCardForm.card_type_id" placeholder="請選擇卡片類型" style="width: 100%">
          <el-option
            v-for="type in cardStore.cardTypes"
            :key="type.id"
            :label="type.name"
            :value="type.id"
          ></el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="父級卡片 (可選)">
                <el-tree-select
           v-model="newCardForm.parent_id"
           :data="cardTree"
           :props="treeSelectProps"
           check-strictly
           :render-after-expand="false"
           placeholder="選擇父級卡片"
           clearable
           style="width: 100%"
         />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="isCreateCardDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleCreateCard">創建</el-button>
    </template>
  </el-dialog>

  <!-- 導入卡片對話框 -->
  <el-dialog v-model="importDialog.visible" title="導入卡片" width="900px" class="nf-import-dialog">
    <div style="display:flex; gap:12px; align-items:center; margin-bottom:8px; flex-wrap: wrap;">
      <el-select v-model="importDialog.sourcePid" placeholder="來源項目" style="width:220px" @change="onImportSourceChange($event as any)">
        <el-option v-for="p in importDialog.projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-input v-model="importDialog.search" placeholder="搜索來源卡片標題..." clearable style="flex:1; min-width: 200px" />
      <el-select v-model="importFilter.types" multiple collapse-tags placeholder="類型篩選" style="min-width:220px;" :max-collapse-tags="2">
        <el-option v-for="t in cardStore.cardTypes" :key="t.id" :label="t.name" :value="t.id!" />
      </el-select>
      <el-tree-select
        v-model="importDialog.parentId"
        :data="cardTree"
        :props="treeSelectProps"
        check-strictly
        :render-after-expand="false"
        placeholder="目標父級 (可選)"
        clearable
        popper-class="nf-tree-select-popper"
        style="width: 300px"
      />
    </div>
    <el-table :data="filteredImportCards" height="360px" border @selection-change="onImportSelectionChange">
      <el-table-column type="selection" width="48" />
      <el-table-column label="標題" prop="title" min-width="220" />
      <el-table-column label="類型" min-width="160">
        <template #default="{ row }">{{ row.card_type?.name }}</template>
      </el-table-column>
      <el-table-column label="創建時間" min-width="160">
        <template #default="{ row }">{{ (row as any).created_at }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="importDialog.visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedImportIds.length" @click="confirmImportCards">導入所選</el-button>
    </template>
  </el-dialog>

  <SchemaStudio v-model:visible="schemaStudio.visible" :mode="'card'" :target-id="schemaStudio.cardId" :context-title="schemaStudio.cardTitle" @saved="onCardSchemaSaved" />
  <CardExportDialog
    v-model="exportDialogVisible"
    :project-id="projectStore.currentProject?.id"
    :project-name="projectStore.currentProject?.name"
    :cards="cards as any"
    :card-types="cardStore.cardTypes as any"
    :initial-card-id="selectedCardIds.length === 1 ? selectedCardIds[0] : ((activeCard as any)?.id ?? null)"
  />

  
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, defineAsyncComponent, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { Plus, Search, Upload, Download, Delete, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { debounce } from 'lodash-es'
import { 
  Box,
  CollectionTag,
  MagicStick,
  ChatLineRound,
  List,
  Connection,
  Tickets,
  Notebook,
  User,
  OfficeBuilding,
  Document,
  Folder,
} from '@element-plus/icons-vue'
import type { components } from '@renderer/types/generated'
import { useSidebarResizer } from '@renderer/composables/useSidebarResizer'
import AssistantPanel from '@renderer/components/assistants/AssistantPanel.vue'
import ContextPanel from '@renderer/components/panels/ContextPanel.vue'
import ChapterToolsPanel from '@renderer/components/panels/ChapterToolsPanel.vue'
import OutlinePanel from '@renderer/components/panels/OutlinePanel.vue'
import ReviewHistoryPanel from '@renderer/components/panels/ReviewHistoryPanel.vue'
import RelationGraphPanel from '@renderer/components/panels/RelationGraphPanel.vue'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useEditorStore } from '@renderer/stores/useEditorStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import SchemaStudio from '@renderer/components/shared/SchemaStudio.vue'
import { getCardSchema, createCardType } from '@renderer/api/setting'
import { getProjects } from '@renderer/api/projects'
import { getCardsForProject, copyCard, getCardAIParams, searchCards } from '@renderer/api/cards'
import { generateAIContent } from '@renderer/api/ai'
import type { AssistantRef, ChapterExcerptRef, ReviewResultRef } from '@renderer/api/ai'
 
 // Mock components that will be created later
 const CardEditorHost = defineAsyncComponent(() => import('@renderer/components/cards/CardEditorHost.vue'));
 const CardMarket = defineAsyncComponent(() => import('@renderer/components/cards/CardMarket.vue'));
 const CardExportDialog = defineAsyncComponent(() => import('@renderer/components/cards/CardExportDialog.vue'));


 type Project = components['schemas']['ProjectRead']
 type CardRead = components['schemas']['CardRead']
 type CardCreate = components['schemas']['CardCreate']

 // 導入卡片對話框狀態
 const importDialog = ref<{ visible: boolean; search: string; parentId: number | null; sourcePid: number | null; projects: Array<{id:number; name:string}> }>({ visible: false, search: '', parentId: null, sourcePid: null, projects: [] })
 const importSourceCards = ref<CardRead[]>([])
 const selectedImportIds = ref<number[]>([])
 
 // 過濾：類型 + 標題
 const importFilter = ref<{ types: number[] }>({ types: [] })
 
 const filteredImportCards = computed(() => {
   const q = (importDialog.value.search || '').trim().toLowerCase()
   let list = importSourceCards.value || []
   if (importFilter.value.types.length) {
     const typeSet = new Set(importFilter.value.types)
     list = list.filter(c => c.card_type?.id && typeSet.has(c.card_type.id))
   }
   if (q) {
     list = list.filter(c => (c.title || '').toLowerCase().includes(q))
   }
   return list
 })

async function openImportFreeCards() {
  try {
    const list = await getProjects()
    const currentId = projectStore.currentProject?.id
     importDialog.value.projects = (list || []).filter(p => p.id !== currentId).map(p => ({ id: p.id!, name: p.name! }))
     importDialog.value.sourcePid = importDialog.value.projects[0]?.id ?? null
     selectedImportIds.value = []
     await onImportSourceChange(importDialog.value.sourcePid as any)
     importDialog.value.visible = true
   } catch { ElMessage.error('加載來源項目失敗') }
 }

function openExportDialog() {
  if (!projectStore.currentProject?.id) {
    ElMessage.warning('請先選擇項目')
    return
  }
  if ((cards.value || []).length === 0) {
    ElMessage.warning('當前項目暫無可導出的卡片')
    return
  }
  exportDialogVisible.value = true
}

 async function onImportSourceChange(pid: number | null) {
   importSourceCards.value = []
   if (!pid) return
   try { importSourceCards.value = await getCardsForProject(pid) } catch { importSourceCards.value = [] }
 }

 function onImportSelectionChange(rows: any[]) {
   selectedImportIds.value = (rows || []).map(r => Number(r.id)).filter(n => Number.isFinite(n))
 }

 async function confirmImportCards() {
   try {
     const pid = projectStore.currentProject?.id
     if (!pid) return
     const targetParent = importDialog.value.parentId || null
     for (const id of selectedImportIds.value) {
       await copyCard(id, { target_project_id: pid, parent_id: targetParent as any })
     }
     await cardStore.fetchCards(pid)
     ElMessage.success('已導入所選卡片')
     importDialog.value.visible = false
   } catch { ElMessage.error('導入失敗') }
 }

 // Props
 const props = defineProps<{
   initialProject: Project
 }>()

 // Store
 const cardStore = useCardStore()
 const { cardTree, activeCard, cards } = storeToRefs(cardStore)
 const editorStore = useEditorStore()
 const { expandedKeys } = storeToRefs(editorStore)
 const projectStore = useProjectStore()
 const assistantStore = useAssistantStore()
 const isFreeProject = computed(() => (projectStore.currentProject?.name || '') === '__free__')

  // --- 前端自動分組器 ---
 // 當某節點的直接子卡片中，任一“類型的數量 > 2”時，爲該類型創建一個虛擬分組節點；
 // 其餘數量 <= 2 的類型保持原樣顯示（即使整個父節點下只有一種類型，只要該類型數量>2也要分組）。
 // 該結構完全在前端進行，不影響後端數據
 interface TreeNode { id: number | string; title: string; children?: TreeNode[]; card_type?: { name: string }; __isGroup?: boolean; __groupType?: string }


 function buildGroupedNodes(nodes: any[]): any[] {
  return nodes.map(n => {
    const node: TreeNode = { ...n }
    // 分組節點自身不再參與分組邏輯，直接遞歸其子節點
    if ((n as any).__isGroup) {
      if (Array.isArray(n.children) && n.children.length > 0) {
        node.children = buildGroupedNodes(n.children as any)
      }
      return node
    }
    if (Array.isArray(n.children) && n.children.length > 0) {
      // 統計子節點類型數量
      const byType: Record<string, any[]> = {}
      n.children.forEach((c: any) => {
        const typeName = c.card_type?.name || '未知類型'
        if (!byType[typeName]) byType[typeName] = []
        byType[typeName].push(c)
      })
      const types = Object.keys(byType)
        const grouped: any[] = []
        types.forEach(t => {
          const list = byType[t]
        if (list.length > 2) {
            // 創建虛擬分組節點（id 使用字符串避免衝突）
            grouped.push({
              id: `group:${n.id}:${t}`,
              title: `${t}`,
              __isGroup: true,
              __groupType: t,
              __parentCardId: n.id,  // 保存實際父卡片ID
              children: list.map(x => ({ ...x }))
            })
          } else {
          // 數量爲 1 或 2，直接平鋪
          grouped.push(...list)
          }
        })
      // 遞歸對子樹繼續處理（分組節點與普通節點都遞歸其 children）
      node.children = grouped.map((x: any) => {
        const copy = { ...x }
        if (Array.isArray(copy.children) && copy.children.length > 0) {
          copy.children = buildGroupedNodes(copy.children as any)
        }
        return copy
      })
    }
    return node
  })
}

// 基於原始 cardTree 計算帶分組的樹
const groupedTree = computed(() => buildGroupedNodes(cardTree.value as unknown as any[]))

// Local State
const activeTab = ref('market')
const relationGraphRefreshSeq = ref(0)
const activeRightTab = ref('assistant')
const isCreateCardDialogVisible = ref(false)
const exportDialogVisible = ref(false)
const prefetchedContext = ref<any>(null)
const newCardForm = reactive<Partial<CardCreate>>({
  title: '',
  card_type_id: undefined,
  parent_id: '' as any
})

// 卡片多選狀態
const selectedCardIds = ref<number[]>([])
const lastSelectedCardId = ref<number | null>(null)

// 空白區域菜單狀態
const blankMenuVisible = ref(false)
const blankMenuX = ref(0)
const blankMenuY = ref(0)
const blankMenuRef = ref<HTMLElement | null>(null)

// Search State
const searchQuery = ref('')
const searchResults = ref<CardRead[]>([])
const isSearching = computed(() => searchQuery.value.trim().length > 0)
const searchLoading = ref(false)

const handleSearch = debounce(async (query: string) => {
  if (!query.trim()) {
    searchResults.value = []
    return
  }
  searchLoading.value = true
  try {
    const pid = projectStore.currentProject?.id
    if (pid) {
      searchResults.value = await searchCards(pid, query)
    }
  } catch (e) {
    console.error(e)
  } finally {
    searchLoading.value = false
  }
}, 300)

// Composables
const { leftSidebarWidth, rightSidebarWidth, startResizing } = useSidebarResizer()
const isLeftSidebarVisible = ref(true)
const leftSidebarDisplayWidth = computed(() => (isLeftSidebarVisible.value ? leftSidebarWidth.value : 0))
const leftSidebarToggleOffset = computed(() => (isLeftSidebarVisible.value ? Math.max(leftSidebarDisplayWidth.value - 18, 8) : 10))

function toggleLeftSidebar() {
  isLeftSidebarVisible.value = !isLeftSidebarVisible.value
}
  
 // 統一 TreeSelect 樣式/屬性，確保選項可見
 const treeSelectProps = {
   value: 'id',
   label: 'title',
   children: 'children'
 } as const
 
 // 內部垂直分割：類型/卡片高度
 const typesPaneHeight = ref(180)
 const innerResizerThickness = 6
 // 左側寬度拖拽沿用 useSidebarResizer.startResizing('left')

 function startResizingInner() {
   const startY = (event as MouseEvent).clientY
   const startH = typesPaneHeight.value
   const onMove = (e: MouseEvent) => {
     const dy = e.clientY - startY
     const next = Math.max(120, Math.min(startH + dy, 400))
     typesPaneHeight.value = next
   }
   const onUp = () => {
     window.removeEventListener('mousemove', onMove)
     window.removeEventListener('mouseup', onUp)
   }
   window.addEventListener('mousemove', onMove)
   window.addEventListener('mouseup', onUp)
 }

// 拖拽：從類型到卡片區域創建新實例
function onTypeDragStart(t: any) {
  try { (event as DragEvent).dataTransfer?.setData('application/x-card-type-id', String(t.id)) } catch {}
}
async function onCardsPaneDrop(e: DragEvent) {
 try {
   const typeId = e.dataTransfer?.getData('application/x-card-type-id')
   if (typeId) {
     // 從類型列表拖拽到空白區域，在根創建新卡片
     newCardForm.title = (cardStore.cardTypes.find(ct => ct.id === Number(typeId))?.name || '新卡片')
     newCardForm.card_type_id = Number(typeId)
     newCardForm.parent_id = '' as any
     handleCreateCard()
     return
   }
   // 從 __free__ 項目跨項目拖拽複製到空白區域
   const freeCardId = e.dataTransfer?.getData('application/x-free-card-id')
   if (freeCardId) {
     await copyCard(Number(freeCardId), { target_project_id: projectStore.currentProject!.id, parent_id: null as any })
     await cardStore.fetchCards(projectStore.currentProject!.id)
     ElMessage.success('已複製自由卡片到根目錄')
     return
   }
   // 注意：同項目內的卡片拖拽現在由 el-tree 的原生拖拽處理（handleNodeDrop）
 } catch {}
}

// 從卡片實例提升爲類型：在上半區鬆手
async function onTypesPaneDrop(e: DragEvent) {
 try {
   const cardIdStr = e.dataTransfer?.getData('application/x-card-id')
   const cardId = cardIdStr ? Number(cardIdStr) : NaN
   if (!cardId || Number.isNaN(cardId)) return
   // 讀取該卡片的有效 schema
   const resp = await getCardSchema(cardId)
   const effective = resp?.effective_schema || resp?.json_schema
   if (!effective) { ElMessage.warning('該卡片暫無可用結構，無法生成類型'); return }
   // 默認名稱：卡片標題或“新類型”
   const old = cards.value.find(c => (c as any).id === cardId)
   const defaultName = (old?.title || '新類型') as string
   const { value } = await ElMessageBox.prompt('從該實例創建卡片類型，請輸入類型名稱：', '創建卡片類型', {
     inputValue: defaultName,
     confirmButtonText: '創建',
     cancelButtonText: '取消',
     inputValidator: (v:string) => v.trim().length > 0 || '名稱不能爲空'
   })
   const finalName = String(value).trim()
   await createCardType({ name: finalName, description: `${finalName}的默認卡片類型`, json_schema: effective } as any)
   ElMessage.success('已從實例創建卡片類型')
   await cardStore.fetchCardTypes()
 } catch (err) {
   // 用戶取消或錯誤忽略
 }
}

// ===== el-tree 原生拖拽功能 =====

// 控制哪些節點可以被拖拽
function handleAllowDrag(draggingNode: any): boolean {
  // 分組節點不允許拖拽
  if (draggingNode.data.__isGroup) {
    return false
  }
  return true
}

// 控制拖拽放置的位置
// type: 'prev' | 'inner' | 'next' 表示放置在目標節點的前/內/後
function handleAllowDrop(draggingNode: any, dropNode: any, type: 'prev' | 'inner' | 'next'): boolean {
  // 分組節點只允許作爲"inner"目標（即將卡片放入分組內）
  if (dropNode.data.__isGroup) {
    return type === 'inner'
  }
  
  // 普通卡片節點允許所有放置方式
  return true
}

// 處理拖拽完成
async function handleNodeDrop(
  draggingNode: any,
  dropNode: any,
  dropType: 'before' | 'after' | 'inner',
  ev: DragEvent
) {
  try {
    const draggedCard = draggingNode.data
    const targetCard = dropNode.data
    
    // 如果是拖到分組內，設置 parent_id 爲 null（根級）
    if (targetCard.__isGroup && dropType === 'inner') {
      // 計算根級的下一個 display_order
      const rootCards = cards.value.filter(c => c.parent_id === null)
      const maxOrder = rootCards.length > 0 ? Math.max(...rootCards.map(c => c.display_order || 0)) : -1
      
      await cardStore.modifyCard(draggedCard.id, { 
        parent_id: null,
        display_order: maxOrder + 1
      }, { skipHooks: true })
      ElMessage.success(`已將「${draggedCard.title}」移到根級`)
      await cardStore.fetchCards(projectStore.currentProject!.id)
      
      // 記錄移動操作（包含層級變化信息）
      assistantStore.recordOperation(projectStore.currentProject!.id, {
        type: 'move',
        cardId: draggedCard.id,
        cardTitle: draggedCard.title,
        cardType: draggedCard.card_type?.name || 'Unknown',
        detail: '從子卡片移到根級'
      })
      
      // 更新項目結構
      updateProjectStructureContext(activeCard.value?.id)
      return
    }
    
    // 如果是拖到卡片內部（成爲子卡片）
    if (dropType === 'inner') {
      // 計算目標卡片的子卡片的下一個 display_order
      const children = cards.value.filter(c => c.parent_id === targetCard.id)
      const maxOrder = children.length > 0 ? Math.max(...children.map(c => c.display_order || 0)) : -1
      
      await cardStore.modifyCard(draggedCard.id, { 
        parent_id: targetCard.id,
        display_order: maxOrder + 1
      }, { skipHooks: true })
      ElMessage.success(`已將「${draggedCard.title}」設爲「${targetCard.title}」的子卡片`)
      await cardStore.fetchCards(projectStore.currentProject!.id)
      
      // 記錄移動操作（包含層級變化信息）
      assistantStore.recordOperation(projectStore.currentProject!.id, {
        type: 'move',
        cardId: draggedCard.id,
        cardTitle: draggedCard.title,
        cardType: draggedCard.card_type?.name || 'Unknown',
        detail: `設爲「${targetCard.title}」(${targetCard.card_type?.name || 'Unknown'} #${targetCard.id})的子卡片`
      })
      
      // 更新項目結構
      updateProjectStructureContext(activeCard.value?.id)
      return
    }
    
    // 如果是拖到卡片前/後（同級排序）
    const newParentId = targetCard.parent_id || null
    
    // 獲取同級的所有卡片，按 display_order 排序（不包括拖拽的卡片）
    const siblings = cards.value
      .filter(c => (c.parent_id || null) === newParentId && c.id !== draggedCard.id)
      .sort((a, b) => (a.display_order || 0) - (b.display_order || 0))
    
    // 找到目標卡片在同級中的位置
    const targetIndex = siblings.findIndex(c => c.id === targetCard.id)
    
    // 構建新的順序數組（插入拖拽的卡片）
    let newSiblings = [...siblings]
    if (dropType === 'before') {
      // 插入到目標卡片之前
      newSiblings.splice(targetIndex, 0, draggedCard)
    } else {
      // 插入到目標卡片之後
      newSiblings.splice(targetIndex + 1, 0, draggedCard)
    }
    
    // 批量更新所有受影響卡片的 display_order（使用批量API）
    const updates: Array<{ card_id: number; display_order: number; parent_id?: number | null }> = []
    
    newSiblings.forEach((card, index) => {
      if (card.id === draggedCard.id) {
        // 拖拽的卡片需要同時更新 parent_id 和 display_order
        updates.push({
          card_id: card.id,
          display_order: index,
          parent_id: newParentId
        })
      } else if (card.display_order !== index) {
        // 其他卡片只需要更新 display_order（如果有變化）
        // ⚠️ 重要：必須傳遞 parent_id，否則後端會錯誤地將其設置爲 null！
        updates.push({
          card_id: card.id,
          display_order: index,
          parent_id: card.parent_id || null  // 保持原有的 parent_id
        })
      }
    })
    
    // 調用批量更新API
    if (updates.length > 0) {
      const { batchReorderCards } = await import('@renderer/api/cards')
      await batchReorderCards({ updates })
    }
    
    ElMessage.success(`已調整「${draggedCard.title}」的位置`)
    await cardStore.fetchCards(projectStore.currentProject!.id)
    
    // 記錄移動操作（包含位置和父級信息）
    const targetCardTitle = targetCard?.title || '根目錄'
    const positionText = dropType === 'before' ? '之前' : '之後'
    let moveDetail = `移動到「${targetCardTitle}」${positionText}`
    
    // 如果改變了父級，特別標註
    if (draggedCard.parent_id !== newParentId) {
      // 優化：創建 Map 避免多次 find（僅在父級變化時）
      const cardMap = new Map(cards.value.map(c => [(c as any).id, c.title]))
      const oldParentName = draggedCard.parent_id 
        ? cardMap.get(draggedCard.parent_id) || '未知' 
        : '根目錄'
      const newParentName = newParentId 
        ? cardMap.get(newParentId) || '未知' 
        : '根目錄'
      moveDetail += ` (從「${oldParentName}」移到「${newParentName}」)`
    }
    
    assistantStore.recordOperation(projectStore.currentProject!.id, {
      type: 'move',
      cardId: draggedCard.id,
      cardTitle: draggedCard.title,
      cardType: draggedCard.card_type?.name || 'Unknown',
      detail: moveDetail
    })
    
    // 立即更新項目結構，讓靈感助手感知層級變化
    updateProjectStructureContext(activeCard.value?.id)
    
  } catch (err: any) {
    console.error('拖拽失敗:', err)
    ElMessage.error(err?.message || '拖拽失敗')
    // 刷新以恢復狀態
    await cardStore.fetchCards(projectStore.currentProject!.id)
    // 即使失敗也更新結構
    updateProjectStructureContext(activeCard.value?.id)
  }
}

// --- 拖拽：從外部（類型列表、自由卡片）到卡片樹 ---
// 注意：el-tree 內部的卡片拖拽由 handleNodeDrop 處理，這裏只處理外部拖入

function getDraggedTypeId(e: DragEvent): number | null {
 try {
   const raw = e.dataTransfer?.getData('application/x-card-type-id') || ''
   const n = Number(raw)
   return Number.isFinite(n) && n > 0 ? n : null
 } catch { return null }
}

async function onExternalDropToNode(e: DragEvent, nodeData: any) {
 // 只處理從類型列表或跨項目的拖拽，不處理樹內部的卡片拖拽
 const typeId = getDraggedTypeId(e)
 if (typeId) {
   // 從類型列表拖拽創建新卡片
   if (nodeData?.__isGroup) return
   const newCard = await cardStore.addCard({ title: '新建卡片', card_type_id: typeId, parent_id: nodeData?.id } as any)
   
   //  記錄創建操作
   if (newCard && projectStore.currentProject?.id) {
     const cardType = cardStore.cardTypes.find(ct => ct.id === typeId)
     assistantStore.recordOperation(projectStore.currentProject.id, {
       type: 'create',
       cardId: (newCard as any).id,
       cardTitle: newCard.title,
       cardType: cardType?.name || 'Unknown'
     })
   }
   
   return
 }
 
 try {
   // 處理從 __free__ 跨項目拖拽複製
   const freeCardId = e.dataTransfer?.getData('application/x-free-card-id')
   if (freeCardId) {
     if (nodeData?.__isGroup) return
     await copyCard(Number(freeCardId), { target_project_id: projectStore.currentProject!.id, parent_id: Number(nodeData?.id) })
     await cardStore.fetchCards(projectStore.currentProject!.id)
     ElMessage.success('已複製自由卡片到該節點下')
     return
   }
 } catch (err) {
   console.error('外部拖拽失敗:', err)
 }
}

 // --- Methods ---

// 點擊行爲對"分組節點"不做打開編輯，僅用於展開/摺疊。對實際卡片才觸發編輯。
function handleNodeClick(data: any) {
  if (data.__isGroup) return
  
  // 確保點擊的卡片被選中（用於UI高亮），同時覆蓋 handleCardClick 中的清空操作
  selectedCardIds.value = [data.id]
  lastSelectedCardId.value = data.id

  // 章節正文現在也在中欄編輯器中打開
  cardStore.setActiveCard(data.id)
  assistantSelectionCleared.value = false
  activeTab.value = 'editor'
  try {
    const pid = projectStore.currentProject?.id as number
    const pname = projectStore.currentProject?.name || ''
    const full = (cards.value || []).find((c:any) => c.id === data.id)
    const title = (full?.title || data.title || '') as string
    const content = (full?.content || (data as any).content || {})
    if (pid && data?.id) {
      // 僅追加 auto 引用：store 規則會保留已存在的 manual，不會被 auto 覆蓋
      assistantStore.addAutoRef({
        refType: 'card',
        projectId: pid,
        projectName: pname,
        cardId: data.id,
        cardTitle: title,
        content,
      })
    }
  } catch {}
}

// 卡片點擊處理（支持多選）
function handleCardClick(event: MouseEvent, data: any) {
  // 分組節點不支持多選
  if (data.__isGroup) {
    handleNodeClick(data)
    return
  }
  
  const cardId = data.id
  
  // Ctrl 鍵：跳躍式多選
  if (event.ctrlKey || event.metaKey) {
    const index = selectedCardIds.value.indexOf(cardId)
    if (index > -1) {
      // 取消選中
      selectedCardIds.value.splice(index, 1)
    } else {
      // 添加選中
      selectedCardIds.value.push(cardId)
    }
    lastSelectedCardId.value = cardId
    event.stopPropagation()
    return
  }
  
  // Shift 鍵：連續多選
  if (event.shiftKey && lastSelectedCardId.value !== null) {
    // 獲取所有可見的卡片ID（扁平化樹結構）
    const flatCards: number[] = []
    function flattenTree(nodes: any[]) {
      for (const node of nodes) {
        if (!node.__isGroup && node.id) {
          flatCards.push(node.id)
        }
        if (node.children && node.children.length > 0) {
          flattenTree(node.children)
        }
      }
    }
    flattenTree(groupedTree.value)
    
    // 找到起始和結束位置
    const startIndex = flatCards.indexOf(lastSelectedCardId.value)
    const endIndex = flatCards.indexOf(cardId)
    
    if (startIndex !== -1 && endIndex !== -1) {
      const minIndex = Math.min(startIndex, endIndex)
      const maxIndex = Math.max(startIndex, endIndex)
      
      // 選中範圍內的所有卡片
      selectedCardIds.value = flatCards.slice(minIndex, maxIndex + 1)
    }
    
    event.stopPropagation()
    return
  }
  
  // 普通點擊：交由 handleNodeClick 處理選中和激活
  handleNodeClick(data)
}

// 判斷卡片是否被選中
function isCardSelected(cardId: number): boolean {
  return selectedCardIds.value.includes(cardId)
}

// 批量刪除卡片
async function batchDeleteCards() {
  if (selectedCardIds.value.length === 0) {
    ElMessage.warning('請先選擇要刪除的卡片')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `確認刪除選中的 ${selectedCardIds.value.length} 個卡片？此操作不可恢復`,
      '批量刪除確認',
      { type: 'warning' }
    )
    
    // 記錄刪除的卡片信息
    const deletedCards = selectedCardIds.value.map(id => {
      const card = cards.value.find(c => (c as any).id === id)
      return {
        id,
        title: card?.title || '未知',
        cardType: (card as any)?.card_type?.name || 'Unknown'
      }
    })
    
    // 如果當前激活的卡片在刪除列表中，先清空激活狀態
    if (activeCard.value && selectedCardIds.value.includes((activeCard.value as any).id)) {
      cardStore.setActiveCard(null as any)
    }
    
    // 優化：過濾掉會被級聯刪除的子卡片
    // 只刪除頂層卡片（即不是其他選中卡片的子孫的卡片）
    const selectedSet = new Set(selectedCardIds.value)
    const cardsToDelete: number[] = []
    
    // 檢查一個卡片是否是另一個選中卡片的子孫
    function isDescendantOfSelected(cardId: number): boolean {
      const card = cards.value.find(c => (c as any).id === cardId)
      if (!card) return false
      
      let parentId = (card as any).parent_id
      while (parentId) {
        if (selectedSet.has(parentId)) {
          return true  // 是某個選中卡片的子孫
        }
        const parent = cards.value.find(c => (c as any).id === parentId)
        if (!parent) break
        parentId = (parent as any).parent_id
      }
      return false
    }
    
    // 只保留頂層卡片（不是其他選中卡片的子孫）
    for (const cardId of selectedCardIds.value) {
      if (!isDescendantOfSelected(cardId)) {
        cardsToDelete.push(cardId)
      }
    }
    
    // 批量刪除（只刪除頂層卡片，子卡片會被後端級聯刪除）
    let successCount = 0
    for (const cardId of cardsToDelete) {
      try {
        await cardStore.removeCard(cardId)
        successCount++
      } catch (error: any) {
        console.error(`刪除卡片 ${cardId} 失敗:`, error)
        ElMessage.error(`刪除卡片失敗: ${error.message || '未知錯誤'}`)
      }
    }
    
    // 記錄刪除操作（記錄所有選中的卡片，包括被級聯刪除的）
    if (projectStore.currentProject?.id) {
      for (const card of deletedCards) {
        assistantStore.recordOperation(projectStore.currentProject.id, {
          type: 'delete',
          cardId: card.id,
          cardTitle: card.title,
          cardType: card.cardType
        })
      }
    }
    
    // 清空選中狀態
    selectedCardIds.value = []
    lastSelectedCardId.value = null
    
    ElMessage.success(`已刪除 ${selectedCardIds.value.length || deletedCards.length} 個卡片`)
  } catch (e) {
    // 用戶取消
  }
}

// 兜底：當 activeCard 改變時也自動注入一次
watch(activeCard, (c) => {
 try {
   if (!c) return
   const pid = projectStore.currentProject?.id as number
   const pname = projectStore.currentProject?.name || ''
  assistantStore.addAutoRef({
    refType: 'card',
    projectId: pid,
    projectName: pname,
    cardId: (c as any).id,
    cardTitle: (c as any).title || '',
    content: (c as any).content || {},
  })
   
   //  更新卡片上下文（用於靈感助手工具調用）
   assistantStore.updateActiveCard(c as any, pid)
   
   //  更新項目結構（當前卡片變化時）
   updateProjectStructureContext((c as any)?.id)
 } catch (err) {
   console.error('🔄 [Editor] 更新卡片上下文失敗:', err)
 }
})

//  監聽項目切換，初始化結構和操作歷史
watch(() => projectStore.currentProject, (newProject) => {
  if (!newProject?.id) return
  
  // 切換項目時重置搜索
  searchQuery.value = ''
  searchResults.value = []

  try {
    // 加載操作歷史
    assistantStore.loadOperations(newProject.id)
    
    // 更新卡片類型列表
    assistantStore.updateProjectCardTypes(cardStore.cardTypes.map(ct => ct.name))
    
    // 構建項目結構
    updateProjectStructureContext(activeCard.value?.id)
  } catch (err) {
    console.error('📦 [Editor] 初始化助手上下文失敗:', err)
  }
}, { immediate: true })

//  監聽卡片數量變化（新增/刪除），自動更新項目結構
// 優化：只監聽數量變化，層級變化由拖拽操作手動觸發
watch(() => cards.value.length, () => {
  try {
    updateProjectStructureContext(activeCard.value?.id)
  } catch (err) {
    console.error('🔄 [Editor] 更新項目結構失敗:', err)
  }
})

//  統一更新項目結構的函數
function updateProjectStructureContext(currentCardId?: number) {
  const project = projectStore.currentProject
  if (!project?.id) return
  
  assistantStore.updateProjectStructure(
    project.id,
    project.name,
    cards.value,
    cardStore.cardTypes,
    currentCardId
  )
}

function onNodeExpand(_: any, node: any) {
  editorStore.addExpandedKey(String(node.key))
}

function onNodeCollapse(_: any, node: any) {
  // 遞歸移除該節點及其所有子節點的展開狀態
  // 這樣可以防止刷新數據時，一下子節點觸發父節點自動展開
  const removeRecursively = (n: any) => {
    if (n.key) {
      editorStore.removeExpandedKey(String(n.key))
    }
    if (n.childNodes && n.childNodes.length > 0) {
      n.childNodes.forEach((child: any) => removeRecursively(child))
    }
  }
  removeRecursively(node)
}

function handleEditCard(cardId: number) {
  cardStore.setActiveCard(cardId);
  activeTab.value = 'editor';
}

async function handleCreateCard() {
  if (!newCardForm.title || !newCardForm.card_type_id) {
    ElMessage.warning('請填寫卡片標題和類型');
    return;
  }
  const payload: any = {
    ...newCardForm,
    parent_id: (newCardForm as any).parent_id === '' ? undefined : (newCardForm as any).parent_id
  }
  const newCard = await cardStore.addCard(payload as CardCreate);
  
  //  記錄創建操作
  if (newCard && projectStore.currentProject?.id) {
    const cardType = cardStore.cardTypes.find(ct => ct.id === newCardForm.card_type_id)
    assistantStore.recordOperation(projectStore.currentProject.id, {
      type: 'create',
      cardId: (newCard as any).id,
      cardTitle: newCard.title,
      cardType: cardType?.name || 'Unknown'
    })
  }
  
  isCreateCardDialogVisible.value = false;
  // Reset form
  Object.assign(newCardForm, { title: '', card_type_id: undefined, parent_id: '' as any });
}

// 根據卡片類型返回圖標組件
function getIconByCardType(typeName?: string) {
  // 約定：若後端默認類型名稱變更，可在此映射中調整
  switch (typeName) {
    case '作品標籤':
      return CollectionTag
    case '金手指':
      return MagicStick
    case '一句話梗概':
      return ChatLineRound
    case '故事大綱':
      return List
    case '世界觀設定':
      return Connection
    case '核心藍圖':
      return Tickets
    case '分卷大綱':
      return Notebook
    case '章節大綱':
      return Document
    case '角色卡':
      return User
    case '場景卡':
      return OfficeBuilding
    case '組織卡':
      return Connection
    case '物品卡':
      return Box
    case '概念卡':
      return CollectionTag
    case '文件夾':
      return Folder
    default:
      return Document // 通用默認圖標
  }
}

// 右鍵菜單命令處理（新建子卡片、刪除卡片）
function handleContextCommand(command: string, data: any) {
  if (command === 'create-child') {
    openCreateChild(data.id)
  } else if (command === 'create-child-in-group') {
    // 分組節點：使用實際父卡片ID，並預設卡片類型
    openCreateChildInGroup(data.__parentCardId, data.__groupType)
  } else if (command === 'delete') {
    deleteNode(data.id, data.title)
  } else if (command === 'batch-delete') {
    batchDeleteCards()
  } else if (command === 'delete-group') {
    deleteGroupNodes(data)
  } else if (command === 'edit-structure') {
     if (!data?.id || data.__isGroup) return
     openCardSchemaStudio(data)
  } else if (command === 'rename') {
    if (!data?.id || data.__isGroup) return
    renameCard(data.id, data.title || '')
  } else if (command === 'add-as-reference') {
    try {
      if (!data?.id || data.__isGroup) return
      const pid = projectStore.currentProject?.id as number
      const pname = projectStore.currentProject?.name || ''
      const full = (cards.value || []).find((c:any) => c.id === data.id)
      const title = (full?.title || data.title || '') as string
      const content = (full?.content || (data as any).content || {})
      assistantStore.addInjectedRefDirect({
        refType: 'card',
        projectId: pid,
        projectName: pname,
        cardId: data.id,
        cardTitle: title,
        content,
      }, 'manual')
      ElMessage.success('已添加爲引用')
    } catch {}
  }
}

function openCardSchemaStudio(card: any) {
  schemaStudio.value = { visible: true, cardId: card.id, cardTitle: card.title || '' }
}

const schemaStudio = ref<{ visible: boolean; cardId: number; cardTitle: string }>({ visible: false, cardId: 0, cardTitle: '' })

async function onCardSchemaSaved() {
  try {
    await cardStore.fetchCards(projectStore.currentProject?.id as number)
  } catch {}
}

function openCreateCardDialog(options?: { title?: string; cardTypeName?: string; parentId?: number | null }) {
  newCardForm.title = options?.title || ''
  newCardForm.parent_id = options?.parentId == null ? '' as any : options.parentId as any
  if (options?.cardTypeName) {
    const cardType = cardStore.cardTypes.find(ct => ct.name === options.cardTypeName)
    newCardForm.card_type_id = cardType?.id
  } else {
    newCardForm.card_type_id = undefined
  }
  activeTab.value = 'editor'
  isCreateCardDialogVisible.value = true
  blankMenuVisible.value = false
}

// 打開"新建卡片"對話框並預填父ID
function openCreateChild(parentId: number) {
  openCreateCardDialog({ parentId })
}

// 打開"新建卡片"對話框（分組節點專用）：預填父ID和卡片類型
function openCreateChildInGroup(parentId: number, groupType: string) {
  openCreateCardDialog({ parentId, cardTypeName: groupType })
}

function openCreateRoot() {
  openCreateCardDialog()
}

function onOpenCreateCardEvent(e: Event) {
  const detail = (e as CustomEvent)?.detail || {}
  openCreateCardDialog({
    title: typeof detail.title === 'string' ? detail.title : '',
    cardTypeName: typeof detail.cardTypeName === 'string' ? detail.cardTypeName : '',
    parentId: Number.isFinite(Number(detail.parentId)) ? Number(detail.parentId) : null,
  })
}

// 空白處右鍵：僅當未命中節點時顯示菜單
function onSidebarContextMenu(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('.custom-tree-node')) return
  blankMenuX.value = e.clientX
  blankMenuY.value = e.clientY
  blankMenuVisible.value = true
}

// 刪除卡片（確認）
async function deleteNode(cardId: number, title: string) {
  try {
    await ElMessageBox.confirm(`確認刪除卡片「${title}」？此操作不可恢復`, '刪除確認', { type: 'warning' })
    
    //  刪除前記錄卡片信息
    const card = cards.value.find(c => (c as any).id === cardId)
    const cardType = card ? ((card as any).card_type?.name || 'Unknown') : 'Unknown'
    
    // 如果刪除的是當前激活的卡片，先清空激活狀態
    if (activeCard.value && (activeCard.value as any).id === cardId) {
      cardStore.setActiveCard(null as any)
    }
    
    try {
      await cardStore.removeCard(cardId)
      ElMessage.success('卡片已刪除')
      
      //  記錄刪除操作
      if (projectStore.currentProject?.id) {
        assistantStore.recordOperation(projectStore.currentProject.id, {
          type: 'delete',
          cardId,
          cardTitle: title,
          cardType
        })
      }
    } catch (error: any) {
      console.error('刪除卡片失敗:', error)
      ElMessage.error('刪除卡片失敗')
    }
  } catch (e) {
    // 用戶取消
  }
}

async function deleteGroupNodes(groupData: any) {
  try {
    const title = groupData?.title || groupData?.__groupType || '該分組'
    await ElMessageBox.confirm(`確認刪除${title}下的所有卡片？此操作不可恢復`, '刪除確認', { type: 'warning' })
    const directChildren: any[] = Array.isArray(groupData?.children) ? groupData.children : []
    const toDeleteOrdered: number[] = []

    // 遞歸收集：葉子優先（先刪子孫，再刪父）
    function collectDescendantIds(parentId: number) {
      const childIds = (cards.value || []).filter((c: any) => c.parent_id === parentId).map((c: any) => c.id)
      for (const cid of childIds) collectDescendantIds(cid)
      toDeleteOrdered.push(parentId)
    }

    for (const child of directChildren) {
      collectDescendantIds(child.id)
    }

    // 去重（理論上無交叉）
    const seen = new Set<number>()
    for (const id of toDeleteOrdered) {
      if (seen.has(id)) continue
      seen.add(id)
      await cardStore.removeCard(id)
    }
  } catch (e) {
    // 用戶取消
  }
}

// 重命名功能
async function renameCard(cardId: number, oldTitle: string) {
  try {
    const { value } = await ElMessageBox.prompt('重命名會立即生效，請輸入新名稱：', '重命名', {
      confirmButtonText: '確定',
      cancelButtonText: '取消',
      inputValue: oldTitle,
      inputPlaceholder: '請輸入卡片標題',
      inputValidator: (v:string) => v.trim().length > 0 || '標題不能爲空'
    })
    const newTitle = String(value).trim()
    if (newTitle === oldTitle) return
    // 默認僅更新外殼 card.title
    const card = (cards.value || []).find((c: any) => c.id === cardId) as any
    const payload: any = { title: newTitle }

    // 僅對章節大綱 / 章節正文做「標題字段與卡片名」的綁定優化
    const typeName = card?.card_type?.name || ''
    if ((typeName === '章節大綱' || typeName === '章節正文') && card?.content) {
      const content: any = { ...(card.content as any) }
      content.title = newTitle
      payload.content = content
    }
    await cardStore.modifyCard(cardId, payload)
    ElMessage.success('已重命名')
  } catch {
    // 用戶取消或失敗
  }
}

// 助手面板上下文
const assistantResolvedContext = ref<string>('')
const assistantEffectiveSchema = ref<any>(null)
const assistantSelectionCleared = ref<boolean>(false)
const assistantParams = ref<{ llm_config_id: number | null; prompt_name: string | null; temperature: number | null; max_tokens: number | null; timeout: number | null }>({ llm_config_id: null, prompt_name: '靈感對話', temperature: null, max_tokens: null, timeout: null })

// 判斷當前是否爲章節正文卡片
const isChapterContent = computed(() => {
  return activeCard.value?.card_type?.name === '章節正文'
})

const showRightSidebarTabs = computed(() => {
  return Boolean(activeCard.value)
})

const reviewTargetCardIdForSidebar = computed<number | null>(() => {
  const card = activeCard.value as any
  if (!card) return null
  if (card?.card_type?.name === '內容審核卡片') {
    const target = Number(card?.content?.review_target_card_id || 0)
    return Number.isFinite(target) && target > 0 ? target : null
  }
  return Number(card.id || 0) || null
})

const rightSidebarTabNames = computed(() => {
  if (!showRightSidebarTabs.value) return [] as string[]
  if (isChapterContent.value) return ['assistant', 'context', 'extract', 'outline', 'review-history']
  return ['assistant', 'review-history']
})

// 章節信息提取
const chapterVolumeNumber = computed(() => {
  if (!isChapterContent.value) return null
  const content: any = activeCard.value?.content || {}
  return content.volume_number ?? null
})

const chapterChapterNumber = computed(() => {
  if (!isChapterContent.value) return null
  const content: any = activeCard.value?.content || {}
  return content.chapter_number ?? null
})

const chapterParticipants = computed(() => {
  if (!isChapterContent.value) return []
  const content: any = activeCard.value?.content || {}
  const list = content.entity_list || []
  if (Array.isArray(list)) {
    return list.map((x: any) => typeof x === 'string' ? x : (x?.name || '')).filter(Boolean).slice(0, 6)
  }
  return []
})

// 自動裝配章節上下文（首次進入章節正文時）
watch(isChapterContent, async (val) => {
  if (val && activeCard.value) {
    await assembleChapterContext()
  }
}, { immediate: true })

watch(rightSidebarTabNames, (tabNames) => {
  if (!tabNames.includes(activeRightTab.value)) {
    activeRightTab.value = 'assistant'
  }
}, { immediate: true })

// 當卡片倉庫內容發生變化時，若當前仍在章節正文卡片上，則重新裝配上下文
watch(cards, async () => {
  if (isChapterContent.value && activeCard.value) {
    await assembleChapterContext()
  }
})

async function assembleChapterContext() {
  if (!isChapterContent.value || !projectStore.currentProject?.id) return
  
  try {
    const { assembleContext } = await import('@renderer/api/ai')
    const res = await assembleContext({
      project_id: projectStore.currentProject.id,
      volume_number: chapterVolumeNumber.value ?? undefined,
      chapter_number: chapterChapterNumber.value ?? undefined,
      participants: chapterParticipants.value,
      current_draft_tail: ''
    })
    prefetchedContext.value = res
  } catch (e) {
    console.error('Failed to assemble chapter context:', e)
  }
}

// 當右側“參與實體”面板中手動增刪參與者時，將變更寫回當前章節卡片的內容
async function handleContextParticipantsUpdate(names: string[]) {
  try {
    if (!isChapterContent.value || !activeCard.value) return
    const card = activeCard.value as any
    const content: any = { ...(card.content || {}) }
    // 僅以名稱列表作爲實體列表的來源（對象形態後續仍可由分析流程補全）
    const normalized = (names || [])
      .map(n => (typeof n === 'string' ? n.trim() : String(n || '')).trim())
      .filter(Boolean)
    content.entity_list = normalized
    await cardStore.modifyCard(card.id, { content } as any)
    // modifyCard 成功後，cards watcher 會觸發 assembleChapterContext 使用新的參與者
  } catch (e) {
    console.error('Failed to update participants on card:', e)
  }
}

function handleContextAssembledUpdate(ctx: any) {
  prefetchedContext.value = ctx || null
}


async function refreshAssistantContext() {
  try {
    const card = assistantSelectionCleared.value ? null : (activeCard.value as any)
    if (!card) { assistantResolvedContext.value = ''; assistantEffectiveSchema.value = null; return }
    // 計算上下文（沿用 contextResolver）
    const { resolveTemplate } = await import('@renderer/services/contextResolver')
    // 使用卡片當前保存的 ai_context_template 和 content
    const resolved = resolveTemplate({
      template: card.ai_context_template || '',
      cards: cards.value,
      currentCard: card,
      assembledContext: prefetchedContext.value,
    })
    assistantResolvedContext.value = resolved
    // 讀取有效 Schema
    const resp = await getCardSchema(card.id)
    assistantEffectiveSchema.value = resp?.effective_schema || resp?.json_schema || null
    // 讀取有效 AI 參數（保障 llm_config_id 存在）
    try {
      const ai = await getCardAIParams(card.id)
      const eff = (ai?.effective_params || {}) as any
      assistantParams.value = {
        llm_config_id: eff.llm_config_id ?? null,
        prompt_name: (eff.prompt_name ?? '靈感對話') as any,
        temperature: eff.temperature ?? null,
        max_tokens: eff.max_tokens ?? null,
        timeout: eff.timeout ?? null,
      }
    } catch {
      // 回退：直接使用卡片上的 ai_params
      const p = (card?.ai_params || {}) as any
      assistantParams.value = {
        llm_config_id: p.llm_config_id ?? null,
        prompt_name: (p.prompt_name ?? '靈感對話') as any,
        temperature: p.temperature ?? null,
        max_tokens: p.max_tokens ?? null,
        timeout: p.timeout ?? null,
      }
    }
  } catch { assistantResolvedContext.value = '' }
}

watch(activeCard, () => { if (!assistantSelectionCleared.value) refreshAssistantContext() })
watch(prefetchedContext, () => { if (!assistantSelectionCleared.value) refreshAssistantContext() })

watch(activeTab, (tab) => {
  if (tab === 'relation-graph') {
    relationGraphRefreshSeq.value += 1
  }
})

function resetAssistantSelection() {
  assistantSelectionCleared.value = true
  assistantResolvedContext.value = ''
  assistantEffectiveSchema.value = null
}

const assistantFinalize = async (summary: string) => {
  try {
    const card = activeCard.value as any
    if (!card) return
    const evt = new CustomEvent('nf:assistant-finalize', { detail: { cardId: card.id, summary } })
    window.dispatchEvent(evt)
    ElMessage.success('已發送定稿要點到編輯器頁')
  } catch {}
}

function onAssistantAddRef(e: CustomEvent) {
  try {
    const payload = (e as any)?.detail || {}
    const ref = (payload.ref || payload) as AssistantRef
    assistantStore.addInjectedRefDirect(ref, (ref as any)?.source || 'manual')
    activeRightTab.value = 'assistant'
  } catch {}
}

function onAssistantAddExcerptRef(e: CustomEvent) {
  try {
    const payload = (e as any)?.detail || {}
    const ref = (payload.ref || payload) as ChapterExcerptRef
    assistantStore.addChapterExcerptRef(ref, (ref as any)?.source || 'manual')
    activeRightTab.value = 'assistant'
  } catch {}
}

function onAssistantAddReviewRef(e: CustomEvent) {
  try {
    const payload = (e as any)?.detail || {}
    const ref = (payload.ref || payload) as ReviewResultRef
    assistantStore.addReviewResultRef(ref, (ref as any)?.source || 'manual')
    activeRightTab.value = 'assistant'
  } catch {}
}

async function onAssistantFinalize(e: CustomEvent) {
  try {
    const card = activeCard.value as any
    if (!card) return
    const summary: string = (e as any)?.detail?.summary || ''
    const llmId = assistantParams.value.llm_config_id
    const promptName = (assistantParams.value.prompt_name || '內容生成') as string
    const schema = assistantEffectiveSchema.value
    if (!llmId) { ElMessage.warning('請先爲該卡片選擇模型'); return }
    if (!schema) { ElMessage.warning('未獲取到有效 Schema，無法定稿'); return }
    // 組裝定稿輸入：上下文 + 定稿要點
    const ctx = (assistantResolvedContext.value || '').trim()
    const inputText = [ctx ? `【上下文】\n${ctx}` : '', summary ? `【定稿要點】\n${summary}` : ''].filter(Boolean).join('\n\n')
    const result = await generateAIContent({
      input: { input_text: inputText },
      llm_config_id: llmId as any,
      prompt_name: promptName,
      response_model_schema: schema as any,
      temperature: assistantParams.value.temperature ?? undefined,
      max_tokens: assistantParams.value.max_tokens ?? undefined,
      timeout: assistantParams.value.timeout ?? undefined,
    } as any)
    if (result) {
      await cardStore.modifyCard(card.id, { content: result as any })
      ElMessage.success('已根據要點生成並寫回該卡片')
    } else {
      ElMessage.error('定稿生成失敗：無返回內容')
    }
  } catch (err) {
    ElMessage.error('定稿生成失敗')
    console.error(err)
  }
}

// 助手 chips 跳轉卡片
async function handleJumpToCard(payload: { projectId: number; cardId: number }) {
  try {
    const curPid = projectStore.currentProject?.id
    if (curPid !== payload.projectId) {
      // 切換項目：從全部項目列表中找到目標項目並設置
      const all = await getProjects()
      const target = (all || []).find(p => p.id === payload.projectId)
      if (target) {
        projectStore.setCurrentProject(target as any)
        await cardStore.fetchCards(target.id!)
      }
    }
    // 激活目標卡（僅導航，不改動 injectedRefs）
    cardStore.setActiveCard(payload.cardId)
    activeTab.value = 'editor'
  } catch {}
}

function onJumpToCardEvent(e: CustomEvent) {
  const detail = (e as any)?.detail || {}
  const cardId = Number(detail.cardId || 0)
  if (!cardId) return
  void handleJumpToCard({
    projectId: Number(detail.projectId || projectStore.currentProject?.id || 0),
    cardId,
  })
}

// --- Lifecycle ---

onMounted(async () => {
  // Fetch initial data for the card system (like types and models)
  // Cards will be fetched automatically by the watcher in the card store
  await cardStore.fetchInitialData()
  // 進入編輯頁時也刷新一次可用模型（處理應用在其他頁新增模型的場景）
  await cardStore.fetchAvailableModels()
  
  // 更新項目卡片類型列表（用於靈感助手工具調用）
  try {
    const types = cardStore.cardTypes.map(t => t.name)
    assistantStore.updateProjectCardTypes(types)
  } catch {}
  
  window.addEventListener('nf:navigate', onNavigate as any)
  window.addEventListener('nf:assistant-finalize', onAssistantFinalize as any)
  window.addEventListener('nf:switch-main-tab', onSwitchMainTab as any)
  window.addEventListener('nf:switch-right-tab', onSwitchRightTab as any)
  window.addEventListener('nf:assistant-add-ref', onAssistantAddRef as any)
  window.addEventListener('nf:assistant-add-excerpt-ref', onAssistantAddExcerptRef as any)
  window.addEventListener('nf:assistant-add-review-ref', onAssistantAddReviewRef as any)
  window.addEventListener('nf:jump-to-card', onJumpToCardEvent as any)
  window.addEventListener('nf:open-create-card', onOpenCreateCardEvent as any)
  await refreshAssistantContext()
})

 onBeforeUnmount(() => {
   window.removeEventListener('nf:navigate', onNavigate as any)
   window.removeEventListener('nf:assistant-finalize', onAssistantFinalize as any)
   window.removeEventListener('nf:switch-main-tab', onSwitchMainTab as any)
   window.removeEventListener('nf:switch-right-tab', onSwitchRightTab as any)
   window.removeEventListener('nf:assistant-add-ref', onAssistantAddRef as any)
   window.removeEventListener('nf:assistant-add-excerpt-ref', onAssistantAddExcerptRef as any)
   window.removeEventListener('nf:assistant-add-review-ref', onAssistantAddReviewRef as any)
   window.removeEventListener('nf:jump-to-card', onJumpToCardEvent as any)
   window.removeEventListener('nf:open-create-card', onOpenCreateCardEvent as any)
  })

 function onNavigate(e: CustomEvent) {
   if ((e as any).detail?.to === 'market') {
     activeTab.value = 'market'
   }
 }

function onSwitchMainTab(e: CustomEvent) {
  const tab = (e as any)?.detail?.tab
  if (tab && ['market', 'editor', 'relation-graph'].includes(tab)) {
    activeTab.value = tab
  }
}

function onSwitchRightTab(e: CustomEvent) {
  const tab = (e as any)?.detail?.tab
  if (tab && rightSidebarTabNames.value.includes(tab)) {
    activeRightTab.value = tab
  }
}

 // 點擊頁面任意處隱藏空白菜單
 document.addEventListener('click', () => (blankMenuVisible.value = false))

 const treeRef = ref<any>(null)

 watch(groupedTree, async () => {
   // Wait for the tree to re-render with new data
   await nextTick()
   try { 
     if (expandedKeys.value.length > 0) {
       // Using Element Plus Tree store API to set expanded keys
       // This is more reliable than manipulating nodes directly
       treeRef.value?.store?.setDefaultExpandedKeys(expandedKeys.value)
     }
   } catch (e) {
     console.error('Failed to restore expanded state:', e)
   }
 }, { deep: true })
</script>

<style scoped>
/* 讓右鍵觸發區域充滿整行 */
.full-row-dropdown { display: block; width: 100%; }
.blank-menu-ref { pointer-events: none; }

.editor-layout {
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  background-color: var(--el-fill-color-lighter); /* 適配暗黑模式 */
}

.sidebar {
  display: flex;
  flex-direction: column;
  background-color: var(--el-fill-color-lighter); /* 適配暗黑模式 */
  transition: width 0.2s;
  flex-shrink: 0;
  overflow: hidden;
  border-right: none; /* 移除邊框 */
}

.card-navigation-sidebar {
  padding: 8px;
}

/* 頂部標題區已移除按鈕，這裏直接隱藏以消除空隙 */
.sidebar-header { display: none; }

.sidebar-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.card-tree {
  background-color: transparent;
  flex-grow: 1;
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  font-size: 14px;
  padding-right: 8px;
}
.card-icon {
  color: var(--el-text-color-secondary);
}
.child-count {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.resizer {
  width: 5px;
  background: transparent;
  cursor: col-resize;
  z-index: 10;
  user-select: none;
  position: relative;
  transition: background-color 0.2s;
}
.resizer:hover {
  background: var(--el-color-primary-light-7);
}

.main-content {
  padding: 16px 8px; /* 留出邊距 */
  display: flex;
  flex-direction: column;
  background-color: transparent; /* 透明背景 */
}

.main-tabs {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color); /* 適配暗黑模式 */
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08); /* 輕微陰影 */
  border-radius: 8px; /* 圓角 */
  overflow: hidden; /* 確保內容不溢出圓角 */
  border: none; /* 移除默認邊框 */
}

:deep(.el-tabs__content) {
  flex-grow: 1;
  overflow-y: auto;
}
:deep(.el-tab-pane) {
  height: 100%;
}

.custom-tree-node.full-row { 
  display: flex;
  align-items: center;
  width: 100%;
  padding: 3px 6px;
  border-radius: 4px;
  transition: background-color 0.2s;
}
.custom-tree-node.full-row .label {
  flex: 1;
}
.custom-tree-node.full-row.selected {
  background-color: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
}
.custom-tree-node.full-row.selected .label {
  color: var(--el-color-primary);
  font-weight: 500;
}


.types-pane { display: flex; flex-direction: column; border-bottom: 1px solid var(--el-border-color-light); background: var(--el-fill-color-lighter); padding: 6px; box-shadow: 0 2px 6px -2px var(--el-box-shadow-lighter); border-radius: 6px; }
.pane-title { font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; padding: 2px 4px 6px 4px; }
.types-scroll { flex: 1; background: var(--el-fill-color-lighter); }
.types-list { list-style: none; padding: 0; margin: 0; }
.type-item { padding: 6px 8px; cursor: grab; display: flex; align-items: center; color: var(--el-text-color-primary); font-size: 13px; border-radius: 4px; }
.type-item:hover { background: var(--el-fill-color-light); color: var(--el-color-primary); }
.type-name { flex: 1; }

.inner-resizer { height: 6px; cursor: row-resize; background: var(--el-fill-color-light); border-top: 1px solid var(--el-border-color-light); border-bottom: 1px solid var(--el-border-color-light); transition: height .12s ease, background-color .12s ease, border-color .12s ease; }
.inner-resizer:hover { height: 8px; background: var(--el-fill-color); border-top: 1px solid var(--el-border-color); border-bottom: 1px solid var(--el-border-color); }
/* 下半區：標題置頂並設置滾動容器 */
.cards-pane { position: relative; padding-top: 8px; overflow: auto; overflow-x: hidden; }
.cards-title {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  padding: 8px;
  background: color-mix(in srgb, var(--el-bg-color) 92%, transparent);
  backdrop-filter: blur(14px);
  border: 1px solid color-mix(in srgb, var(--el-border-color-light) 82%, transparent);
  border-radius: 12px;
  margin: 0 2px 8px;
  box-shadow: 0 10px 24px -22px rgba(15, 23, 42, 0.45);
}
.cards-title-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.cards-title-text {
  min-width: 0;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cards-selection-chip {
  flex-shrink: 0;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1;
  color: var(--el-color-danger);
  background: color-mix(in srgb, var(--el-color-danger-light-9) 78%, var(--el-bg-color));
  border: 1px solid color-mix(in srgb, var(--el-color-danger-light-7) 82%, transparent);
}
.cards-title-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}
.toolbar-action {
  width: 100%;
  min-width: 0;
  margin: 0 !important;
  justify-content: center;
}
.toolbar-action-create-full {
  grid-column: 1 / -1;
}
.toolbar-action-create-split {
  grid-column: span 1;
}
.toolbar-action-secondary {
  grid-column: span 1;
}
.toolbar-action-secondary--solo {
  grid-column: 1 / -1;
}
.toolbar-action-danger-split {
  grid-column: span 1;
}
.cards-title-actions :deep(.el-button > span) {
  min-width: 0;
}
.assistant-sidebar { 
  border-left: none; 
  background: transparent; 
  flex-shrink: 0; 
  padding: 16px 8px 16px 0; /* 右側留白 */
}
.right-resizer { cursor: col-resize; width: 5px; background: transparent; }
.right-resizer:hover { background: var(--el-color-primary-light-7); }
.sidebar-edge-toggle {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 30;
  display: grid;
  place-items: center;
  align-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--el-border-color) 84%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--el-bg-color) 94%, rgba(255,255,255,0.65));
  box-shadow:
    0 10px 22px -18px rgba(15, 23, 42, 0.34),
    0 3px 8px -6px rgba(15, 23, 42, 0.18);
  color: var(--el-text-color-regular);
  cursor: pointer;
  transition:
    left 0.2s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    background-color 0.18s ease,
    transform 0.18s ease,
    opacity 0.18s ease;
  backdrop-filter: blur(14px);
  opacity: 0.92;
}
.sidebar-edge-toggle:hover,
.sidebar-edge-toggle:focus-visible {
  transform: translateY(-50%) scale(1.04);
  box-shadow:
    0 14px 28px -20px rgba(37, 99, 235, 0.28),
    0 4px 10px -8px rgba(15, 23, 42, 0.2);
  border-color: color-mix(in srgb, var(--el-color-primary-light-6) 68%, transparent);
  color: var(--el-color-primary);
  outline: none;
  opacity: 1;
}
.sidebar-edge-toggle.is-collapsed {
  background: color-mix(in srgb, var(--el-bg-color) 96%, rgba(255,255,255,0.72));
}
.sidebar-edge-toggle__icon {
  font-size: 15px;
  line-height: 1;
}
.nf-import-dialog :deep(.el-input__wrapper) { font-size: 14px; }
.nf-import-dialog :deep(.el-input__inner) { font-size: 14px; }
.nf-import-dialog :deep(.el-table .cell) { font-size: 14px; color: var(--el-text-color-primary); }
.nf-import-dialog :deep(.el-table__row) { height: 40px; }
.nf-tree-select-popper { min-width: 320px; }
.nf-tree-select-popper { background: var(--el-bg-color-overlay, #fff); color: var(--el-text-color-primary); }
.nf-tree-select-popper :deep(.el-select-dropdown__item) { color: var(--el-text-color-primary); }
.nf-tree-select-popper :deep(.el-tree) { background: transparent; }
.nf-tree-select-popper :deep(.el-tree-node__content) { background: transparent; }
.nf-tree-select-popper :deep(.el-tree-node__label) { font-size: 14px; color: var(--el-text-color-primary); }
.nf-tree-select-popper :deep(.is-current > .el-tree-node__content),
.nf-tree-select-popper :deep(.el-tree-node__content:hover) { background: var(--el-fill-color-light); }

/* 右欄Tab樣式 */
.right-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}
.right-tabs :deep(.el-tabs__header) {
  margin: 0;
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 12px 12px 0 12px;
  background: var(--el-fill-color-lighter);
}
.right-tabs :deep(.el-tabs__nav-wrap) {
  padding: 0;
}
.right-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  font-weight: 500;
  padding: 0 16px;
  height: 36px;
  line-height: 36px;
}
.right-tabs :deep(.el-tabs__item.is-active) {
  color: var(--el-color-primary);
}
.right-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}
.right-tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow-y: auto;
}

.search-results-list {
  flex-grow: 1;
  overflow-y: auto;
  padding: 0 8px;
}
.search-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  cursor: pointer;
  border-radius: 4px;
  color: var(--el-text-color-primary);
  font-size: 14px;
  transition: background-color 0.2s;
}
.search-item:hover {
  background-color: var(--el-fill-color-light);
}
.search-item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
