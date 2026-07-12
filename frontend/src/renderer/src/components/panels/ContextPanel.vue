<template>
  <div class="ctx-panel">
    <div class="panel-header">
      <h3 class="panel-title">參與實體</h3>
      <el-button size="small" type="primary" :loading="assembling" @click="assemble">查詢實體狀態</el-button>
    </div>
    
    <div class="entity-sections">
      <el-alert
        v-if="localParticipants.length > 10"
        class="entity-count-warning"
        type="warning"
        :closable="false"
        show-icon
        title="參與實體較多"
        :description="`目前共 ${localParticipants.length} 個實體。系統不會自動裁剪；建議確認每個實體都會直接參與或影響本段內容。`"
      />
      <section v-for="g in participantGroups" :key="g.label" class="entity-section">
        <div class="entity-section__head">
          <span class="entity-section__title">{{ g.label }}</span>
          <span class="entity-section__count">{{ participantsForGroup(g.label).length }}</span>
        </div>
        <div class="entity-chip-list">
          <button
            v-for="name in participantsForGroup(g.label)"
            :key="name"
            type="button"
            class="entity-chip"
            :title="`移除 ${name}`"
            @click="removeParticipant(g.label, name)"
          >
            <span>{{ name }}</span>
            <span class="entity-chip__remove" aria-hidden="true">×</span>
          </button>
          <el-select
            v-model="pendingParticipant[g.label]"
            class="entity-add-select"
            filterable
            :allow-create="g.label === '其他'"
            default-first-option
            placeholder="＋"
            :aria-label="`新增${g.label}實體`"
            @change="value => addParticipant(g.label, String(value || ''))"
          >
            <el-option v-for="p in availableForGroup(g)" :key="p" :label="p" :value="p" />
          </el-select>
        </div>
      </section>
    </div>

    <div v-if="assembled" class="assembled">
      <div class="facts-structured" v-if="assembled.facts_structured">
        <div class="facts-title" v-if="Array.isArray((assembled.facts_structured as any)?.fact_summaries) && ((assembled.facts_structured as any)?.fact_summaries?.length > 0)">關鍵事實</div>
        <ul class="list" v-if="Array.isArray((assembled.facts_structured as any)?.fact_summaries) && ((assembled.facts_structured as any)?.fact_summaries?.length > 0)">
          <li v-for="(f, i0) in ((assembled.facts_structured as any)?.fact_summaries as string[] || [])" :key="i0">- {{ f }}</li>
        </ul>

        <div class="facts-title" v-if="Array.isArray((assembled.facts_structured as any)?.relation_summaries) && ((assembled.facts_structured as any)?.relation_summaries?.length > 0)">關係摘要</div>
        <ul class="list" v-if="Array.isArray((assembled.facts_structured as any)?.relation_summaries) && ((assembled.facts_structured as any)?.relation_summaries?.length > 0)">
          <li v-for="(r, idx) in ((assembled.facts_structured as any)?.relation_summaries as any[] || [])" :key="idx" class="relation-item">
            <div class="relation-head">{{ (r as any).a }} ↔ {{ (r as any).b }}（{{ (r as any).kind }}）
              <el-tag v-if="(r as any).stance" size="small" style="margin-left:6px;">{{ (r as any).stance }}</el-tag>
            </div>
            <div v-if="(r as any).description" class="muted" style="margin: 2px 0;">{{ (r as any).description }}</div>
            <div v-if="(r as any).a_to_b_addressing || (r as any).b_to_a_addressing" class="muted addressing">
              <span v-if="(r as any).a_to_b_addressing">A稱B：{{ (r as any).a_to_b_addressing }}</span>
              <span v-if="(r as any).b_to_a_addressing" style="margin-left:12px;">B稱A：{{ (r as any).b_to_a_addressing }}</span>
            </div>
            <div v-if="Array.isArray((r as any)?.recent_dialogues) && ((r as any).recent_dialogues?.length > 0)" class="muted">
              對話樣例：
              <ul class="list">
                <li v-for="(d, i3) in ((r as any).recent_dialogues as string[] || [])" :key="i3"><div class="dialog-text">{{ d }}</div></li>
              </ul>
            </div>
            <div v-if="Array.isArray((r as any)?.recent_event_summaries) && ((r as any).recent_event_summaries?.length > 0)" class="muted">
              近期事件：
              <ul class="list">
                <li v-for="(ev, i4) in ((r as any).recent_event_summaries as any[] || [])" :key="i4">
                  <span>{{ (ev as any).summary }}</span>
                  <span class="badges" v-if="(ev as any).volume_number != null || (ev as any).chapter_number != null">
                    <el-tag size="small" type="info" v-if="(ev as any).volume_number != null">卷{{ (ev as any).volume_number }}</el-tag>
                    <el-tag size="small" type="info" v-if="(ev as any).chapter_number != null" style="margin-left:6px;">章{{ (ev as any).chapter_number }}</el-tag>
                  </span>
                </li>
              </ul>
            </div>
          </li>
        </ul>

        <div class="facts-title" v-if="Array.isArray((assembled.facts_structured as any)?.item_summaries) && ((assembled.facts_structured as any)?.item_summaries?.length > 0)">物品摘要</div>
        <ul class="list" v-if="Array.isArray((assembled.facts_structured as any)?.item_summaries) && ((assembled.facts_structured as any)?.item_summaries?.length > 0)">
          <li v-for="(item, idx) in ((assembled.facts_structured as any)?.item_summaries as any[] || [])" :key="`item-${idx}`" class="relation-item">
            <div class="relation-head">
              {{ (item as any).name }}
              <el-tag v-if="(item as any).category" size="small" style="margin-left:6px;">{{ (item as any).category }}</el-tag>
            </div>
            <div v-if="(item as any).description" class="muted" style="margin: 2px 0;">{{ (item as any).description }}</div>
            <div v-if="(item as any).current_state" class="muted">當前狀態：{{ (item as any).current_state }}</div>
            <div v-if="(item as any).owner_hint" class="muted">歸屬提示：{{ (item as any).owner_hint }}</div>
            <div v-if="(item as any).power_or_effect" class="muted">效果/用途：{{ (item as any).power_or_effect }}</div>
            <div v-if="(item as any).constraints" class="muted">限制條件：{{ (item as any).constraints }}</div>
            <div v-if="Array.isArray((item as any)?.important_events) && ((item as any).important_events?.length > 0)" class="muted">
              重要事件：
              <ul class="list">
                <li v-for="(eventText, eventIdx) in ((item as any).important_events as string[] || [])" :key="eventIdx">{{ eventText }}</li>
              </ul>
            </div>
          </li>
        </ul>

        <div class="facts-title" v-if="Array.isArray((assembled.facts_structured as any)?.concept_summaries) && ((assembled.facts_structured as any)?.concept_summaries?.length > 0)">概念摘要</div>
        <ul class="list" v-if="Array.isArray((assembled.facts_structured as any)?.concept_summaries) && ((assembled.facts_structured as any)?.concept_summaries?.length > 0)">
          <li v-for="(concept, idx) in ((assembled.facts_structured as any)?.concept_summaries as any[] || [])" :key="`concept-${idx}`" class="relation-item">
            <div class="relation-head">
              {{ (concept as any).name }}
              <el-tag v-if="(concept as any).category" size="small" style="margin-left:6px;">{{ (concept as any).category }}</el-tag>
            </div>
            <div v-if="(concept as any).description" class="muted" style="margin: 2px 0;">{{ (concept as any).description }}</div>
            <div v-if="(concept as any).rule_definition" class="muted">規則定義：{{ (concept as any).rule_definition }}</div>
            <div v-if="(concept as any).mastery_hint" class="muted">掌握提示：{{ (concept as any).mastery_hint }}</div>
            <div v-if="(concept as any).cost" class="muted">代價：{{ (concept as any).cost }}</div>
            <div v-if="Array.isArray((concept as any)?.known_by) && ((concept as any).known_by?.length > 0)" class="muted">已知掌握者：{{ ((concept as any).known_by as string[]).join('、') }}</div>
            <div v-if="Array.isArray((concept as any)?.counter_relations) && ((concept as any).counter_relations?.length > 0)" class="muted">剋制/對立：{{ ((concept as any).counter_relations as string[]).join('、') }}</div>
          </li>
        </ul>
        
      </div>
      <pre class="pre" v-if="!assembled.facts_structured && assembled.facts_subgraph">{{ assembled.facts_subgraph }}</pre>
      <div v-if="!assembled.facts_structured && !assembled.facts_subgraph">關鍵事實：暫無（相關實體之間資訊尚未收集）。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { assembleContext, type AssembleContextResponse } from '@renderer/api/ai'
