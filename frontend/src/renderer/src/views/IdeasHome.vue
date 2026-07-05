<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useCardStore } from '@renderer/stores/useCardStore'
import { getProjects } from '@renderer/api/projects'
import { getCardsForProject, copyCard, moveCard, type CardRead } from '@renderer/api/cards'
import Editor from './Editor.vue'

const projectStore = useProjectStore()
const { currentProject } = storeToRefs(projectStore)

const cardStore = useCardStore()
const { cardTree } = storeToRefs(cardStore)

onMounted(async () => {
  // 若未載入或不是保留項目，則載入保留項目
  if (!currentProject.value || (currentProject.value.name || '') !== '__free__') {
    await projectStore.loadFreeProject()
  }
  await cardStore.fetchInitialData()
  if (projectStore.currentProject?.id) {
    await cardStore.fetchCards(projectStore.currentProject.id)
  }
})

// 新建自由卡對話框
const createDialog = ref(false)
const newTitle = ref('')
const newTypeId = ref<number | null>(null)
const newParentId = ref<number | null>(null)
const treeSelectProps = { value: 'id', label: 'title', children: 'children' } as const

const canCreate = computed(() => !!newTitle.value.trim() && !!newTypeId.value)

async function openCreateDialog() {
  newTitle.value = ''
  newTypeId.value = null
  newParentId.value = null
  createDialog.value = true
}

async function confirmCreate() {
  if (!canCreate.value) return
  await cardStore.addCard({ title: newTitle.value.trim(), card_type_id: Number(newTypeId.value), parent_id: (newParentId.value as any) })
  createDialog.value = false
}

// --- 移動/複製到項目 ---
const transferDialog = ref(false)
const transferOp = ref<'copy' | 'move'>('copy')
const transferSearch = ref('')
const targetProjectId = ref<number | null>(null)
const targetParentId = ref<number | null>(null)
const targetProjectCards = ref<CardRead[]>([])
const projectOptions = ref<Array<{ id: number; name: string }>>([])
const selectedIds = ref<number[]>([])

const filteredFreeCards = computed(() => {
  const q = transferSearch.value.trim().toLowerCase()
  const list = (cardStore.cards as any as CardRead[]) || []
  if (!q) return list
  return list.filter(c => (c.title || '').toLowerCase().includes(q))
})

async function openTransferDialog() {
  selectedIds.value = []
  transferSearch.value = ''
  targetProjectId.value = null
  targetParentId.value = null
  targetProjectCards.value = []
  // 載入項目列表（排除 __free__）
  try {
    const list = await getProjects()
    projectOptions.value = (list || []).filter(p => (p.name || '') !== '__free__').map(p => ({ id: p.id!, name: p.name! }))
  } catch { projectOptions.value = [] }
  transferDialog.value = true
}

async function onTargetProjectChange(pid: number | null) {
  targetParentId.value = null
  targetProjectCards.value = []
  if (!pid) return
  try { targetProjectCards.value = await getCardsForProject(pid) } catch { targetProjectCards.value = [] }
}

async function confirmTransfer() {
  try {
    const ids = [...selectedIds.value]
    const pid = targetProjectId.value
    if (!ids.length || !pid) return
    for (const id of ids) {
      if (transferOp.value === 'copy') {
        await copyCard(id, { target_project_id: pid, parent_id: targetParentId.value as any })
      } else {
        await moveCard(id, { target_project_id: pid, parent_id: targetParentId.value as any })
      }
    }
    // 刷新自由項目卡片
    if (projectStore.currentProject?.id) await cardStore.fetchCards(projectStore.currentProject.id)
    transferDialog.value = false
  } catch {}
}
</script>

<template>
  <div class="ideas-home">
    <div class="topbar" v-if="currentProject">
      <div class="left">
        <el-button size="small" @click="openTransferDialog">移動/複製到專案</el-button>
      </div>
      <div class="right"></div>
    </div>
    <template v-if="currentProject">
      <Editor :initial-project="currentProject" />
    </template>
    <template v-else>
      <el-skeleton animated :rows="6" style="padding: 24px;" />
    </template>

    

    <el-dialog v-model="transferDialog" title="移動/複製到專案" width="760px" class="nf-transfer-dialog">
      <div style="display:flex; gap:12px; align-items:center; margin-bottom:10px;">
        <el-radio-group v-model="transferOp" size="small">
          <el-radio-button label="copy">複製</el-radio-button>
          <el-radio-button label="move">移動</el-radio-button>
        </el-radio-group>
        <el-select v-model="targetProjectId" placeholder="目標專案" style="width: 240px" @change="onTargetProjectChange($event as any)">
          <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-tree-select v-model="targetParentId" :data="targetProjectCards" :props="treeSelectProps" check-strictly clearable :render-after-expand="false" placeholder="目標父級（可選）" style="width: 280px" />
        <el-input v-model="transferSearch" placeholder="搜尋自由卡標題..." clearable style="flex:1" />
      </div>
      <el-table :data="filteredFreeCards" height="360px" border @selection-change="(rows:any[])=>selectedIds = rows.map(r=>r.id)">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="title" label="標題" min-width="220" />
        <el-table-column label="類型" min-width="160">
          <template #default="{ row }">{{ row.card_type?.name }}</template>
        </el-table-column>
        <el-table-column label="創建時間" min-width="180">
          <template #default="{ row }">{{ (row as any).created_at }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="transferDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedIds.length || !targetProjectId" @click="confirmTransfer">確定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ideas-home { height: 100%; display: flex; flex-direction: column; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-light); background: var(--el-bg-color); }
.topbar .left, .topbar .right { display: flex; align-items: center; gap: 8px; }
</style>
<style>
.nf-transfer-dialog .el-table .cell { font-size: 13px; }
</style> 
