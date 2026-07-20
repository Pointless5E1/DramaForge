<template>
	<div class="ai-param-inline">
		<el-button v-if="showTrigger" type="primary" size="small" class="model-trigger" @click="open">
					<template #icon>
						<el-icon><Setting /></el-icon>
					</template>
					<span class="model-label">模型：</span>
					<span class="model-name">{{ selectedModelName || '未設定' }}</span>
		</el-button>
		<el-dialog v-model="visible" title="模型與生成參數" width="520px" append-to-body align-center>
			<div class="ai-config-form">
				<el-form label-width="110px">
					<el-form-item label="模型ID">
						<el-select v-model="editing.llm_config_id" placeholder="選擇模型" style="width: 240px;" :teleported="false">
							<el-option v-for="m in (aiOptions?.llm_configs || [])" :key="m.id" :label="m.display_name || String(m.id)" :value="Number(m.id)" />
						</el-select>
					</el-form-item>
					<el-form-item label="提示詞">
						<el-select v-model="editing.prompt_name" placeholder="選擇提示詞" filterable style="width: 240px;" :teleported="false">
							<el-option v-for="p in (aiOptions?.prompts || [])" :key="p.id" :label="p.name" :value="p.name" />
						</el-select>
					</el-form-item>
					<el-form-item label="溫度">
						<el-input-number v-model="editing.temperature" :min="0" :max="2" :step="0.1" />
					</el-form-item>
					<el-form-item label="最大tokens">
						<el-input-number v-model="editing.max_tokens" :min="1" :step="256" />
					</el-form-item>
					<el-form-item label="超時(秒)">
						<el-input-number v-model="editing.timeout" :min="1" :step="5" />
					</el-form-item>
				</el-form>
			</div>
			<template #footer>
				<div class="ai-actions">
					<div class="left">
						<el-button @click="visible = false">取消</el-button>
						<el-button @click="resetToPreset">重置為預設</el-button>
					</div>
					<div class="right">
						<el-button type="warning" plain @click="restoreFollowType">恢復跟隨類型</el-button>
						<el-button type="primary" plain @click="applyToType">應用到類型</el-button>
						<el-button type="primary" @click="saveLocal">儲存</el-button>
					</div>
				</div>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { usePerCardAISettingsStore, type PerCardAIParams } from '@renderer/stores/usePerCardAISettingsStore'
import { getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import { getCardAIParams, updateCardAIParams, applyCardAIParamsToType } from '@renderer/api/setting'
import { ElMessage } from 'element-plus'

const props = withDefaults(defineProps<{ cardId: number; cardTypeName?: string; showTrigger?: boolean }>(), {
	showTrigger: true,
})

const store = usePerCardAISettingsStore()
const visible = ref(false)
const aiOptions = ref<AIConfigOptions | null>(null)
const editing = ref<PerCardAIParams>({})

async function loadOptions() { try { aiOptions.value = await getAIConfigOptions() } catch {} }

async function refreshForCard(id: number): Promise<void> {
	if (!id) return
	await loadOptions()
	try {
		const resp = await getCardAIParams(id)
		const eff = (resp as any)?.effective_params
		if (eff && Object.keys(eff).length) {
			const fixed = { ...eff, llm_config_id: eff.llm_config_id == null ? eff.llm_config_id : Number(eff.llm_config_id) }
			editing.value = fixed
			store.setForCard(id, { ...fixed })
			return
		}
	} catch {}
	const fallback = store.getByCardId(id)
	if (fallback) editing.value = { ...fallback }
}

function open(): void {
	visible.value = true
	void refreshForCard(props.cardId)
}

defineExpose({ open })

const saved = computed(() => store.getByCardId(props.cardId))
const selectedModelName = computed(() => {
	try {
		const raw = (saved.value || editing.value)?.llm_config_id as any
		const id = raw == null ? undefined : Number(raw)
		const list = aiOptions.value?.llm_configs || []
		const found = list.find(m => Number(m.id) === id)
		return found?.display_name || (id != null ? String(id) : '')
	} catch { return '' }
})

watch(() => props.cardId, (id) => {
	if (!id) return
	// 隱藏的設定面板不在切卡時讀取後端；先使用父編輯器已載入的快取。
	const cached = store.getByCardId(id)
	if (cached) {
		const sv = cached as any
		editing.value = { ...sv, llm_config_id: sv?.llm_config_id == null ? sv?.llm_config_id : Number(sv.llm_config_id) }
	} else {
		const preset = getPresetForType(props.cardTypeName)
		editing.value = { ...preset, llm_config_id: preset.llm_config_id == null ? preset.llm_config_id : Number(preset.llm_config_id) }
	}
}, { immediate: true })

function getPresetForType(typeName?: string): PerCardAIParams {
	const map: Record<string, PerCardAIParams> = {
		'金手指': { prompt_name: '金手指生成', temperature: 0.6, max_tokens: 1024, timeout: 60 },
		'一句話梗概': { prompt_name: '一句話梗概', temperature: 0.6, max_tokens: 1024, timeout: 60 },
		'世界觀設定': { prompt_name: '世界觀設定', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'核心藍圖': { prompt_name: '核心藍圖', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'分卷大綱': { prompt_name: '分卷大綱', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'階段大綱': { prompt_name: '階段大綱', temperature: 0.6, max_tokens: 8192, timeout: 120 },
		'章節大綱': { prompt_name: '章節大綱', temperature: 0.6, max_tokens: 4096, timeout: 60 },
		'寫作指南': { prompt_name: '寫作指南', temperature: 0.7, max_tokens: 8192, timeout: 60 },
		'章節正文': { prompt_name: '內容生成', temperature: 0.7, max_tokens: 8192, timeout: 60 },
	}
	return map[typeName || ''] || {}
}

function saveLocal(): void {
	try {
		const payload = { ...editing.value, llm_config_id: editing.value.llm_config_id == null ? editing.value.llm_config_id : Number(editing.value.llm_config_id) }
		// 先寫入後端資料庫
		updateCardAIParams(props.cardId, payload)
			.then(() => {
				store.setForCard(props.cardId, { ...payload })
				ElMessage.success('已儲存')
				visible.value = false
			})
			.catch(() => { ElMessage.error('儲存到後端失敗') })
	} catch { ElMessage.error('儲存失敗') }
}
function resetToPreset(): void {
	const preset = getPresetForType(props.cardTypeName)
	editing.value = { ...preset, llm_config_id: preset.llm_config_id == null ? preset.llm_config_id : Number(preset.llm_config_id) }
	store.setForCard(props.cardId, editing.value)
}
async function restoreFollowType() {
	try { await updateCardAIParams(props.cardId, null); ElMessage.success('已恢復跟隨類型'); const resp = await getCardAIParams(props.cardId); const eff = (resp as any)?.effective_params; if (eff) { editing.value = { ...eff }; store.setForCard(props.cardId, { ...eff }) } } catch { ElMessage.error('操作失敗') }
}
async function applyToType() {
	try {
		await updateCardAIParams(props.cardId, { ...editing.value })
		await applyCardAIParamsToType(props.cardId)
		window.dispatchEvent(new Event('card-types-updated'))
		await updateCardAIParams(props.cardId, null)
		const resp = await getCardAIParams(props.cardId)
		const eff = (resp as any)?.effective_params
		if (eff) { editing.value = { ...eff }; store.setForCard(props.cardId, { ...eff }) }
		ElMessage.success('已應用到類型，並恢復本卡片跟隨類型')
	} catch { ElMessage.error('應用失敗') }
}

</script>

<style scoped>
.ai-param-inline { 
  display: inline-flex; 
  align-items: center; 
}

.ai-config-form { padding-top: 4px; }

.ai-actions {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.ai-actions .left,
.ai-actions .right { display: flex; gap: 8px; }

.model-trigger { 
  min-width: 200px;
  max-width: 320px;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  overflow: hidden; /* 確保按鈕本身不超出 */
}

.model-trigger :deep(.el-button__content) {
  display: flex;
  align-items: center;
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}

.model-label { 
  flex-shrink: 0;
  margin-right: 4px;
  font-weight: 500;
}

.model-name { 
  flex: 1; 
  min-width: 0; 
  overflow: hidden; 
  text-overflow: ellipsis; 
  white-space: nowrap;
  text-align: left;
}
</style>