import { ElMessage } from 'element-plus'
import { getCardsForProject, type CardRead } from '@renderer/api/cards'

const props = defineProps<{ projectId?: number; participants?: string[]; volumeNumber?: number | null; stageNumber?: number | null; chapterNumber?: number | null; draftTail?: string; prefetched?: AssembleContextResponse | null }>()
const emit = defineEmits<{
  (e:'update:participants', v: string[]): void;
  (e:'update:volumeNumber', v: number | null): void;
  (e:'update:stageNumber', v: number | null): void;
  (e:'update:chapterNumber', v: number | null): void;
  (e:'context-updated', v: AssembleContextResponse): void;
}>()

const assembling = ref(false)
const assembled = ref<AssembleContextResponse | null>(null)
// 回顯入口已移除

type Group = { label: string; values: string[] }
const participantGroups = ref<Group[]>([])
const localParticipants = ref<string[]>(props.participants || [])
const pendingParticipant = ref<Record<string, string>>({})
const localVolumeNumber = ref<number | null>(props.volumeNumber ?? null)
const localStageNumber = ref<number | null>(props.stageNumber ?? null)
const localChapterNumber = ref<number | null>(props.chapterNumber ?? null)

// 緩存：名稱 -> 分組標籤（通過項目卡片匹配）
const nameToGroup = ref<Record<string, string>>({})

