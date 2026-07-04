
<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="500" >
    <el-form :model="form" ref="formRef" :rules="rules" label-width="80px" @submit.prevent="handleConfirm">
      <el-form-item label="項目名稱" prop="name">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="項目描述" prop="description">
        <el-input v-model="form.description" type="textarea" />
      </el-form-item>
      <el-form-item v-if="!isEditMode" label="項目模板">
        <el-select v-model="selectedTemplate" placeholder="選擇項目模板（可選）" filterable clearable :loading="loadingTemplates" style="width:100%">
          <el-option label="空白項目" :value="null" />
          <el-option v-for="tpl in projectTemplates" :key="tpl.template" :label="tpl.workflow_name" :value="tpl.template" />
        </el-select>
      </el-form-item>
      <!-- 隱藏的提交按鈕，確保在輸入框按回車會觸發表單提交 -->
      <button type="submit" style="display:none"></button>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirm">確定</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { components } from '@renderer/types/generated'
import { getProjectTemplates } from '@renderer/api/workflows'

type Project = components['schemas']['ProjectRead']
type ProjectCreate = components['schemas']['ProjectCreate']
type ProjectUpdate = components['schemas']['ProjectUpdate']

interface ProjectTemplate {
  workflow_id: number
  workflow_name: string
  template: string | null
  description?: string
}

const visible = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<ProjectCreate | ProjectUpdate>({
  name: '',
  description: ''
})
const editingProject = ref<Project | null>(null)

// 項目模板
const selectedTemplate = ref<string | null>(null)
const projectTemplates = ref<ProjectTemplate[]>([])
const loadingTemplates = ref(false)

const isEditMode = computed(() => !!editingProject.value)
const dialogTitle = computed(() => isEditMode.value ? '編輯項目' : '新建項目')

const rules = reactive<FormRules>({
  name: [{ required: true, message: '請輸入項目名稱', trigger: 'blur' }]
})

const emit = defineEmits(['create', 'update'])

async function loadProjectTemplates() {
  try {
    loadingTemplates.value = true
    const response = await getProjectTemplates()
    projectTemplates.value = response.templates || []
    
    // 默認選擇第一個模板（如果有）
    if (projectTemplates.value.length > 0) {
      selectedTemplate.value = projectTemplates.value[0].template
    }
  } catch (error) {
    console.error('加載項目模板失敗:', error)
    ElMessage.error('加載項目模板失敗')
  } finally {
    loadingTemplates.value = false
  }
}

function open(project: Project | null = null) {
  visible.value = true
  editingProject.value = project
  
  nextTick(() => {
    formRef.value?.resetFields()
    if (project) {
      form.name = project.name
      form.description = project.description || ''
    } else {
      form.name = ''
      form.description = ''
      selectedTemplate.value = null
      // 加載項目模板
      loadProjectTemplates()
    }
  })
}

function handleConfirm() {
  formRef.value?.validate((valid) => {
    if (valid) {
      if (isEditMode.value && editingProject.value) {
        emit('update', editingProject.value.id, { ...form })
      } else {
        const payload: any = { ...form }
        // 顯式傳遞 template 參數（null 表示空白項目）
        payload.template = selectedTemplate.value
        emit('create', payload)
      }
      visible.value = false
    } else {
      ElMessage.error('請填寫必要的表單項')
    }
  })
}

// 暴露 open 方法給父組件
defineExpose({
  open
})
</script>

<style scoped>
.mode-switch { margin-bottom: 8px; }
.selector-block { width: 100%; }
</style>