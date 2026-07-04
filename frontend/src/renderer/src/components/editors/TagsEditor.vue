<template>
  <div class="tags-editor">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>作品標籤設定</span>
          <div>
            <el-button type="primary" @click="handleRandomize">一鍵隨機靈感</el-button>
            <el-button type="success" :loading="isSaving" @click="saveTags">保存更改</el-button>
          </div>
        </div>
      </template>
      <div class="tag-selection-container">
        <el-scrollbar>
          <div class="category-block">
            <div class="category-header">
              <h3>主題標籤</h3>
              <el-button @click="randomizeTheme" type="primary" plain size="small">隨機靈感</el-button>
            </div>
            <el-cascader
              :model-value="themeArray"
              @change="handleThemeChange"
              :options="themeOptions"
              placeholder="請選擇小說主題"
              style="width: 100%"
            />
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>目標讀者</h3>
              <el-button @click="randomizeAudience" type="primary" plain size="small">隨機靈感</el-button>
            </div>
            <el-radio-group v-model="localData.audience">
              <el-radio v-for="opt in audienceOptions" :key="opt" :value="opt" border>{{ opt }}</el-radio>
            </el-radio-group>
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>寫作人稱</h3>
              <el-button @click="randomizePerson" type="primary" plain size="small">隨機靈感</el-button>
            </div>
            <el-radio-group v-model="localData.narrative_person">
              <el-radio v-for="opt in personOptions" :key="opt" :value="opt" border>{{ opt }}</el-radio>
            </el-radio-group>
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>類別標籤 (建議選擇 3-5 個)</h3>
              <el-button @click="randomizeStoryTags" type="primary" plain size="small">隨機靈感</el-button>
            </div>
            <div class="story-tags-grid">
              <div v-for="full in categoryOptions" :key="full" class="story-tag-item">
                <el-checkbox
                  :model-value="isStoryTagSelected(full)"
                  @change="(checked) => handleStoryTagChange(checked, full)"
                >
                  {{ stripAnnotation(full) }}
                </el-checkbox>
                <el-select
                  v-if="isStoryTagSelected(full)"
                  :model-value="getStoryTagWeight(full)"
                  @change="(weight) => updateStoryTagWeight(full, weight as WeightLevel)"
                  size="small"
                  class="weight-input"
                  placeholder="權重"
                >
                  <el-option v-for="w in WEIGHT_LEVELS" :key="w" :label="w" :value="w" />
                </el-select>
              </div>
            </div>
          </div>

          <div class="category-block">
            <div class="category-header">
              <h3>情感關係</h3>
              <el-button @click="randomizeRelationship" type="primary" plain size="small">隨機靈感</el-button>
            </div>
                          <el-radio-group v-model="localData.affection">
                <el-radio v-for="tag in relationshipOptions" :key="tag" :value="tag" border>{{ tag }}</el-radio>
              </el-radio-group>
          </div>
        </el-scrollbar>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { ElCard, ElButton } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { useCardStore } from '@renderer/stores/useCardStore'
import { ElMessage } from 'element-plus'
// 引入原子組件
import { 
  ElCheckbox,
  ElRadio,
  ElRadioGroup,
  ElCascader,
  ElScrollbar,
  ElSelect,
  ElOption
} from 'element-plus'
import { onMounted } from 'vue'
import { listKnowledge } from '@renderer/api/setting'
// Define types from generated schemas
type CardRead = components['schemas']['CardRead']
type Tags = components['schemas']['Tags']
type WeightLevel = '低權重' | '中權重' | '高權重'
// 權重檔位常量，統一來源
const WEIGHT_LEVELS: WeightLevel[] = ['低權重', '中權重', '高權重']
const DEFAULT_WEIGHT: WeightLevel = '中權重'

const props = defineProps<{
  card: CardRead
}>()

const cardStore = useCardStore()
const isSaving = ref(false)

// 本地可編輯數據
const localData = reactive<Tags>({
  theme: '',
  audience: '通用' as any,
  narrative_person: '第三人稱' as any,
  story_tags: [],
  affection: ''
})
// 選項數據（運行時從知識庫解析填充）
const themeOptions = ref<any[]>([])
const categoryOptions = ref<string[]>([])
const relationshipOptions = ref<string[]>([])
const audienceOptions = ref<string[]>([])
const personOptions = ref<string[]>([])

watch(
  () => props.card,
  (newCard) => {
    // 確保 content 是對象後再賦值
    if (newCard && newCard.content && typeof newCard.content === 'object') {
      Object.assign(localData, newCard.content as unknown as Partial<Tags>)
    }
  },
  { deep: true, immediate: true }
)

// 隨機化入口
const handleRandomize = () => {
  randomizeAll()
}

// 保存
const saveTags = async () => {
  isSaving.value = true
  try {
    await cardStore.modifyCard(props.card.id, { content: localData });
    ElMessage.success('已保存標籤設置')
  } catch (error) {
    // 錯誤消息已在 store 處理
  } finally {
    isSaving.value = false
  }
}

// 主題聯動
const themeArray = computed(() => {
  return localData.theme ? localData.theme.split('-') : []
})

function handleThemeChange(value: any) {
  if (Array.isArray(value)) {
    localData.theme = (value as string[]).join('-')
  }
}

// 類別標籤邏輯
function isStoryTagSelected(tagName: string) {
  return localData.story_tags.some(([name]) => name === tagName)
}

function getStoryTagWeight(tagName: string): WeightLevel {
  const tag = localData.story_tags.find(([name]) => name === tagName)
  return (tag ? (tag[1] as WeightLevel) : DEFAULT_WEIGHT)
}

