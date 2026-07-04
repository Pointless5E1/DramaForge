<script setup lang="ts">
import { ref } from 'vue'
import LLMConfigManager from '../setting/LLMConfigManager.vue'
import Versions from '../Versions.vue'
import PromptWorkshop from '../setting/PromptWorkshop.vue'
import CardTypeManager from '../setting/CardTypeManager.vue'
import KnowledgeManager from '../setting/KnowledgeManager.vue'
import AssistantSettings from '../setting/AssistantSettings.vue'
import { useUpdateStore } from '@renderer/stores/useUpdateStore'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; 'close': [] }>()

const activeTab = ref('llm')
// 讀取全局 store 預設的初始 tab
import { useAppStore } from '@renderer/stores/useAppStore'
const appStore = useAppStore()
const updateStore = useUpdateStore()
activeTab.value = appStore.settingsInitialTab || 'llm'

function handleClose() {
  emit('update:modelValue', false)
  emit('close')
}

// 當切到 LLM 標籤或首次顯示時，讓子組件刷新
import { onMounted, watch, nextTick } from 'vue'
const llmManagerRef = ref()
function emitRefreshIfLLM() {
  if (activeTab.value === 'llm' && llmManagerRef.value?.refresh) {
    llmManagerRef.value.refresh()
  }
}
onMounted(() => emitRefreshIfLLM())
watch(() => activeTab.value, () => emitRefreshIfLLM())
// 對話框每次打開也刷新一次（等待子組件渲染完成）
watch(() => props.modelValue, async (open) => { if (open) { await nextTick(); emitRefreshIfLLM() } })
</script>

<template>
  <el-dialog 
    :model-value="modelValue" 
    @update:model-value="(val) => emit('update:modelValue', val)"
    title="應用設置" 
    width="85%" 
    top="4vh"
    @close="handleClose"
  >
    <div class="settings-container">
      <el-tabs v-model="activeTab" tab-position="left" class="settings-tabs">
        <el-tab-pane label="LLM 配置" name="llm">
          <LLMConfigManager ref="llmManagerRef" />
        </el-tab-pane>
        <el-tab-pane label="知識庫" name="knowledge">
          <KnowledgeManager />
        </el-tab-pane>
        <el-tab-pane label="提示詞工坊" name="prompts">
          <PromptWorkshop />
        </el-tab-pane>
        <el-tab-pane label="卡片類型" name="card-types">
          <CardTypeManager />
        </el-tab-pane>
        <el-tab-pane label="Agent 設置" name="assistant">
          <AssistantSettings />
        </el-tab-pane>
        <el-tab-pane name="about">
          <template #label>
            <el-badge :is-dot="updateStore.hasUpdate" type="warning">
              <span>關於</span>
            </el-badge>
          </template>
          <Versions />
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-dialog>
</template>

<style scoped>
.settings-container { height: 78vh; }
.settings-tabs { height: 100%; }
:deep(.el-dialog__body) { padding-top: 8px; }
:deep(.el-tabs__content) { height: 100%; overflow-y: auto; }
</style> 
