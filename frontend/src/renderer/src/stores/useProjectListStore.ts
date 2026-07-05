import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { getProjects, createProject as apiCreateProject, updateProject as apiUpdateProject, deleteProject as apiDeleteProject } from '@renderer/api/projects'

type Project = components['schemas']['ProjectRead']
type ProjectCreate = components['schemas']['ProjectCreate']
type ProjectUpdate = components['schemas']['ProjectUpdate']

export const useProjectListStore = defineStore('projectList', () => {
  // 項目列表
  const projects = ref<Project[]>([])
  const isLoading = ref(false)

  // Actions
  async function fetchProjects() {
    isLoading.value = true
    try {
      const list = await getProjects()
      projects.value = (list || []).filter(p => (p.name || '') !== '__free__')
    } catch (error) {
      console.error('獲取項目列表失敗:', error)
      ElMessage.error('獲取專案列表失敗')
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function createProject(projectData: ProjectCreate) {
    try {
      const newProject = await apiCreateProject(projectData)
      await fetchProjects()
      ElMessage.success('專案創建成功！')
      return newProject
    } catch (error) {
      ElMessage.error(`創建專案失敗: ${error}`)
      throw error
    }
  }

  async function updateProject(projectId: number, projectData: ProjectUpdate) {
    try {
      await apiUpdateProject(projectId, projectData)
      ElMessage.success('專案更新成功！')
      await fetchProjects()
    } catch (error) {
      ElMessage.error(`更新專案失敗: ${error}`)
      throw error
    }
  }

  async function deleteProject(projectId: number) {
    try {
      // 額外前端保護：阻止刪除保留項目
      const proj = projects.value.find(p => p.id === projectId)
      if (proj && (proj.name || '') === '__free__') {
        ElMessage.warning('系統保留專案不可刪除')
        return
      }
      await apiDeleteProject(projectId)
      ElMessage.success('專案刪除成功！')
      await fetchProjects()
    } catch (error) {
      ElMessage.error(`刪除專案失敗: ${error}`)
      throw error
    }
  }

  function reset() {
    projects.value = []
    isLoading.value = false
  }

  return {
    // State
    projects,
    isLoading,
    
    // Actions
    fetchProjects,
    createProject,
    updateProject,
    deleteProject,
    reset
  }
}) 
