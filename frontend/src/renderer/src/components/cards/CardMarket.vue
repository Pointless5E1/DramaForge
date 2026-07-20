<template>
  <div class="card-market">
    <div class="market-toolbar">
      <el-input v-model="keyword" placeholder="搜尋卡片標題..." clearable class="search-input">
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <div v-if="usedCardTypes.length" class="type-filter" aria-label="卡片類型篩選">
        <el-check-tag
          :checked="selectedTypes.length === 0"
          class="type-filter__chip"
          @change="clearTypeFilter"
        >
          全部
        </el-check-tag>
        <el-check-tag
          v-for="type in usedCardTypes"
          :key="type.id"
          :checked="selectedTypes.includes(type.id)"
          class="type-filter__chip"
          @click="selectType(type.id, $event)"
        >
          {{ type.name }}
          <span class="type-filter__count">{{ type.count }}</span>
        </el-check-tag>
      </div>
    </div>

    <div class="table-shell">
      <el-table
        :data="filteredCards"
        height="100%"
        border
        stripe
        :default-sort="{ prop: 'created_at', order: 'descending' }"
        empty-text="未找到符合條件的卡片"
      >
        <el-table-column
          prop="title"
          label="標題"
          min-width="240"
          sortable
          :sort-orders="sortOrders"
        />
        <el-table-column
          prop="card_type.name"
          label="類型"
          min-width="150"
          sortable
          :sort-method="sortByType"
          :sort-orders="sortOrders"
        >
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ visibleCardTypeLabel(row.card_type.name) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          label="建立時間"
          width="200"
          sortable
          :sort-method="sortByCreatedAt"
          :sort-orders="sortOrders"
        >
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="onEditCard(row.id)"
              >編輯</el-button
            >
            <el-popconfirm title="確定刪除?" @confirm="onDeleteCard(row.id)">
              <template #reference>
                <el-button size="small" type="danger" plain>刪除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { Search } from '@element-plus/icons-vue'
import { useCardStore } from '@renderer/stores/useCardStore'
import type { components } from '@renderer/types/generated'
import { isInternalCardFacet, visibleCardTypeLabel } from '@renderer/services/cardVisibility'

type CardRead = components['schemas']['CardRead']

const emit = defineEmits<{ (e: 'edit-card', id: number): void }>()

const cardStore = useCardStore()
const { cards } = storeToRefs(cardStore)

const keyword = ref('')
const selectedTypes = ref<number[]>([])
const sortOrders = ['ascending', 'descending', null] as const

const usedCardTypes = computed(() => {
  const types = new Map<number, { id: number; name: string; count: number }>()
  for (const card of cards.value) {
    if (isInternalCardFacet(card)) continue
    const id = Number(card.card_type_id ?? card.card_type?.id)
    if (!Number.isFinite(id)) continue
    const current = types.get(id)
    if (current) current.count += 1
    else types.set(id, { id, name: visibleCardTypeLabel(card.card_type?.name), count: 1 })
  }
  return [...types.values()].sort((a, b) => a.name.localeCompare(b.name, 'zh-Hant'))
})

const filteredCards = computed(() => {
  let list = cards.value.filter((card) => !isInternalCardFacet(card))
  if (keyword.value.trim()) {
    const keywords = keyword.value.trim().toLowerCase().split(/\s+/)
    list = list.filter((card) => {
      const title = (card.title || '').toLowerCase()
      return keywords.every((term) => title.includes(term))
    })
  }
  if (selectedTypes.value.length) {
    const selected = new Set(selectedTypes.value)
    list = list.filter((card) => selected.has(Number(card.card_type_id ?? card.card_type?.id)))
  }
  return list
})

function clearTypeFilter(): void {
  selectedTypes.value = []
}

function selectType(typeId: number, event: MouseEvent): void {
  if (!event.ctrlKey && !event.metaKey) {
    selectedTypes.value = [typeId]
    return
  }

  selectedTypes.value = selectedTypes.value.includes(typeId)
    ? selectedTypes.value.filter((id) => id !== typeId)
    : [...selectedTypes.value, typeId]
}

function sortByType(a: CardRead, b: CardRead): number {
  return String(a.card_type?.name || '').localeCompare(String(b.card_type?.name || ''), 'zh-Hant')
}

function sortByCreatedAt(a: CardRead, b: CardRead): number {
  return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
}

function onEditCard(id: number): void {
  emit('edit-card', id)
}
async function onDeleteCard(id: number): Promise<void> {
  await cardStore.removeCard(id)
}
function formatDate(dt: string): string {
  return new Date(dt).toLocaleString()
}
</script>

<style scoped>
.card-market {
  height: 100%;
  min-height: 0;
  padding: 16px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-size: 13px;
}
.card-market :deep(.el-input__inner),
.card-market :deep(.el-check-tag),
.card-market :deep(.el-table .cell),
.card-market :deep(.el-tag),
.card-market :deep(.el-button) {
  font-size: 13px;
}
.market-toolbar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}
.search-input {
  width: min(704px, 100%);
}
.search-input :deep(.el-input__wrapper) {
  background: var(--nf-surface-control, var(--el-fill-color));
  box-shadow: none !important;
}
.search-input :deep(.el-input__wrapper:hover) {
  background: var(--nf-surface-raised, var(--el-fill-color-light));
}
.search-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--el-color-primary) 64%, transparent) inset !important;
}
.type-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.type-filter__chip {
  display: inline-flex;
  align-items: center;
  height: 30px;
  box-sizing: border-box;
  border-radius: 999px;
  padding-inline: 13px;
}
.type-filter__count {
  display: inline-block;
  min-width: 18px;
  margin-left: 5px;
  padding: 1px 5px;
  border-radius: 999px;
  background: color-mix(in srgb, currentColor 10%, transparent);
  font-size: 11px;
  text-align: center;
}
.table-shell {
  flex: 1;
  min-height: 0;
}
.table-shell :deep(.el-table) {
  border-radius: 4px;
  --el-table-bg-color: var(--nf-surface-panel, var(--el-bg-color));
  --el-table-tr-bg-color: var(--nf-surface-panel, var(--el-bg-color));
  --el-table-header-bg-color: var(--nf-surface-control, var(--el-fill-color-light));
  --el-table-row-hover-bg-color: var(--nf-surface-raised, var(--el-fill-color));
  --el-table-border-color: var(--nf-divider-subtle, var(--el-border-color-lighter));
}
.table-shell :deep(.el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: var(--nf-surface-section, var(--el-fill-color-lighter));
}
.card-market :deep(.el-input__wrapper),
.card-market :deep(.el-button:not(.is-circle)) {
  border-radius: 6px;
}
.table-shell :deep(.el-table__header th.is-sortable) {
  cursor: pointer;
}
.table-shell :deep(.caret-wrapper) {
  margin-left: 6px;
}
</style>