watch(() => props.participants, (v) => { localParticipants.value = [...(v || [])] })
watch(() => props.volumeNumber, (v) => { localVolumeNumber.value = v ?? null })
watch(() => props.stageNumber, (v) => { localStageNumber.value = v ?? null })
watch(() => props.chapterNumber, (v) => { localChapterNumber.value = v ?? null })
watch(() => props.prefetched, (v) => { if (v) assembled.value = v })
watch(() => props.projectId, async () => { await buildNameGroupCache(); await buildAllGroups() })

function emitParticipants() { emit('update:participants', [...localParticipants.value]) }
function emitVolume() { emit('update:volumeNumber', localVolumeNumber.value ?? null) }
function emitStage() { emit('update:stageNumber', localStageNumber.value ?? null) }
function emitChapter() { emit('update:chapterNumber', localChapterNumber.value ?? null) }

function detectTypeGroupByCard(c: CardRead): string {
  // 1) 優先使用內容中的實體類型標記（後端新增）
  const et = (c.content as any)?.entity_type
  if (et === 'character') return '角色'
  if (et === 'scene') return '場景'
  if (et === 'organization') return '組織'
  if (et === 'item') return '物品'
  if (et === 'concept') return '概念'

  // 2) 使用卡片類型中文名歸類
  const tname = (c.card_type?.name || '').trim()
  if (tname.includes('角色')) return '角色'
  if (tname.includes('場景')) return '場景'
  if (tname.includes('組織')) return '組織'
  if (tname.includes('物品')) return '物品'
  if (tname.includes('概念')) return '概念'

  // 3) 兼容舊模型名：優先實例/類型的 model_name
  const m = (c as any).model_name || (c.card_type as any)?.model_name || ''
  if (m === 'CharacterCard') return '角色'
  if (m === 'SceneCard') return '場景'
  if (m === 'OrganizationCard') return '組織'

  return '其他'
}

async function buildNameGroupCache() {
  nameToGroup.value = {}
  if (!props.projectId) return
  try {
    const cards: CardRead[] = await getCardsForProject(props.projectId)
    for (const c of cards) {
      const nm = (c.title || '').trim()
      if (!nm) continue
      nameToGroup.value[nm] = detectTypeGroupByCard(c)
    }
  } catch {}
}

async function buildAllGroups() {
  if (!props.projectId) { participantGroups.value = []; return }
  try {
    const cards: CardRead[] = await getCardsForProject(props.projectId)
    const order = ['角色','場景','組織','物品','概念','其他']
    const buckets = new Map<string, Set<string>>()
    order.forEach(t => buckets.set(t, new Set<string>()))
    for (const c of cards) {
      const t = detectTypeGroupByCard(c)
      const title = (c.title || '').trim()
      if (!title) continue
      buckets.get(t)!.add(title)
    }
    participantGroups.value = order
      .map(label => ({ label, values: Array.from(buckets.get(label) || []).sort((a,b)=>a.localeCompare(b)) }))
  } catch {
    participantGroups.value = []
  }
}

function onParticipantsChange() {
  emitParticipants();
}

function participantsForGroup(label: string): string[] {
  return localParticipants.value.filter(name => (nameToGroup.value[name] || '其他') === label)
}

function updateGroupParticipants(label: string, values: string[]) {
  const retained = localParticipants.value.filter(name => (nameToGroup.value[name] || '其他') !== label)
  const selected = values.map(value => String(value).trim()).filter(Boolean)
  if (label === '其他') {
    selected.forEach(name => { if (!nameToGroup.value[name]) nameToGroup.value[name] = '其他' })
  }
  localParticipants.value = Array.from(new Set([...retained, ...selected]))
  onParticipantsChange()
}

