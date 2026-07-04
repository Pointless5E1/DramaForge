import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listPrompts, type Prompt } from '@renderer/api/setting'

export const usePromptStore = defineStore('prompt', () => {
  // State
  const prompts = ref<Prompt[]>([])
  const isLoading = ref(false)

  // Actions
  async function fetchPrompts() {
    isLoading.value = true
    try {
      const list = await listPrompts()
      prompts.value = list || []
    } catch (error) {
      console.error('獲取提示詞列表失敗:', error)
      ElMessage.error('獲取提示詞列表失敗')
      throw error
    } finally {
      isLoading.value = false
    }
  }

  return {
    prompts,
    isLoading,
    fetchPrompts
  }
})