function handleStoryTagChange(checked: any, tagName: string) {
  const index = localData.story_tags.findIndex(([name]) => name === tagName)
  if (checked as boolean) {
    if (index === -1) {
      localData.story_tags.push([tagName, DEFAULT_WEIGHT as any])
    }
  } else {
    if (index !== -1) {
      localData.story_tags.splice(index, 1)
    }
  }
}

function updateStoryTagWeight(tagName: string, weight: WeightLevel | undefined) {
  const tag = localData.story_tags.find(([name]) => name === tagName)
  if (tag && typeof weight === 'string') {
    tag[1] = weight
  }
}

// 隨機化
function randomizeAll() {
  randomizeTheme()
  randomizeAudience()
  randomizePerson()
  randomizeStoryTags()
  randomizeRelationship()
}

function randomizeTheme() {
  if (!themeOptions.value.length) return
  const mainTheme = themeOptions.value[Math.floor(Math.random() * themeOptions.value.length)]
  const subTheme = mainTheme.children[Math.floor(Math.random() * mainTheme.children.length)]
  localData.theme = `${mainTheme.value}-${subTheme.value}`
}

function randomizeStoryTags() {
  const count = Math.floor(Math.random() * 3) + 3 // 3 到 5 個
  const shuffled = [...categoryOptions.value].sort(() => 0.5 - Math.random())
  localData.story_tags = shuffled.slice(0, count).map(tag => {
    const weight = WEIGHT_LEVELS[Math.floor(Math.random() * WEIGHT_LEVELS.length)]
    return [tag, weight as any]
  })
}

function randomizeRelationship() {
  if (!relationshipOptions.value.length) return
  localData.affection = relationshipOptions.value[Math.floor(Math.random() * relationshipOptions.value.length)]
}

function randomizeAudience() {
  if (!audienceOptions.value.length) return
  localData.audience = audienceOptions.value[Math.floor(Math.random() * audienceOptions.value.length)] as any
}

function randomizePerson() {
  if (!personOptions.value.length) return
  localData.narrative_person = personOptions.value[Math.floor(Math.random() * personOptions.value.length)] as any
}

// 知識庫解析：僅渲染名稱；story_tags 存儲完整項
function stripAnnotation(label: string): string {
  // 去除括號中的註解（中文/英文括號）
  return label.replace(/\s*[（(].*[）)]\s*$/, '')
}

function parseKnowledge(text: string) {
  // 去除圍欄與空白行
  const rawLines = (text || '').split(/\r?\n/)
  const lines: string[] = []
  for (const l of rawLines) {
    const t = l.replace(/\t/g, '    ')
    if (!t.trim().length) continue
    if (t.trim() === '```') continue
    lines.push(t)
  }
  type Section = 'none' | 'theme' | 'audience' | 'person' | 'category' | 'affection'
  let section: Section = 'none'
  const themes: Record<string, string[]> = {}
  let currentTheme: string | null = null
  const categories: string[] = []
  const relationships: string[] = []
  const audiences: string[] = []
  const persons: string[] = []

  for (const raw of lines) {
    const m = raw.match(/^(\s*)-\s*(.+)$/)
    if (!m) continue
    const indent = m[1].length
    const content = m[2].trim()

    // 切換段落
    if (indent <= 2) {
      if (content.startsWith('主題標籤')) { section = 'theme'; currentTheme = null; continue }
      if (content.startsWith('目標羣體')) { section = 'audience'; continue }
      if (content.startsWith('寫作人稱')) { section = 'person'; continue }
      if (content.startsWith('類別標籤')) { section = 'category'; continue }
      if (content.startsWith('情感關係')) { section = 'affection'; continue }
    }

    if (section === 'theme') {
      const ROOT_INDENT_MAX = 6
      if (indent <= ROOT_INDENT_MAX || !currentTheme) {
        const name = stripAnnotation(content)
        if (!themes[name]) themes[name] = []
        currentTheme = name
      } else {
        const sub = stripAnnotation(content)
        if (!currentTheme) {
          const fallback = stripAnnotation(content)
          themes[fallback] = []
          currentTheme = fallback
        } else {
          themes[currentTheme].push(sub)
        }
      }
      continue
    }

    if (section === 'audience') {
      const name = stripAnnotation(content)
      if (name) audiences.push(name)
      continue
    }
    if (section === 'person') {
      const name = stripAnnotation(content)
      if (name) persons.push(name)
      continue
    }
    if (section === 'category') {
      // 類別：保留完整字符串（含註解）
      categories.push(content)
      continue
    }
    if (section === 'affection') {
      const name = stripAnnotation(content)
      if (name) relationships.push(name)
      continue
    }
  }

  themeOptions.value = Object.keys(themes).map(k => ({ value: k, label: k, children: (themes[k] || []).map(s => ({ value: s, label: s })) }))
  categoryOptions.value = categories
  relationshipOptions.value = relationships
  audienceOptions.value = audiences.length ? audiences : ['通用','男生','女生']
  personOptions.value = persons.length ? persons : ['第一人稱','第三人稱']
}

onMounted(async () => {
  try {
    const list = await listKnowledge()
    const kb = (list || []).find(k => k && k.name === '作品標籤')
    if (kb && kb.content) parseKnowledge(kb.content)
  } catch {}
})
// ----------------- 合併邏輯結束 -----------------
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 原 Step0TagSelection 樣式 */
.tag-selection-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.category-block {
  margin-bottom: 24px;
}
.category-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.category-block h3 {
  margin-bottom: 0;
  font-size: 1.1em;
  font-weight: 600;
  border-left: 4px solid var(--el-color-primary);
  padding-left: 8px;
  color: var(--text-color-primary);
}

.story-tags-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
}

.story-tag-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.weight-input {
  width: 70px;
}

.el-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.el-radio.is-bordered {
  margin: 0;
}
</style> 