function availableForGroup(group: Group): string[] {
  const selected = new Set(participantsForGroup(group.label))
  return group.values.filter(name => !selected.has(name))
}

function addParticipant(label: string, value: string) {
  const name = value.trim()
  if (!name) return
  if (!nameToGroup.value[name]) nameToGroup.value[name] = label
  localParticipants.value = Array.from(new Set([...localParticipants.value, name]))
  pendingParticipant.value[label] = ''
  onParticipantsChange()
}

function removeParticipant(label: string, name: string) {
  updateGroupParticipants(
    label,
    participantsForGroup(label).filter(participant => participant !== name),
  )
}

onMounted(async () => { await buildNameGroupCache(); await buildAllGroups(); if (props.prefetched) assembled.value = props.prefetched })

async function assemble() {
  try {
    assembling.value = true
    const res = await assembleContext({
      project_id: props.projectId,
      volume_number: localVolumeNumber.value ?? undefined,
      chapter_number: localChapterNumber.value ?? undefined,
      participants: localParticipants.value,
      current_draft_tail: props.draftTail || ''
    })
    assembled.value = res
    emit('context-updated', res)
    // 將最新本地值回寫父層，確保儲存時同步
    emitParticipants(); emitVolume(); emitStage(); emitChapter();
    ElMessage.success('上下文已裝配')
  } catch (e:any) {
    ElMessage.error('裝配失敗')
  } finally {
    assembling.value = false
  }
}
</script>

<style scoped>
.ctx-panel { display: flex; flex-direction: column; gap: 0; height: 100%; }
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 2px solid var(--el-border-color-light);
  background: var(--el-fill-color-lighter);
}
.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.entity-sections {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
  padding: 4px 16px 12px;
  overflow-y: auto;
}
.entity-count-warning { margin: 8px 0; }
.entity-section {
  min-width: 0;
  padding: 12px 0;
  background: transparent;
}
.entity-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
  margin-bottom: 7px;
}
.entity-section__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.entity-section__count {
  min-width: 24px;
  padding: 2px 7px;
  border-radius: 999px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  text-align: center;
  font-size: 11px;
}
.entity-chip-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.entity-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 26px;
  padding: 0 9px 0 10px;
  border: 0;
  border-radius: 999px;
  color: var(--el-text-color-primary);
  background: var(--nf-surface-control, var(--el-fill-color));
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.16s ease, background-color 0.16s ease;
}
.entity-chip:hover,
.entity-chip:focus-visible {
  color: var(--el-color-primary);
  background: var(--nf-surface-raised, var(--el-fill-color-light));
  outline: none;
}
.entity-chip__remove {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  line-height: 1;
}
.entity-add-select {
  flex: 0 0 26px;
  width: 26px;
  min-width: 26px;
  max-width: 26px;
}
.entity-add-select :deep(.el-select__wrapper) {
  width: 26px;
  min-width: 26px;
  min-height: 26px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 50% !important;
  background: var(--nf-surface-control, var(--el-fill-color));
  box-shadow: none !important;
  cursor: pointer;
}
.entity-add-select :deep(.el-select__wrapper:hover),
.entity-add-select :deep(.el-select__wrapper.is-focused) {
  background: var(--nf-surface-raised, var(--el-fill-color-light));
}
.entity-add-select :deep(.el-select__placeholder) {
  width: 100%;
  color: var(--el-text-color-primary);
  font-size: 16px;
  font-weight: 500;
  line-height: 26px;
  text-align: center;
}
.entity-add-select :deep(.el-select__suffix) {
  display: none;
}
.entity-add-select :deep(.el-select__input) {
  margin: 0;
  text-align: center;
}
.actions { display: flex; gap: 8px; }
.assembled { padding: 16px; overflow: auto; color: var(--el-text-color-primary); font-size: 14px; line-height: 1.8; }
.pre { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 13px; color: var(--el-text-color-primary); }
.facts-structured { margin-bottom: 8px; }
.facts-title { font-weight: 600; margin: 6px 0; color: var(--el-text-color-primary); }
.list { margin: 0; padding-left: 16px; }
.list li { margin: 4px 0; }
.muted { color: var(--el-text-color-regular); }
.relation-item { margin-bottom: 10px; }
.relation-head { font-weight: 600; margin: 2px 0; color: var(--el-text-color-primary); }
.addressing span { display: inline-block; }
.dialog-text { white-space: pre-wrap; line-height: 1.8; font-size: 13.5px; color: var(--el-text-color-primary); }
.badges { margin-left: 8px; }
.raw-toggle { margin: 6px 0; }
</style> 
