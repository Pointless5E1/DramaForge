import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAppStore = defineStore('app', () => {
  // 當前視圖
  const currentView = ref<'dashboard' | 'editor' | 'ideas' | 'workflows' | 'code-workflows' | 'triggers'>('dashboard')

  // 應用程式固定使用深色主題
  const isDarkMode = ref(true)

  // 設定對話框狀態
  const settingsDialogVisible = ref(false)
  const settingsInitialTab = ref<string>('llm')

  // 全局載入狀態
  const globalLoading = ref(false)

  // 全局錯誤狀態
  const globalError = ref<string | null>(null)

  // Computed
  const isDashboard = computed(() => currentView.value === 'dashboard')
  const isEditor = computed(() => currentView.value === 'editor')
  const isWorkflows = computed(() => currentView.value === 'workflows')

  // Actions
  function setCurrentView(view: 'dashboard' | 'editor' | 'ideas' | 'workflows' | 'code-workflows' | 'triggers') {
    currentView.value = view
  }

  function goToDashboard() {
    currentView.value = 'dashboard'
  }

  function goToEditor() {
    currentView.value = 'editor'
  }

  function goToIdeas() {
    currentView.value = 'ideas'
  }

  function goToWorkflows() {
    currentView.value = 'workflows'
  }

  function goToCodeWorkflows() {
    currentView.value = 'code-workflows'
  }

  function goToTriggers() {
    currentView.value = 'triggers'
  }

  function applyTheme() {
    const html = document.documentElement
    isDarkMode.value = true
    html.classList.add('dark')
  }

  function initTheme() {
    isDarkMode.value = true
    localStorage.setItem('theme', 'dark')
    applyTheme()
  }

  function openSettings(tab?: string) {
    if (tab) settingsInitialTab.value = tab
    settingsDialogVisible.value = true
  }

  function closeSettings() {
    settingsDialogVisible.value = false
  }

  function setGlobalLoading(loading: boolean) {
    globalLoading.value = loading
  }

  function setGlobalError(error: string | null) {
    globalError.value = error
  }

  function clearGlobalError() {
    globalError.value = null
  }

  function reset() {
    currentView.value = 'dashboard'
    settingsDialogVisible.value = false
    globalLoading.value = false
    globalError.value = null
  }

  return {
    // State
    currentView,
    isDarkMode,
    settingsDialogVisible,
    settingsInitialTab,
    globalLoading,
    globalError,

    // Computed
    isDashboard,
    isEditor,
    isWorkflows,

    // Actions
    setCurrentView,
    goToDashboard,
    goToEditor,
    goToIdeas,
    goToWorkflows,
    goToCodeWorkflows,
    goToTriggers,
    applyTheme,
    initTheme,
    openSettings,
    closeSettings,
    setGlobalLoading,
    setGlobalError,
    clearGlobalError,
    reset
  }
}) 
