import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { components } from '@renderer/types/generated'
import { getFreeProject } from '@renderer/api/projects'

type Project = components['schemas']['ProjectRead']

export const useProjectStore = defineStore('project', () => {
  // 當前項目資料
  const currentProject = ref<Project | null>(null)

  // 載入狀態
  const isLoading = ref(false)
  const isSaving = ref(false)

  // Actions
  function setCurrentProject(project: Project) {
    currentProject.value = project
  }

  function setLoading(loading: boolean) {
    isLoading.value = loading
  }

  function setSaving(saving: boolean) {
    isSaving.value = saving
  }

  async function loadFreeProject() {
    try {
      isLoading.value = true
      const proj = await getFreeProject()
      currentProject.value = proj
      return proj
    } finally {
      isLoading.value = false
    }
  }

  function reset() {
    currentProject.value = null
    isLoading.value = false
    isSaving.value = false
  }

  return {
    // State
    currentProject,
    isLoading,
    isSaving,
    
    // Actions
    setCurrentProject,
    setLoading,
    setSaving,
    loadFreeProject,
    reset
  }
}) 