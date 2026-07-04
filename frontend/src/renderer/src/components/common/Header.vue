<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { Setting, Sunny, Moon, Document } from '@element-plus/icons-vue'
import { useAppStore } from '@renderer/stores/useAppStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { useUpdateStore } from '@renderer/stores/useUpdateStore'
import KnowledgeManager from '../setting/KnowledgeManager.vue'

const appStore = useAppStore()
const projectStore = useProjectStore()
const updateStore = useUpdateStore()
const { currentView, isDarkMode } = storeToRefs(appStore)

function toggleTheme() {
  appStore.toggleTheme()
}

function openSettingsDialog() {
  appStore.openSettings()
}

function openWorkflowManager() {
  appStore.goToWorkflows()
  window.location.hash = '#/workflows'
}

function handleLogoClick() {
  if (currentView.value !== 'dashboard') {
    appStore.goToDashboard()
  }
}

const isLogoClickable = computed(() => currentView.value !== 'dashboard')

function openIdeasWorkbench() {
  // 直接調用主進程打開新窗口，避免當前窗口路由或狀態變化引起的閃爍
  // @ts-ignore
  window.api?.openIdeasHome?.()
}

// 知識庫抽屜
// const kbVisible = ref(false)
</script>

<template>
  <header class="app-header">
    <div class="logo-container" @click="handleLogoClick" :class="{ clickable: isLogoClickable }">
      <span class="logo-text">Novel Forge</span>
    </div>
    <div class="actions-container">
      <el-button type="primary" title="靈感工作臺" @click="openIdeasWorkbench">
        <el-icon><Document /></el-icon>
        <span style="margin-left:6px;">靈感</span>
      </el-button>
      <el-button type="primary" plain title="工作流" @click="openWorkflowManager">工作流</el-button>
      <el-button :icon="isDarkMode ? Moon : Sunny" @click="toggleTheme" circle title="切換主題" />
      <el-badge :is-dot="updateStore.hasUpdate" type="warning">
        <el-button :icon="Setting" @click="openSettingsDialog" circle title="設置" />
      </el-badge>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  height: 60px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  flex-shrink: 0; /* Prevent header from shrinking */
}

.logo-container.clickable {
  cursor: pointer;
  transition: opacity 0.2s;
}

.logo-container.clickable:hover {
  opacity: 0.8;
}

.logo-container .logo-text {
  font-size: 20px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.actions-container {
  display: flex;
  gap: 15px;
}
</style> 