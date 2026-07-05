/**
 * 更新檢測狀態管理 Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ReleaseInfo, UpdateCheckResult } from '@renderer/services/updateService'
import { autoCheckForUpdates, manualCheckForUpdates, getCurrentVersion } from '@renderer/services/updateService'

export const useUpdateStore = defineStore('update', () => {
  // 當前版本
  const currentVersion = ref(getCurrentVersion())
  
  // 最新版本資訊
  const latestVersion = ref<string | null>(null)
  const releaseInfo = ref<ReleaseInfo | null>(null)
  
  // 是否有可用更新
  const hasUpdate = computed(() => {
    return latestVersion.value !== null && releaseInfo.value !== null
  })
  
  // 檢測狀態
  const isChecking = ref(false)
  const lastCheckTime = ref<Date | null>(null)
  const lastCheckError = ref<string | null>(null)
  
  // 自動檢測開關（持久化到 localStorage）
  const autoCheckEnabled = ref(true)
  
  // 初始化時從 localStorage 讀取設定
  const STORAGE_KEY = 'novelforge_auto_update_enabled'
  const storedSetting = localStorage.getItem(STORAGE_KEY)
  if (storedSetting !== null) {
    autoCheckEnabled.value = storedSetting === 'true'
  }
  
  // 監聽自動檢測開關變化，同步到 localStorage
  function setAutoCheckEnabled(enabled: boolean) {
    autoCheckEnabled.value = enabled
    localStorage.setItem(STORAGE_KEY, String(enabled))
  }
  
  /**
   * 執行更新檢測（內部方法）
   */
  async function performCheck(checkFn: () => Promise<UpdateCheckResult>): Promise<UpdateCheckResult> {
    isChecking.value = true
    lastCheckError.value = null
    
    try {
      const result = await checkFn()
      
      lastCheckTime.value = new Date()
      
      if (result.hasUpdate && result.releaseInfo) {
        latestVersion.value = result.latestVersion || null
        releaseInfo.value = result.releaseInfo
      } else {
        latestVersion.value = null
        releaseInfo.value = null
      }
      
      return result
    } catch (error: any) {
      lastCheckError.value = error.message || '檢測失敗'
      throw error
    } finally {
      isChecking.value = false
    }
  }
  
  /**
   * 自動檢測更新（帶重試）
   */
  async function autoCheck(): Promise<UpdateCheckResult> {
    return performCheck(autoCheckForUpdates)
  }
  
  /**
   * 手動檢測更新（不重試）
   */
  async function manualCheck(): Promise<UpdateCheckResult> {
    return performCheck(manualCheckForUpdates)
  }
  
  /**
   * 清除更新狀態（用戶已知曉更新後可調用）
   */
  function clearUpdateNotification() {
    // 注意：這裏不清除 latestVersion 和 releaseInfo，
    // 只是用於 UI 邏輯（比如關閉通知彈窗）
    // 如果需要真正清除，可以在這裏實現
  }
  
  /**
   * 重置錯誤狀態
   */
  function clearError() {
    lastCheckError.value = null
  }
  
  return {
    // 狀態
    currentVersion,
    latestVersion,
    releaseInfo,
    hasUpdate,
    isChecking,
    lastCheckTime,
    lastCheckError,
    autoCheckEnabled,
    
    // 方法
    autoCheck,
    manualCheck,
    setAutoCheckEnabled,
    clearUpdateNotification,
    clearError
  }
})
