<script setup lang="ts">
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAssistantPreferences } from '@renderer/composables/useAssistantPreferences'
import {
  playTaskDoneSound,
  requestTaskDoneNotificationPermission,
  unlockTaskDoneSound
} from '@renderer/utils/taskDoneNotifier'

// 通過組合式統一管理靈感助手偏好，方便在設定頁與助手面板之間複用
const prefs = useAssistantPreferences()

const ctxSummaryEnabled = computed({
  get: () => prefs.contextSummaryEnabled.value,
  set: (val: boolean) => prefs.setContextSummaryEnabled(val)
})

const ctxSummaryThreshold = computed({
  get: () => prefs.contextSummaryThreshold.value,
  set: (val: number | null) => prefs.setContextSummaryThreshold(val)
})

const reactModeEnabled = computed({
  get: () => prefs.reactModeEnabled.value,
  set: (val: boolean) => prefs.setReactModeEnabled(val)
})

const assistantTemperature = computed({
  get: () => prefs.assistantTemperature.value,
  set: (val: number | null) => prefs.setAssistantTemperature(val)
})

const assistantMaxTokens = computed({
  get: () => prefs.assistantMaxTokens.value,
  set: (val: number | null) => prefs.setAssistantMaxTokens(val)
})

const assistantTimeout = computed({
  get: () => prefs.assistantTimeout.value,
  set: (val: number | null) => prefs.setAssistantTimeout(val)
})

const assistantFontSize = computed({
  get: () => prefs.assistantFontSize.value,
  set: (val: number | null) => prefs.setAssistantFontSize(val)
})

const taskDoneSoundEnabled = computed({
  get: () => prefs.taskDoneSoundEnabled.value,
  set: (val: boolean) => {
    void setTaskDoneSoundEnabled(val)
  }
})

const taskDoneDesktopNotificationEnabled = computed({
  get: () => prefs.taskDoneDesktopNotificationEnabled.value,
  set: (val: boolean) => {
    void setTaskDoneDesktopNotificationEnabled(val)
  }
})

async function setTaskDoneSoundEnabled(val: boolean): Promise<void> {
  prefs.setTaskDoneSoundEnabled(val)
  if (!val) return

  await unlockTaskDoneSound()
}

async function handleTestTaskDoneSound(): Promise<void> {
  try {
    const played = await playTaskDoneSound()
    if (!played) {
      ElMessage.warning('提示音播放失敗，請檢查系統音量、應用音量或瀏覽器音頻權限。')
    }
  } catch {
    ElMessage.warning('提示音播放失敗，請檢查系統音量、應用音量或瀏覽器音頻權限。')
  }
}

async function setTaskDoneDesktopNotificationEnabled(val: boolean): Promise<void> {
  prefs.setTaskDoneDesktopNotificationEnabled(val)
  if (!val) return

  const permission = await requestTaskDoneNotificationPermission()
  if (permission === 'granted') {
    ElMessage.success('桌面通知已啓用。')
    return
  }

  prefs.setTaskDoneDesktopNotificationEnabled(false)
  if (permission === 'denied') {
    ElMessage.warning('桌面通知權限已被系統或瀏覽器拒絕，請在系統/瀏覽器設定中允許通知。')
    return
  }
  if (permission === 'unsupported') {
    ElMessage.warning('當前環境不支持桌面通知。')
    return
  }
  ElMessage.warning('未授予桌面通知權限。')
}
</script>

<template>
  <div class="assistant-settings-root">
    <h3 class="section-title">Agent 設定</h3>
    <p class="section-desc">
      設定通用 Agent 的高級能力，靈感助手與工作流 Agent 共享這些參數與模式。
    </p>

    <el-form label-width="160px" class="assistant-form" size="small">
      <!-- 參數設定組 -->
      <div class="group-title">參數設定</div>

      <el-form-item>
        <template #label>
          <span>
            助手字體大小
            <el-tooltip placement="top" effect="dark">
              <template #content>
                控制靈感助手消息、工具結果和輸入框的主要文字大小。預設 16px，不影響正文編輯器字號。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-input-number
          v-model="assistantFontSize"
          :min="13"
          :max="24"
          :step="1"
          controls-position="right"
        />
        <span class="field-hint">px</span>
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            採樣溫度 (temperature)
            <el-tooltip placement="top" effect="dark">
              <template #content>
                控制輸出的隨機性，數值越大越有創意、越發散，越小越保守、越穩定。<br/>
                建議範圍 0.4 ~ 0.9。預設值爲 0.6。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-input-number
          v-model="assistantTemperature"
          :min="0.1"
          :max="2"
          :step="0.1"
          :precision="2"
          controls-position="right"
          placeholder="0.6"
        />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            最大輸出 Token 數
            <el-tooltip placement="top" effect="dark">
              <template #content>
                控制單次回覆的最大長度。值越大，回覆可以越長，但也會增加響應時間和費用。<br/>
                預設值爲 -1（不限制）。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-input-number
          v-model="assistantMaxTokens"
          :min="-1"
          :max="65536"
          :step="512"
          controls-position="right"
          placeholder="-1"
        />
      </el-form-item>

      <el-form-item>
        <template #label>
          <span>
            超時 (秒)
            <el-tooltip placement="top" effect="dark">
              <template #content>
                限制單次調用的最長等待時間，避免請求長時間掛起。<br/>
                預設值爲 90 秒。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-input-number
          v-model="assistantTimeout"
          :min="10"
          :max="600"
          :step="10"
          controls-position="right"
          placeholder="90"
        />
      </el-form-item>

      <el-divider />

      <!-- React 設定組 -->
      <div class="group-title">模式設定</div>
      <el-form-item>
        <template #label>
          <span>
            React 模式
            <el-tooltip placement="top" effect="dark">
              <template #content>
                讓模型通過文本協議輸出工具調用指令（<Action>{...}</Action>），
                系統解析後真正調用工具，適合不支持函數調用的模型。
              </template>
              <el-icon class="field-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-switch v-model="reactModeEnabled" />
      </el-form-item>

      <el-divider />

      <div class="group-title">完成提醒</div>
      <el-form-item label="任務完成後播放提示音">
        <div class="reminder-control">
          <div class="reminder-control-row">
            <el-switch v-model="taskDoneSoundEnabled" />
            <el-button size="small" plain @click="handleTestTaskDoneSound">試聽提示音</el-button>
          </div>
          <span class="field-hint reminder-hint"
            >靈感助手、續寫、潤色、擴寫、審閱完成時播放短提示音。</span
          >
        </div>
      </el-form-item>
      <el-form-item label="任務完成後顯示桌面通知">
        <el-switch v-model="taskDoneDesktopNotificationEnabled" />
        <span class="field-hint">任務完成時顯示系統桌面通知，需要系統或瀏覽器允許通知權限。</span>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
.assistant-settings-root {
  padding: 16px 12px 24px 12px;
}

.section-title {
  margin: 0 0 4px 0;
  font-size: 15px;
  font-weight: 600;
}

.section-desc {
  margin: 0 0 16px 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.assistant-form {
  max-width: 520px;
}

.field-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.reminder-control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.reminder-control-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.reminder-hint {
  margin-left: 0;
}

.hint-alert {
  margin-top: 12px;
}

.group-title {
  margin: 8px 0 4px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.field-help-icon {
  margin-left: 4px;
  cursor: help;
}
</style>
