<template>
  <div class="llm-config-manager">
    <div class="header">
      <h4>LLM配置管理</h4>
      <el-button type="primary" size="small" @click="openEditDialog()">新增配置</el-button>
    </div>

    <el-table :data="llmConfigs" style="width: 100%" size="small">
      <el-table-column prop="display_name" label="顯示名稱" width="150" />
      <el-table-column prop="provider" label="提供商" width="120" />
      <el-table-column prop="model_name" label="模型名稱" width="200" />
      <el-table-column label="API Base" width="240">
        <template #default="{ row }">
          <span v-if="row.provider === 'openai_compatible'">{{ row.api_base }}</span>
          <span v-else style="color: #909399; font-style: italic;">默認 ({{ row.provider }})</span>
        </template>
      </el-table-column>
      <el-table-column prop="token_limit" label="Token上限" width="90" />
      <el-table-column prop="call_limit" label="調用上限" width="90" />
      <el-table-column label="能力標籤" min-width="180">
        <template #default="{ row }">
          <el-popover v-if="capabilityTags(row).length" placement="top" width="320" trigger="hover">
            <template #reference>
              <div class="capability-cell">
                <el-tag
                  v-for="tag in capabilityTags(row).slice(0, 2)"
                  :key="tag"
                  size="small"
                  :type="capabilityTagType(tag)"
                >
                  {{ tag }}
                </el-tag>
                <span v-if="capabilityTags(row).length > 2" class="more-tags">+{{ capabilityTags(row).length - 2 }}</span>
              </div>
            </template>
            <div class="capability-popover">
              <div class="capability-summary">{{ capabilitySummary(row) }}</div>
              <div class="capability-popover-tags">
                <el-tag
                  v-for="tag in capabilityTags(row)"
                  :key="tag"
                  size="small"
                  :type="capabilityTagType(tag)"
                >
                  {{ tag }}
                </el-tag>
              </div>
            </div>
          </el-popover>
          <el-button v-else size="small" text type="primary" @click="openEditDialog(row)">能力檢測</el-button>
        </template>
      </el-table-column>
      <el-table-column width="200">
        <template #header>
          <span>
            已用（輸入/輸出/調用）
            <el-tooltip placement="top" effect="dark">
              <template #content>
                token 估算規則：<br/>
                - 中文每個漢字計 1<br/>
                - 英文單詞計 1<br/>
                - 每個數字計 1<br/>
                - 非空白符號各計 1<br/>
                注意：不同模型 token 計算不同，此爲粗略估算，僅供參考。<br/>
                <br/>
                顯示格式：<br/>
                - ≥1萬：顯示爲 X.XXX 萬<br/>
                - ≥1百萬：顯示爲 X.XXX 百萬<br/>
                - 最多保留3位小數，自動去除末尾0
              </template>
              <el-icon style="margin-left:4px; cursor: help;"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <template #default="{ row }">
          {{ formatNumber((row as any).used_tokens_input || 0) }} / {{ formatNumber((row as any).used_tokens_output || 0) }} / {{ formatNumber((row as any).used_calls || 0) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="openEditDialog(row)">編輯</el-button>
          <el-button size="small" type="primary" @click="handleCopy(row)" plain>複製</el-button>
          <el-button size="small" type="danger" @click="deleteConfig(row.id)">刪除</el-button>
          <el-button size="small" type="warning" @click="handleReset(row)" plain>重置</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 編輯對話框 -->
    <el-dialog v-model="editDialogVisible" :title="editConfig ? '編輯LLM配置' : '新增LLM配置'" width="500px">
      <LLMConfigForm
        v-if="editDialogVisible"
        :initial-data="editConfig"
        @save="handleSave"
        @refresh="loadLLMConfigs"
        @cancel="editDialogVisible = false"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import LLMConfigForm from './LLMConfigForm.vue'
import type { components } from '@renderer/types/generated'
import { listLLMConfigs, createLLMConfig, updateLLMConfig, deleteLLMConfig, resetLLMUsage, copyLLMConfig } from '@renderer/api/setting'

type LLMConfig = components['schemas']['LLMConfigRead']

const llmConfigs = ref<LLMConfig[]>([])
const editDialogVisible = ref(false)
const editConfig = ref<LLMConfig | null>(null)

/**
 * 格式化數字顯示
 * @param num 數字
 * @returns 格式化後的字符串
 */
function formatNumber(num: number): string {
  if (num >= 1000000) {
    // 大於等於1百萬，顯示爲 X.XXX 百萬
    const millions = num / 1000000
    const formatted = millions.toFixed(3)
    // 去除末尾的0
    const trimmed = parseFloat(formatted).toString()
    return `${trimmed} 百萬`
  } else if (num >= 10000) {
    // 大於等於1萬，顯示爲 X.XXX 萬
    const tenThousands = num / 10000
    const formatted = tenThousands.toFixed(3)
    // 去除末尾的0
    const trimmed = parseFloat(formatted).toString()
    return `${trimmed} 萬`
  } else {
    // 小於1萬，直接顯示原數字
    return num.toString()
  }
}

function capabilityTags(row: LLMConfig): string[] {
  const tags = (row as any).capability_summary?.tags
  return Array.isArray(tags) ? tags.filter((item) => typeof item === 'string') : []
}

function capabilitySummary(row: LLMConfig): string {
  return (row as any).capability_summary?.summary || '暫無檢測摘要'
}

function capabilityTagType(tag: string) {
  if (tag.includes('失敗') || tag.includes('攔截') || tag.includes('不可用')) return 'danger'
  if (tag.includes('建議') || tag.includes('修復') || tag.includes('僅普通')) return 'warning'
  return 'success'
}

async function loadLLMConfigs() {
  try {
    llmConfigs.value = await listLLMConfigs()
  } catch (error) {
    console.error('Failed to load LLM configs:', error)
    ElMessage.error('加載LLM配置失敗')
  }
}

function openEditDialog(config?: LLMConfig) {
  if (config) {
    // 編輯現有配置
    editConfig.value = config
  } else {
    // 新增配置
    editConfig.value = null
  }
  editDialogVisible.value = true
}

async function handleSave(data: any) {
  try {
    if (data.id) {
      await updateLLMConfig(data.id, data)
      ElMessage.success('LLM配置更新成功！')
    } else {
      await createLLMConfig(data)
      ElMessage.success('LLM配置創建成功！')
    }
    editDialogVisible.value = false
    await loadLLMConfigs() // 重新加載列表
  } catch (error) {
    ElMessage.error('保存失敗，請檢查輸入信息')
  }
}

async function deleteConfig(id: number) {
  try {
    await ElMessageBox.confirm('確定要刪除這個LLM配置嗎？', '確認刪除', {
      confirmButtonText: '確定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteLLMConfig(id)
    ElMessage.success('刪除成功')
    await loadLLMConfigs() // 重新加載列表
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('刪除失敗')
    }
  }
}

async function handleReset(row: LLMConfig) {
  try {
    await ElMessageBox.confirm('確認將該配置的統計（輸入/輸出token、調用次數）清零？', '重置統計', {
      type: 'warning', confirmButtonText: '確定', cancelButtonText: '取消'
    })
  } catch (e) {
    return
  }
  try {
    await resetLLMUsage(row.id)
    ElMessage.success('已重置')
    await loadLLMConfigs()
  } catch (e) {
    ElMessage.error('重置失敗')
  }
}

async function handleCopy(row: LLMConfig) {
  try {
    await copyLLMConfig(row.id)
    ElMessage.success('配置複製成功')
    await loadLLMConfigs()
  } catch (error) {
    console.error('複製配置失敗:', error)
    ElMessage.error('複製配置失敗')
  }
}

// 暴露 refresh 給父組件調用
defineExpose({ refresh: loadLLMConfigs })
onMounted(loadLLMConfigs)
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.capability-cell {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.more-tags {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.capability-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.capability-summary {
  overflow-wrap: anywhere;
  color: var(--el-text-color-regular);
}

.capability-popover-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
