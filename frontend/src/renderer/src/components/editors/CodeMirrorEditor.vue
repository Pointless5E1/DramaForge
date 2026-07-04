<template>
	<div class="chapter-studio">
	<div class="toolbar">
		<div class="toolbar-row">
			<!-- 編輯功能組 -->
			<div class="toolbar-group">
				<span class="group-label">編輯</span>
				<el-dropdown @command="(c:any) => fontSize = c" size="small">
					<el-button size="small">
						{{ fontSize }}px
						<el-icon class="el-icon--right"><arrow-down /></el-icon>
					</el-button>
					<template #dropdown>
						<el-dropdown-menu>
							<el-dropdown-item :command="14">小 (14px)</el-dropdown-item>
							<el-dropdown-item :command="16">中 (16px)</el-dropdown-item>
							<el-dropdown-item :command="18">大 (18px)</el-dropdown-item>
							<el-dropdown-item :command="20">特大 (20px)</el-dropdown-item>
							<el-dropdown-item :command="24">超大 (24px)</el-dropdown-item>
							<el-dropdown-item :command="28">巨大 (28px)</el-dropdown-item>
							<el-dropdown-item :command="32">最大 (32px)</el-dropdown-item>
						</el-dropdown-menu>
					</template>
				</el-dropdown>

				<el-dropdown @command="(c:any) => lineHeight = c" size="small">
					<el-button size="small">
						{{ lineHeight }}
						<el-icon class="el-icon--right"><arrow-down /></el-icon>
					</el-button>
					<template #dropdown>
						<el-dropdown-menu>
							<el-dropdown-item :command="1.4">緊湊</el-dropdown-item>
							<el-dropdown-item :command="1.6">適中</el-dropdown-item>
							<el-dropdown-item :command="1.8">舒適</el-dropdown-item>
							<el-dropdown-item :command="2.0">寬鬆</el-dropdown-item>
						</el-dropdown-menu>
					</template>
				</el-dropdown>
			</div>

			<div class="toolbar-divider"></div>

			<!-- AI功能組 -->
			<div class="toolbar-group toolbar-group-ai">
				<span class="group-label">AI</span>
				<div class="ai-action-bar">
					<el-button type="primary" size="small" :loading="aiLoading" :disabled="reviewLoading" @click="executeAIContinuation">
						<el-icon><MagicStick /></el-icon> 續寫
					</el-button>

					<el-dropdown
						split-button
						type="primary"
						size="small"
						popper-class="review-prompt-dropdown"
						:disabled="aiLoading || reviewLoading"
						:loading="reviewLoading"
						@command="handleReviewPromptChange"
						@click="executeReview"
					>
						<span class="review-button-label">
							<el-icon v-if="reviewLoading" class="review-loading-icon"><Loading /></el-icon>
							<el-icon v-else><List /></el-icon>
							{{ reviewLoading ? '審核中...' : '審核' }}
						</span>
						<template #dropdown>
							<el-dropdown-menu>
								<el-dropdown-item
									v-for="prompt in reviewPrompts"
									:key="prompt"
									:command="prompt"
								>
									<div class="prompt-item">
										<span>{{ prompt }}</span>
										<el-icon v-if="prompt === currentReviewPrompt" class="check-icon"><Select /></el-icon>
									</div>
								</el-dropdown-item>
							</el-dropdown-menu>
						</template>
					</el-dropdown>

					<el-dropdown size="small" @command="handleAiQuickAction">
						<el-button plain size="small">
							更多 AI
							<el-icon class="el-icon--right"><ArrowDown /></el-icon>
						</el-button>
						<template #dropdown>
							<el-dropdown-menu>
								<el-dropdown-item command="polish" :disabled="aiLoading || reviewLoading">
									潤色（{{ currentPolishPrompt }}）
								</el-dropdown-item>
							<el-dropdown-item command="expand" :disabled="aiLoading || reviewLoading">
								擴寫（{{ currentExpandPrompt }}）
							</el-dropdown-item>
						</el-dropdown-menu>
					</template>
					</el-dropdown>

					<el-popover trigger="click" width="320" popper-class="chapter-ai-prompt-popper">
						<template #reference>
							<el-button plain size="small">提示詞</el-button>
						</template>
						<div class="prompt-settings-panel">
							<div class="prompt-settings-title">AI 提示詞</div>
							<div class="prompt-settings-item">
								<label>潤色</label>
								<el-select v-model="currentPolishPrompt" size="small" @change="handlePolishPromptChange">
									<el-option v-for="p in polishPrompts" :key="p" :label="p" :value="p" />
								</el-select>
							</div>
							<div class="prompt-settings-item">
								<label>擴寫</label>
								<el-select v-model="currentExpandPrompt" size="small" @change="handleExpandPromptChange">
									<el-option v-for="p in expandPrompts" :key="p" :label="p" :value="p" />
								</el-select>
							</div>
						</div>
					</el-popover>

					<AIPerCardParams
						:card-id="props.card.id"
						:card-type-name="props.card.card_type?.name"
						class="ai-config-entry"
					/>

					<el-button
						type="danger"
						plain
						size="small"
						:disabled="!canInterruptAiTask"
						@click="interruptStream"
					>
						<el-icon><CircleClose /></el-icon> 中斷
					</el-button>
				</div>
			</div>
		</div>
		<div class="toolbar-status-row">
			<div class="toolbar-status-spacer"></div>
			<div class="ai-status-strip">
				<span class="status-pill">模型 · {{ selectedModelName || '未設置' }}</span>
				<span class="status-pill">目標 · {{ activeContinuationConfig.targetWordCount }} 字</span>
				<span class="status-pill">模式 · {{ formatContinuationMode(activeContinuationConfig.wordControlMode) }}</span>
			</div>
		</div>
	</div>

	<div class="editor-content-wrapper">
		<!-- 標題區域 -->
	<div class="chapter-header">
		<div class="title-section">
			<h1
				class="chapter-title"
				contenteditable="true"
				@blur="handleTitleBlur"
				@keydown.enter.prevent="handleTitleEnter"
				ref="titleElement"
			>{{ localCard.title }}</h1>
			<div class="title-meta">
				<el-icon class="word-count-icon"><Timer /></el-icon>
				<span class="word-count-text">{{ wordCount }} 字</span>
			</div>
		</div>
	</div>

		<!-- CodeMirror 容器 -->
		<div ref="cmRoot" class="editor-content"></div>
		<div v-if="pendingAiEdit && !pendingAiEdit.generating" class="ai-replace-review-bar">
			<span class="review-hint">
                <template v-if="nfAssistantPatchTotal">
                        建議 #{{ nfAssistantPatchCurrentNo }} / {{ nfAssistantPatchTotal }}：灰色爲原文，藍色爲新文本
                </template>
                <template v-else>
                        已生成替換建議：灰色爲原文，藍色爲新文本
                </template>
        </span>
        <div class="review-actions">
                <el-button v-if="nfAssistantPatchTotal > 1" size="small" @click="nfAssistantPatchPrev">上一條</el-button>
                <el-button v-if="nfAssistantPatchTotal > 1" size="small" @click="nfAssistantPatchNext">下一條</el-button>
                <el-button type="primary" size="small" @click="nfAssistantPatchTotal ? nfAssistantPatchAcceptCurrent() : acceptPendingAiEdit()">
                        {{ nfAssistantPatchTotal ? '接受本條' : '接受並替換' }}
                </el-button>
                <el-button size="small" @click="nfAssistantPatchTotal ? nfAssistantPatchRejectCurrent() : rejectPendingAiEdit()">
                        {{ nfAssistantPatchTotal ? '拒絕本條' : '拒絕並還原' }}
                </el-button>
        </div>
		</div>
	</div>

		<!-- 右鍵快速編輯菜單 -->
		<Teleport to="body">
			<div
				v-if="contextMenu.visible"
				class="context-menu-popup"
				:style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
			>
				<div v-if="!contextMenu.expanded" class="context-menu-compact">
					<el-button
						type="primary"
						size="small"
						@click="expandContextMenu"
					>
						快速編輯
					</el-button>
					<el-button
						size="small"
						type="success"
						@click="handleContextMenuReference"
					>
						引用到靈感助手
					</el-button>
				</div>
				<div v-else class="context-menu-expanded">
					<el-input
						v-model="contextMenu.userRequirement"
						:autosize="{ minRows: 2, maxRows: 4 }"
						type="textarea"
						placeholder="描述你的要求，如：讓語氣更加強硬、增加環境描寫..."
						size="small"
						style="margin-bottom: 8px;"
					/>
					<div class="context-menu-actions">
						<el-button
							type="primary"
							size="small"
							:loading="aiLoading"
							@click="handleContextMenuPolish"
						>
							<el-icon><Document /></el-icon> 潤色
						</el-button>
						<el-button
							type="primary"
							size="small"
							:loading="aiLoading"
							@click="handleContextMenuExpand"
						>
							<el-icon><MagicStick /></el-icon> 擴寫
						</el-button>
						<el-button
							size="small"
							@click="closeContextMenu"
						>
							取消
						</el-button>
					</div>
				</div>
			</div>
		</Teleport>

		<el-dialog v-model="reviewDialogVisible" title="章節審核結果" width="72%">
			<div v-if="reviewText" class="review-dialog-body">
				<div class="review-overview">
					<div class="review-overview-main">
						<el-tag
							v-if="reviewDraft"
							:type="getReviewVerdictTagType(reviewDraft.quality_gate)"
							effect="dark"
						>
							{{ formatReviewVerdict(reviewDraft.quality_gate) }}
						</el-tag>
						<span v-if="reviewDraft" class="review-score">
							{{ reviewDraft.review_profile }}
						</span>
					</div>
					<p class="review-summary">這是本次審核草稿。確認後可創建或更新對應的審核結果卡片。</p>
				</div>

				<div class="review-text-block">
					<SimpleMarkdown
						:markdown="reviewText || '（暫無內容）'"
						class="review-markdown"
					/>
				</div>
			</div>
			<template #footer>
				<div class="review-dialog-footer">
					<el-button @click="reviewDialogVisible = false">關閉</el-button>
					<el-button
						type="primary"
						:loading="reviewCardSaving"
						:disabled="!reviewDraft"
						@click="handleCreateOrUpdateReviewCard"
					>
						{{ reviewDraft?.existing_review_card_id ? '更新審核結果卡片' : '創建審核結果卡片' }}
					</el-button>
				</div>
			</template>
		</el-dialog>

		<ContinuationBudgetDialog
			v-model:visible="continuationDialogVisible"
			:target-word-count="continuationDialogState.targetWordCount"
			:word-control-mode="continuationDialogState.wordControlMode"
			:guidance="continuationDialogState.guidance"
			@confirm="handleContinuationDialogConfirm"
		/>

		<el-dialog v-model="previewDialogVisible" title="動態信息預覽" width="70%">
			<template #header>
				<div class="preview-dialog-header">
					<div class="preview-dialog-header__title">動態信息預覽</div>
				</div>
			</template>
			<div v-if="previewData">
				<div v-if="dynamicMissingCards.length" class="missing-card-panel">
					<el-alert
						type="warning"
						:closable="false"
						show-icon
						title="以下角色在本章正文中被提取到了，但當前項目裏還沒有對應角色卡。確認更新時這些角色會被跳過；如果需要，請先手動新建對應角色卡，再回到當前預覽繼續確認。"
					/>
					<div class="missing-card-list">
						<div v-for="item in dynamicMissingCards" :key="item.key" class="missing-card-item">
							<span>{{ item.title }}</span>
							<el-button size="small" type="primary" plain @click="openCreateCardFromPreview(item)">
								新增{{ item.cardTypeName }}
							</el-button>
						</div>
					</div>
				</div>
				<div v-if="dynamicParticipantReviewNotices.length" class="participant-review-panel">
					<el-alert
						type="info"
						:closable="false"
						show-icon
						title="以下角色仍在本章參與實體裏，但這次動態提取結果中沒有出現。若確認他們已不再參與本章節，可將其移出本章參與實體；如果只是本章沒有新的動態信息，也可以忽略。"
					/>
					<div class="missing-card-list">
						<div v-for="item in dynamicParticipantReviewNotices" :key="item.key" class="missing-card-item">
							<span>{{ item.title }}</span>
							<el-button size="small" type="warning" plain @click="removeParticipantFromCurrentChapter(item)">
								移出本章參與實體
							</el-button>
						</div>
					</div>
				</div>
				<el-empty
					v-if="isDynamicPreviewEmpty"
					description="本次未提取到可寫回的角色動態信息。你可以直接關閉預覽，或調整提示詞後重試。"
				/>
				<div v-for="(role, roleIndex) in validDynamicPreviewRoles" :key="role.name" class="role-block">
					<el-input
						v-if="isPreviewEditing(buildPreviewEditKey('dynamic-role', roleIndex, 'name'))"
						v-model="role.name"
						size="small"
						class="preview-entity-name-input"
						@blur="deactivatePreviewEdit(buildPreviewEditKey('dynamic-role', roleIndex, 'name'))"
					/>
					<div
						v-else
						class="preview-read-field preview-read-field--title"
						@click="activatePreviewEdit(buildPreviewEditKey('dynamic-role', roleIndex, 'name'))"
					>
						{{ formatPreviewDisplayValue(role.name) }}
					</div>
					<div v-for="(items, catKey) in role.dynamic_info" :key="String(catKey)" class="cat-block">
						<div class="cat-title">{{ formatCategory(catKey) }}</div>
						<el-table :data="items as any[]" size="small" border class="preview-table">
							<el-table-column prop="id" label="ID" width="60" />
							<el-table-column label="信息" min-width="360">
								<template #default="scope">
									<el-input
										v-if="isPreviewEditing(buildPreviewEditKey('dynamic-role', roleIndex, String(catKey), scope.$index, 'info'))"
										v-model="scope.row.info"
										type="textarea"
										:autosize="compactTextareaAutosize"
										@blur="deactivatePreviewEdit(buildPreviewEditKey('dynamic-role', roleIndex, String(catKey), scope.$index, 'info'))"
									/>
									<div
										v-else
										class="preview-read-field preview-read-field--multiline"
										@click="activatePreviewEdit(buildPreviewEditKey('dynamic-role', roleIndex, String(catKey), scope.$index, 'info'))"
									>
										<div
											v-for="(line, lineIndex) in formatPreviewDisplayLines(scope.row.info)"
											:key="lineIndex"
											class="preview-read-field__line"
										>
											{{ line }}
										</div>
									</div>
								</template>
							</el-table-column>
							<el-table-column label="操作" width="90">
								<template #default="scope">
									<el-button type="danger" text size="small" @click="removePreviewItem(role.name, String(catKey), scope.$index)">刪除</el-button>
								</template>
							</el-table-column>
						</el-table>
					</div>
				</div>
				<el-alert
					class="preview-bottom-tip"
					type="info"
					:closable="false"
					show-icon
					:title="previewConfirmReminder"
				/>
			</div>
			<template #footer>
				<el-button @click="previewDialogVisible=false">取消</el-button>
				<el-button type="primary" :loading="dynamicPreviewApplying" @click="confirmApplyUpdates">確認</el-button>
			</template>
		</el-dialog>

		<el-dialog v-model="relationsPreviewVisible" title="關係入圖預覽" width="70%">
			<template #header>
				<div class="preview-dialog-header">
					<div class="preview-dialog-header__title">關係入圖預覽</div>
				</div>
			</template>
			<div v-if="relationsPreview">
				<div v-if="relationMissingCards.length" class="missing-card-panel">
					<el-alert
						type="warning"
						:closable="false"
						show-icon
						title="以下關係端點在卡片樹中還沒有對應實體卡。確認入圖仍可繼續；如果你希望先補齊實體卡，可以先手動新建，再回到當前預覽繼續確認。"
					/>
					<div class="missing-card-list">
						<div v-for="item in relationMissingCards" :key="item.key" class="missing-card-item">
							<span>{{ item.title }} · {{ item.cardTypeName }}</span>
							<el-button size="small" type="primary" plain @click="openCreateCardFromPreview(item)">
								新增{{ item.cardTypeName }}
							</el-button>
						</div>
					</div>
				</div>
				<el-empty
					v-if="isRelationsPreviewEmpty"
					description="本次未提取到可入圖的關係信息。你可以直接關閉預覽，或調整模型參數後重試。"
				/>
				<div style="margin-top: 16px" v-if="validRelationPreviewItems.length">
					<h4>關係項</h4>
					<el-table :data="validRelationPreviewItems" size="small" border class="preview-table">
						<el-table-column label="A" width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('relation', $index, 'a'))"
									v-model="row.a"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('relation', $index, 'a'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('relation', $index, 'a'))"
								>
									{{ formatPreviewDisplayValue(row.a) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="關係" width="140">
							<template #default="{ row, $index }">
								<el-select
									v-if="isPreviewEditing(buildPreviewEditKey('relation', $index, 'kind'))"
									v-model="row.kind"
									size="small"
									style="width: 100%"
									@change="deactivatePreviewEdit(buildPreviewEditKey('relation', $index, 'kind'))"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('relation', $index, 'kind'))"
								>
									<el-option v-for="kind in RELATION_KIND_OPTIONS" :key="kind" :label="kind" :value="kind" />
								</el-select>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('relation', $index, 'kind'))"
								>
									{{ formatPreviewDisplayValue(row.kind, '點擊選擇') }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="B" width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('relation', $index, 'b'))"
									v-model="row.b"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('relation', $index, 'b'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('relation', $index, 'b'))"
								>
									{{ formatPreviewDisplayValue(row.b) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="說明" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('relation', $index, 'description'))"
									v-model="row.description"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('relation', $index, 'description'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('relation', $index, 'description'))"
								>
									<div
										v-for="(line, lineIndex) in formatPreviewDisplayLines(row.description)"
										:key="lineIndex"
										class="preview-read-field__line"
									>
										{{ line }}
									</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="證據">
							<template #default="{ row, $index }">
								<div
									v-if="!isPreviewEditing(buildPreviewEditKey('relation', $index, 'evidence'))"
									class="preview-read-field preview-read-field--multiline preview-evidence-summary"
									@click="activatePreviewEdit(buildPreviewEditKey('relation', $index, 'evidence'))"
								>
									<div class="preview-read-field__line">A 對 B 稱呼：{{ formatPreviewDisplayValue(row.a_to_b_addressing, '未填寫') }}</div>
									<div class="preview-read-field__line">B 對 A 稱呼：{{ formatPreviewDisplayValue(row.b_to_a_addressing, '未填寫') }}</div>
									<div
										v-for="(line, lineIndex) in formatPreviewDisplayLines(row.recent_dialogues, '點擊補充近期對白')"
										:key="`dialogue-${lineIndex}`"
										class="preview-read-field__line"
									>
										對白：{{ line }}
									</div>
									<div
										v-for="(line, lineIndex) in formatEventSummaryDisplayLines(row.recent_event_summaries, '點擊補充近期事件摘要')"
										:key="`event-${lineIndex}`"
										class="preview-read-field__line"
									>
										事件：{{ line }}
									</div>
								</div>
								<div
									v-else
									class="preview-evidence-editor"
								>
									<el-input
										v-model="row.a_to_b_addressing"
										size="small"
										placeholder="A 對 B 的稱呼"
									/>
									<el-input
										v-model="row.b_to_a_addressing"
										size="small"
										placeholder="B 對 A 的稱呼"
									/>
									<el-input
										:model-value="joinPreviewLines(row.recent_dialogues)"
										type="textarea"
										:autosize="compactTextareaAutosize"
										placeholder="每行一條對話樣例"
										@update:model-value="value => updatePreviewStringArray(row, 'recent_dialogues', value)"
									/>
									<el-input
										:model-value="joinEventSummaryLines(row.recent_event_summaries)"
										type="textarea"
										:autosize="compactTextareaAutosize"
										placeholder="每行一條近期事件摘要"
										@update:model-value="value => updateRelationEventSummaries(row, value)"
									/>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="操作" width="90">
							<template #default="{ row, $index }">
								<el-button type="danger" text size="small" @click="removeRelationPreviewItem($index, row)">刪除</el-button>
							</template>
						</el-table-column>
					</el-table>
				</div>
				<el-alert
					class="preview-bottom-tip"
					type="info"
					:closable="false"
					show-icon
					:title="previewConfirmReminder"
				/>
			</div>
			<template #footer>
				<el-button @click="relationsPreviewVisible=false">取消</el-button>
				<el-button type="primary" :loading="relationsPreviewApplying" @click="confirmIngestRelationsFromPreview">確認</el-button>
			</template>
		</el-dialog>

		<el-dialog v-model="memoryPreviewVisible" :title="memoryPreviewTitleResolved" width="78%">
			<template #header>
				<div class="preview-dialog-header">
					<div class="preview-dialog-header__title">{{ memoryPreviewTitleResolved }}</div>
				</div>
			</template>
			<div v-if="memoryPreviewData">
				<div v-if="memoryMissingCards.length" class="missing-card-panel">
					<el-alert
						type="warning"
						:closable="false"
						show-icon
						title="以下實體在本章正文中被提取到了，但當前項目裏還沒有對應卡片。確認寫入時這些實體會被跳過；如果需要，請先手動新建對應卡片，再回到當前預覽繼續確認。"
					/>
					<div class="missing-card-list">
						<div v-for="item in memoryMissingCards" :key="item.key" class="missing-card-item">
							<span>{{ item.title }} · {{ item.cardTypeName }}</span>
							<el-button size="small" type="primary" plain @click="openCreateCardFromPreview(item)">
								新增{{ item.cardTypeName }}
							</el-button>
						</div>
					</div>
				</div>
				<div v-if="memoryParticipantReviewNotices.length" class="participant-review-panel">
					<el-alert
						type="info"
						:closable="false"
						show-icon
						title="以下實體仍在本章參與實體裏，但這次提取結果中沒有出現。若確認它們已不再參與本章節，可將其移出本章參與實體；如果只是本章沒有新的狀態變化，也可以忽略。"
					/>
					<div class="missing-card-list">
						<div v-for="item in memoryParticipantReviewNotices" :key="item.key" class="missing-card-item">
							<span>{{ item.title }} · {{ item.cardTypeName }}</span>
							<el-button size="small" type="warning" plain @click="removeParticipantFromCurrentChapter(item)">
								移出本章參與實體
							</el-button>
						</div>
					</div>
				</div>
				<el-empty
					v-if="isMemoryPreviewEmpty"
					:description="memoryPreviewEmptyDescription"
				/>
				<div v-if="memoryPreviewExtractorCode === 'scene_state' && validScenePreviewItems.length" style="margin-top: 16px">
					<h4>場景狀態預覽</h4>
					<el-table :data="validScenePreviewItems" size="small" border class="preview-table">
						<el-table-column label="名稱" width="150">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('scene', $index, 'name'))"
									v-model="row.name"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('scene', $index, 'name'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('scene', $index, 'name'))"
								>
									{{ formatPreviewDisplayValue(row.name) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="簡介" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('scene', $index, 'description'))"
									v-model="row.description"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('scene', $index, 'description'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('scene', $index, 'description'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.description)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="劇情作用" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('scene', $index, 'function_in_story'))"
									v-model="row.function_in_story"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('scene', $index, 'function_in_story'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('scene', $index, 'function_in_story'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.function_in_story)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="當前狀態" min-width="220">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('scene', $index, 'dynamic_state'))"
									:model-value="joinPreviewLines(row.dynamic_state)"
									type="textarea"
									:autosize="compactTextareaAutosize"
									placeholder="每行一條當前狀態"
									@update:model-value="value => updatePreviewStringArray(row, 'dynamic_state', value)"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('scene', $index, 'dynamic_state'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('scene', $index, 'dynamic_state'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.dynamic_state)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="操作" width="90">
							<template #default="{ row, $index }">
								<el-button type="danger" text size="small" @click="removeMemoryCardPreviewItem('scenes', $index, row)">刪除</el-button>
							</template>
						</el-table-column>
					</el-table>
				</div>

				<div v-if="memoryPreviewExtractorCode === 'organization_state' && validOrganizationPreviewItems.length" style="margin-top: 16px">
					<h4>組織狀態預覽</h4>
					<el-table :data="validOrganizationPreviewItems" size="small" border class="preview-table">
						<el-table-column label="名稱" width="150">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('organization', $index, 'name'))"
									v-model="row.name"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('organization', $index, 'name'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('organization', $index, 'name'))"
								>
									{{ formatPreviewDisplayValue(row.name) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="簡介" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('organization', $index, 'description'))"
									v-model="row.description"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('organization', $index, 'description'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('organization', $index, 'description'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.description)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="影響力" min-width="160">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('organization', $index, 'influence'))"
									v-model="row.influence"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('organization', $index, 'influence'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('organization', $index, 'influence'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.influence)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="對外關係" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('organization', $index, 'relationship'))"
									:model-value="joinPreviewLines(row.relationship)"
									type="textarea"
									:autosize="compactTextareaAutosize"
									placeholder="每行一條對外關係"
									@update:model-value="value => updatePreviewStringArray(row, 'relationship', value)"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('organization', $index, 'relationship'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('organization', $index, 'relationship'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.relationship)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="當前狀態" min-width="220">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('organization', $index, 'dynamic_state'))"
									:model-value="joinPreviewLines(row.dynamic_state)"
									type="textarea"
									:autosize="compactTextareaAutosize"
									placeholder="每行一條當前狀態"
									@update:model-value="value => updatePreviewStringArray(row, 'dynamic_state', value)"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('organization', $index, 'dynamic_state'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('organization', $index, 'dynamic_state'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.dynamic_state)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="操作" width="90">
							<template #default="{ row, $index }">
								<el-button type="danger" text size="small" @click="removeMemoryCardPreviewItem('organizations', $index, row)">刪除</el-button>
							</template>
						</el-table-column>
					</el-table>
				</div>

				<div v-if="memoryPreviewExtractorCode === 'item_state' && validItemPreviewItems.length" style="margin-top: 16px">
					<h4>物品狀態預覽</h4>
					<el-table :data="validItemPreviewItems" size="small" border class="preview-table">
						<el-table-column label="名稱" width="150">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'name'))"
									v-model="row.name"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'name'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'name'))"
								>
									{{ formatPreviewDisplayValue(row.name) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="類別" width="120">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'category'))"
									v-model="row.category"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'category'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'category'))"
								>
									{{ formatPreviewDisplayValue(row.category) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="簡介" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'description'))"
									v-model="row.description"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'description'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'description'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.description)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="歸屬提示" width="140">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'owner_hint'))"
									v-model="row.owner_hint"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'owner_hint'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'owner_hint'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.owner_hint)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="當前狀態" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'current_state'))"
									v-model="row.current_state"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'current_state'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'current_state'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.current_state)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="作用/效果" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'power_or_effect'))"
									v-model="row.power_or_effect"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'power_or_effect'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'power_or_effect'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.power_or_effect)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="限制" min-width="160">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'constraints'))"
									v-model="row.constraints"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'constraints'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'constraints'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.constraints)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="重要事件" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('item', $index, 'important_events'))"
									:model-value="joinPreviewLines(row.important_events)"
									type="textarea"
									:autosize="compactTextareaAutosize"
									placeholder="每行一條重要事件"
									@update:model-value="value => updatePreviewStringArray(row, 'important_events', value)"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('item', $index, 'important_events'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('item', $index, 'important_events'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.important_events)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="操作" width="90">
							<template #default="{ row, $index }">
								<el-button type="danger" text size="small" @click="removeMemoryCardPreviewItem('items', $index, row)">刪除</el-button>
							</template>
						</el-table-column>
					</el-table>
				</div>

				<div v-if="memoryPreviewExtractorCode === 'concept_state' && validConceptPreviewItems.length" style="margin-top: 16px">
					<h4>概念掌握預覽</h4>
					<el-table :data="validConceptPreviewItems" size="small" border class="preview-table">
						<el-table-column label="名稱" width="150">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'name'))"
									v-model="row.name"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'name'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'name'))"
								>
									{{ formatPreviewDisplayValue(row.name) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="類別" width="120">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'category'))"
									v-model="row.category"
									size="small"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'category'))"
								/>
								<div
									v-else
									class="preview-read-field"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'category'))"
								>
									{{ formatPreviewDisplayValue(row.category) }}
								</div>
							</template>
						</el-table-column>
						<el-table-column label="簡介" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'description'))"
									v-model="row.description"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'description'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'description'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.description)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="規則定義" min-width="220">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'rule_definition'))"
									v-model="row.rule_definition"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'rule_definition'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'rule_definition'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.rule_definition)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="代價" min-width="160">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'cost'))"
									v-model="row.cost"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'cost'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'cost'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.cost)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="掌握提示" min-width="180">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'mastery_hint'))"
									v-model="row.mastery_hint"
									type="textarea"
									:autosize="compactTextareaAutosize"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'mastery_hint'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'mastery_hint'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.mastery_hint)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="已知掌握者" min-width="160">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'known_by'))"
									:model-value="joinPreviewLines(row.known_by)"
									type="textarea"
									:autosize="compactTextareaAutosize"
									placeholder="每行一個已知掌握者"
									@update:model-value="value => updatePreviewStringArray(row, 'known_by', value)"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'known_by'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'known_by'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.known_by)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="剋制關係" min-width="160">
							<template #default="{ row, $index }">
								<el-input
									v-if="isPreviewEditing(buildPreviewEditKey('concept', $index, 'counter_relations'))"
									:model-value="joinPreviewLines(row.counter_relations)"
									type="textarea"
									:autosize="compactTextareaAutosize"
									placeholder="每行一條剋制關係"
									@update:model-value="value => updatePreviewStringArray(row, 'counter_relations', value)"
									@blur="deactivatePreviewEdit(buildPreviewEditKey('concept', $index, 'counter_relations'))"
								/>
								<div
									v-else
									class="preview-read-field preview-read-field--multiline"
									@click="activatePreviewEdit(buildPreviewEditKey('concept', $index, 'counter_relations'))"
								>
									<div v-for="(line, lineIndex) in formatPreviewDisplayLines(row.counter_relations)" :key="lineIndex" class="preview-read-field__line">{{ line }}</div>
								</div>
							</template>
						</el-table-column>
						<el-table-column label="操作" width="90">
							<template #default="{ row, $index }">
								<el-button type="danger" text size="small" @click="removeMemoryCardPreviewItem('concepts', $index, row)">刪除</el-button>
							</template>
						</el-table-column>
					</el-table>
				</div>
				<el-alert
					class="preview-bottom-tip"
					type="info"
					:closable="false"
					show-icon
					:title="previewConfirmReminder"
				/>
			</div>
			<template #footer>
				<el-button @click="closeMemoryPreview">取消</el-button>
				<el-button type="primary" :loading="memoryPreviewApplying" @click="applyMemoryPreviewConfirm">確認</el-button>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import SimpleMarkdown from '../common/SimpleMarkdown.vue'
import { useCardStore } from '@renderer/stores/useCardStore'
import { useProjectStore } from '@renderer/stores/useProjectStore'
import { usePerCardAISettingsStore, type PerCardAIParams } from '@renderer/stores/usePerCardAISettingsStore'
import { useEditorStore, type ChapterExtractRunOptions } from '@renderer/stores/useEditorStore'
import { useAppStore } from '@renderer/stores/useAppStore'
import { useAssistantStore } from '@renderer/stores/useAssistantStore'
import { useAssistantPreferences } from '@renderer/composables/useAssistantPreferences'
import { updateCardRaw, type CardRead, type CardUpdate } from '@renderer/api/cards'
import { generateContinuationStreaming, type ContinuationRequest, getAIConfigOptions, type AIConfigOptions } from '@renderer/api/ai'
import { runReview, upsertReviewCard, type QualityGate, type ReviewDraftResult, type ReviewRunRequest } from '@renderer/api/chapterReviews'
import { getCardAIParams, updateCardAIParams, applyCardAIParamsToType } from '@renderer/api/setting'
import {
	extractDynamicInfoOnly,
	updateDynamicInfoOnly,
	type UpdateDynamicInfoOutput,
	extractRelationsOnly,
	ingestRelationsFromPreview,
	type RelationExtractionOutput,
	extractMemoryPreview,
	applyMemoryPreview,
	type ExtractPreviewResponse,
} from '@renderer/api/memory'
import { ArrowDown, Document, MagicStick, CircleClose, Connection, List, Timer, Select, Loading } from '@element-plus/icons-vue'
import AIPerCardParams from '../common/AIPerCardParams.vue'
import ContinuationBudgetDialog, { type ContinuationWordControlMode } from './dialogs/ContinuationBudgetDialog.vue'
import { resolveTemplate } from '@renderer/services/contextResolver'
import { getCardContextTemplates, getContextTemplateByKind, normalizeContextTemplateKind, type ContextTemplateKind, type ContextTemplates } from '@renderer/services/contextSlots'
import { notifyTaskDone } from '@renderer/utils/taskDoneNotifier'

import { EditorState, StateEffect, StateField } from '@codemirror/state'
import { EditorView, keymap, Decoration, DecorationSet, lineNumbers } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, insertNewline } from '@codemirror/commands'

const props = defineProps<{
	card: CardRead
	chapter?: any
	prefetched?: any | null
	contextParams?: { project_id?: number; volume_number?: number; chapter_number?: number; participants?: string[]; extra_context_fn?: Function }
	contextTemplates?: ContextTemplates
	generationContextKind?: ContextTemplateKind
	reviewContextKind?: ContextTemplateKind
}>()

const previewConfirmReminder =
	'若信息提取有誤，如卡片名稱不準確，請手動編輯調整後再確認，避免數據回寫對應卡片失敗'

const emit = defineEmits<{
	(e: 'update:chapter', value: any): void
	(e: 'save'): void
	(e: 'switch-tab', tab: string): void
	(e: 'update:dirty', value: boolean): void
	(e: 'update:generation-context-kind', value: ContextTemplateKind): void
	(e: 'update:review-context-kind', value: ContextTemplateKind): void
}>()

const cardStore = useCardStore()
const projectStore = useProjectStore()
const perCardStore = usePerCardAISettingsStore()
const editorStore = useEditorStore()
const appStore = useAppStore()
const assistantStore = useAssistantStore()
const assistantPrefs = useAssistantPreferences()
const { cards } = storeToRefs(cardStore)
const isDarkMode = computed(() => appStore.isDarkMode)

const ready = ref(false)
const cmRoot = ref<HTMLElement | null>(null)
const titleElement = ref<HTMLElement | null>(null)
let view: EditorView | null = null

// 自定義高亮系統
type HighlightEffectPayload =
	| { mode: 'single'; from: number; to: number }
	| { mode: 'compare'; originalFrom: number; originalTo: number; previewFrom: number; previewTo: number }
	| null

const setHighlightEffect = StateEffect.define<HighlightEffectPayload>()

const highlightField = StateField.define<DecorationSet>({
	create() {
		return Decoration.none
	},
	update(highlights, tr) {
		highlights = highlights.map(tr.changes)
		for (const effect of tr.effects) {
			if (effect.is(setHighlightEffect)) {
				if (effect.value === null) {
					highlights = Decoration.none
				} else if (effect.value.mode === 'single') {
					const decoration = Decoration.mark({
						class: 'cm-ai-highlight'
					}).range(effect.value.from, effect.value.to)
					highlights = Decoration.set([decoration])
				} else {
					const originalDecoration = Decoration.mark({
						class: 'cm-ai-original-highlight'
					}).range(effect.value.originalFrom, effect.value.originalTo)
					const previewDecoration = Decoration.mark({
						class: 'cm-ai-preview-highlight'
					}).range(effect.value.previewFrom, effect.value.previewTo)
					highlights = Decoration.set([originalDecoration, previewDecoration])
				}
			}
		}
		return highlights
	},
	provide: f => EditorView.decorations.from(f)
})

const localCard = reactive({
	...props.card,
	content: {
		content: typeof (props.chapter as any)?.content === 'string'
			? (props.chapter as any).content
			: (typeof (props.card.content as any)?.content === 'string' ? (props.card.content as any).content : ''),
		word_count: typeof (props.chapter as any)?.content === 'string' ? ((props.chapter as any).content as string).length : (typeof (props.card.content as any)?.word_count === 'number' ? (props.card.content as any).word_count : 0),
		volume_number: (props.chapter as any)?.volume_number ?? ((props.contextParams as any)?.volume_number ?? ((props.card.content as any)?.volume_number ?? undefined)),
		chapter_number: (props.chapter as any)?.chapter_number ?? ((props.contextParams as any)?.chapter_number ?? ((props.card.content as any)?.chapter_number ?? undefined)),
		title: (props.chapter as any)?.title ?? ((props.card.content as any)?.title ?? props.card.title ?? ''),
		entity_list: (props.chapter as any)?.entity_list ?? ((props.card.content as any)?.entity_list ?? []),
		...(props.card.content as any || {})
	}
})

const generationContextKindValue = computed(() => normalizeContextTemplateKind(props.generationContextKind, 'generation'))
const reviewContextKindValue = computed(() => normalizeContextTemplateKind(props.reviewContextKind, 'review'))

function getResolvedContext(kind: ContextTemplateKind | string, fallbackKind: ContextTemplateKind) {
	const currentCardWithContent = {
		...props.card,
		content: {
			...(props.card.content as any || {}),
			...(localCard.content as any || {}),
		},
	}
	const template = getContextTemplateByKind(
		props.card,
		props.contextTemplates || getCardContextTemplates(props.card),
		kind,
		fallbackKind
	)
	return template
		? resolveTemplate({
			template,
			cards: cards.value,
			currentCard: currentCardWithContent as any,
		})
		: ''
}

function handleGenerationContextKindChange(value: ContextTemplateKind | string) {
	emit('update:generation-context-kind', normalizeContextTemplateKind(value, 'generation'))
}

function handleReviewContextKindChange(value: ContextTemplateKind | string) {
	emit('update:review-context-kind', normalizeContextTemplateKind(value, 'review'))
}

// 每卡片參數
const editingParams = ref<PerCardAIParams>({})
const aiOptions = ref<AIConfigOptions | null>(null)
async function loadAIOptions() { try { aiOptions.value = await getAIConfigOptions() } catch {} }
const perCardParams = computed(() => perCardStore.getByCardId(props.card.id))
const selectedModelName = computed(() => {
	try {
		const id = (perCardParams.value || editingParams.value)?.llm_config_id
		const list = aiOptions.value?.llm_configs || []
		const found = list.find(m => m.id === id)
		return found?.display_name || (id != null ? String(id) : '')
	} catch { return '' }
})
const paramSummary = computed(() => {
	const p = perCardParams.value || editingParams.value
	const model = selectedModelName.value ? `模型:${selectedModelName.value}` : '模型:未設'
	const prompt = p?.prompt_name ? `任務:${p.prompt_name}` : '任務:未設'
	const t = p?.temperature != null ? `溫度:${p.temperature}` : ''
	const m = p?.max_tokens != null ? `max_tokens:${p.max_tokens}` : ''
	return [model, prompt, t, m].filter(Boolean).join(' · ')
})

watch(() => props.card, async (newCard) => {
	if (!newCard) return
	await loadAIOptions()
	// 優先讀取後端"有效參數"（類型默認或實例覆蓋）
	try {
		const resp = await getCardAIParams(newCard.id)
		const eff = (resp as any)?.effective_params
		if (eff && Object.keys(eff).length) {
			editingParams.value = { ...eff }
			perCardStore.setForCard(newCard.id, { ...eff })
			return
		}
	} catch {}
	// 回退：使用本地存儲或預設
	const saved = perCardStore.getByCardId(newCard.id)
	if (saved) editingParams.value = { ...saved }
	else {
		const preset = getPresetForType(newCard.card_type?.name) || {}
		if (!preset.llm_config_id) { const first = aiOptions.value?.llm_configs?.[0]; if (first) preset.llm_config_id = first.id }
		editingParams.value = { ...preset }
		perCardStore.setForCard(newCard.id, editingParams.value)
	}
}, { immediate: true })

// 監聽卡片內容變化（如靈感助手修改後），同步到編輯器
watch(() => props.card?.content, (newContent) => {
	if (!newContent || !view) return

	try {
		const newText = typeof (newContent as any)?.content === 'string'
			? (newContent as any).content
			: ''
		const currentText = getText()
		const currentContent = localCard.content || {}
		const syncedContent = {
			...currentContent,
			...(newContent as any),
			content: currentText,
			word_count: typeof (newContent as any)?.word_count === 'number'
				? (newContent as any).word_count
				: currentText.length,
		}

		// 只有當內容真的不同，且不是由當前編輯器觸發的保存時，才更新
		// （通過比較 originalContent 判斷：如果相同說明是外部修改）
		if (newText !== currentText && newText !== originalContent.value) {
			console.log('🔄 [CodeMirror] 檢測到外部內容更新，同步到編輯器')

			// 更新編輯器內容
			setText(newText)

			// 更新 localCard
			localCard.content = {
				...syncedContent,
				content: newText,
				word_count: newText.length
			}

			// 更新原始內容引用（避免觸發 dirty）
			originalContent.value = newText
			isDirty.value = false
			emit('update:dirty', false)

			// 更新字數
			wordCount.value = computeWordCount(newText)

			console.log('✅ [CodeMirror] 編輯器內容已同步')
			return
		}

		// 即使正文文本未變化，也要同步 entity_list 等字段，保證預覽始終讀取最新章節掛載實體。
		localCard.content = syncedContent
	} catch (e) {
		console.error('❌ [CodeMirror] 同步內容失敗:', e)
	}
}, { deep: true })

function applyAndSavePerCardParams() {
	try { perCardStore.setForCard(props.card.id, { ...editingParams.value }); ElMessage.success('已保存到本卡片設置') } catch { ElMessage.error('保存失敗') }
}
function resetToPreset() {
	const preset = getPresetForType(props.card.card_type?.name)
	editingParams.value = { ...(preset || {}) }
	perCardStore.setForCard(props.card.id, editingParams.value)
}
function getPresetForType(typeName?: string) : PerCardAIParams | undefined {
	const map: Record<string, PerCardAIParams> = {
		'章節大綱': { prompt_name: '章節大綱', llm_config_id: 1, temperature: 0.6, max_tokens: 4096, timeout: 60 },
		'內容生成': { prompt_name: '內容生成', llm_config_id: 1, temperature: 0.7, max_tokens: 8192, timeout: 60 },
	}
	return map[typeName || '']
}

watch(() => props.chapter, (ch) => {
	if (!ch) return
	const c: any = ch
	const text = typeof c.content === 'string' ? c.content : (localCard.content as any)?.content || ''
	localCard.content = {
		...(localCard.content || {}),
		content: text,
		word_count: typeof c.content === 'string' ? c.content.length : (localCard.content as any)?.word_count || 0,
		volume_number: c.volume_number ?? (localCard.content as any)?.volume_number,
		chapter_number: c.chapter_number ?? (localCard.content as any)?.chapter_number,
		title: c.title ?? (localCard.content as any)?.title ?? props.card.title,
		entity_list: Array.isArray(c.entity_list) ? c.entity_list : ((localCard.content as any)?.entity_list || []),
	}
	if (view && getText() !== text) setText(text)
}, { deep: true })

function computeWordCount(text: string): number {
	return (text || '').replace(/\s+/g, '').length
}

const wordCount = ref(0)
const aiLoading = ref(false)
let streamHandle: { cancel: () => void } | null = null
let aiStreamCanceled = false
const reviewAbortController = ref<AbortController | null>(null)
const canInterruptAiTask = computed(() => aiLoading.value || reviewLoading.value || Boolean(reviewAbortController.value))

// 右鍵菜單狀態
const contextMenu = reactive({
	visible: false,
	expanded: false,
	x: 0,
	y: 0,
	userRequirement: '',
	selectedText: null as {
		text: string
		from: number
		to: number
		startLine: number
		endLine: number
		numberedText: string
		snapshotHash: string
	} | null
})

const pendingAiEdit = ref<{
	originalFrom: number
	originalTo: number
	originalText: string
	previewFrom: number
	previewTo: number
	generating: boolean
	source?: string
	patchId?: number
} | null>(null)

let allowPendingPreviewDocMutation = false
let lastPendingPreviewWarnAt = 0

function runWithPendingPreviewMutation<T>(fn: () => T): T {
	allowPendingPreviewDocMutation = true
	try {
		return fn()
	} finally {
		allowPendingPreviewDocMutation = false
	}
}

function ensureNoPendingAiEdit(): boolean {
	if (pendingAiEdit.value) {
		ElMessage.warning('請先接受或拒絕當前替換建議')
		return false
	}
	return true
}

// 高亮管理
const currentHighlight = ref<{ from: number; to: number } | { mode: 'compare' } | null>(null)

// 設置高亮
function setHighlight(from: number, to: number) {
	if (!view) return
	// CodeMirror 不允許空範圍的 decoration
	if (from >= to) {
		console.log('⚠️ [Highlight] 跳過空範圍高亮:', { from, to })
		return
	}
	currentHighlight.value = { from, to }
	view.dispatch({
		effects: setHighlightEffect.of({ mode: 'single', from, to })
	})
	console.log('✨ [Highlight] 設置高亮:', { from, to })
}

// 清除高亮
function clearHighlight() {
	if (!view) return
	currentHighlight.value = null
	view.dispatch({
		effects: setHighlightEffect.of(null)
	})
	console.log('🧹 [Highlight] 清除高亮')
}

// 更新高亮範圍（用於 AI 輸出時）
function updateHighlight(from: number, to: number) {
	if (!view) return
	// CodeMirror 不允許空範圍的 decoration
	if (from >= to) {
		return
	}
	currentHighlight.value = { from, to }
	view.dispatch({
		effects: setHighlightEffect.of({ mode: 'single', from, to })
	})
}

function setCompareHighlight(originalFrom: number, originalTo: number, previewFrom: number, previewTo: number) {
	if (!view) return
	if (originalFrom >= originalTo || previewFrom >= previewTo) return
	currentHighlight.value = { mode: 'compare' }
	view.dispatch({
		effects: setHighlightEffect.of({
			mode: 'compare',
			originalFrom,
			originalTo,
			previewFrom,
			previewTo
		})
	})
}

// 跟蹤原始內容以檢測dirty狀態
const originalContent = ref<string>('')
const isDirty = ref(false)
const reviewLoading = ref(false)
const reviewDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const previewData = ref<UpdateDynamicInfoOutput | null>(null)
const relationsPreviewVisible = ref(false)
const relationsPreview = ref<RelationExtractionOutput | null>(null)
const memoryPreviewVisible = ref(false)
type MemoryExtractorCode = 'scene_state' | 'organization_state' | 'item_state' | 'concept_state'
const memoryPreviewExtractorCode = ref<MemoryExtractorCode | ''>('')
const memoryPreviewData = ref<ExtractPreviewResponse['preview_data'] | null>(null)
watch([previewDialogVisible, relationsPreviewVisible, memoryPreviewVisible], ([dynamicOpen, relationOpen, memoryOpen]) => {
	if (!dynamicOpen && !relationOpen && !memoryOpen) {
		deactivatePreviewEdit()
	}
})
type ManagedCardTypeName = '角色卡' | '場景卡' | '組織卡' | '物品卡' | '概念卡'
type ManagedEntityType = 'character' | 'scene' | 'organization' | 'item' | 'concept'
interface MissingCardNotice {
	key: string
	title: string
	cardTypeName: ManagedCardTypeName
	entityType: ManagedEntityType
}
interface ParticipantReviewNotice {
	key: string
	title: string
	cardTypeName: ManagedCardTypeName
	entityType: ManagedEntityType
}
const ENTITY_TYPE_TO_CARD_TYPE_NAME: Record<ManagedEntityType, ManagedCardTypeName> = {
	character: '角色卡',
	scene: '場景卡',
	organization: '組織卡',
	item: '物品卡',
	concept: '概念卡',
}
const RELATION_KIND_OPTIONS = [
	'同盟', '隊友', '同門', '敵對', '親屬', '師徒', '對手', '夥伴', '上級', '下屬', '指導',
	'隸屬', '成員', '領導', '創立', '擁有', '使用', '修煉', '領悟', '承載', '映射',
	'控制', '位於', '影響', '剋制', '關於', '其他',
]
const reviewText = ref('')
const reviewDraft = ref<ReviewDraftResult | null>(null)
const reviewCardSaving = ref(false)
const dynamicPreviewApplying = ref(false)
const relationsPreviewApplying = ref(false)
const memoryPreviewApplying = ref(false)
const continuationDialogVisible = ref(false)
const continuationDialogState = reactive<{
	targetWordCount: number
	wordControlMode: ContinuationWordControlMode
	guidance: string
}>({
	targetWordCount: 3000,
	wordControlMode: 'balanced',
	guidance: '',
})

const memoryPreviewTitleResolved = computed(() => {
	switch (memoryPreviewExtractorCode.value) {
		case 'scene_state':
			return '場景狀態預覽'
		case 'organization_state':
			return '組織狀態預覽'
		case 'item_state':
			return '物品狀態預覽'
		case 'concept_state':
			return '概念掌握預覽'
		default:
			return '記憶預覽'
	}
})

function hasMeaningfulText(value: unknown): boolean {
	return String(value || '').trim().length > 0
}

function hasMeaningfulStringArray(values: unknown): boolean {
	return normalizePreviewLines(values).length > 0
}

function hasMeaningfulRelationPreviewItem(item: any): boolean {
	if (!item || typeof item !== 'object') return false
	return [
		item.a,
		item.kind,
		item.b,
		item.description,
		item.a_to_b_addressing,
		item.b_to_a_addressing,
	].some(hasMeaningfulText)
		|| hasMeaningfulStringArray(item.recent_dialogues)
		|| (Array.isArray(item.recent_event_summaries)
			&& item.recent_event_summaries.some((entry: any) => hasMeaningfulText(entry?.summary)))
}

function hasMeaningfulMemoryPreviewItem(item: any, fields: string[]): boolean {
	if (!item || typeof item !== 'object') return false
	return fields.some(field => {
		const value = item[field]
		if (Array.isArray(value)) return hasMeaningfulStringArray(value)
		return hasMeaningfulText(value)
	})
}

const validRelationPreviewItems = computed(() =>
	(relationsPreview.value?.relations || []).filter(item => hasMeaningfulRelationPreviewItem(item)),
)
const isRelationsPreviewEmpty = computed(() => validRelationPreviewItems.value.length === 0)
const compactTextareaAutosize = { minRows: 1, maxRows: 4 }
const activePreviewEditKey = ref('')

const validDynamicPreviewRoles = computed(() => {
	const roles = previewData.value?.info_list || []
	return roles.filter(role =>
		Object.values(role?.dynamic_info || {}).some(items => Array.isArray(items) && items.length > 0),
	)
})

const isDynamicPreviewEmpty = computed(() => validDynamicPreviewRoles.value.length === 0)

const validScenePreviewItems = computed(() =>
	(memoryPreviewData.value?.scenes || []).filter(item =>
		hasMeaningfulMemoryPreviewItem(item, ['name', 'description', 'function_in_story', 'dynamic_state']),
	),
)

const validOrganizationPreviewItems = computed(() =>
	(memoryPreviewData.value?.organizations || []).filter(item =>
		hasMeaningfulMemoryPreviewItem(item, ['name', 'description', 'influence', 'relationship', 'dynamic_state']),
	),
)

const validItemPreviewItems = computed(() =>
	(memoryPreviewData.value?.items || []).filter(item =>
		hasMeaningfulMemoryPreviewItem(item, [
			'name',
			'category',
			'description',
			'owner_hint',
			'current_state',
			'power_or_effect',
			'constraints',
			'important_events',
		]),
	),
)

const validConceptPreviewItems = computed(() =>
	(memoryPreviewData.value?.concepts || []).filter(item =>
		hasMeaningfulMemoryPreviewItem(item, [
			'name',
			'category',
			'description',
			'rule_definition',
			'cost',
			'mastery_hint',
			'known_by',
			'counter_relations',
		]),
	),
)

const isMemoryPreviewEmpty = computed(() => {
	return !(
		validScenePreviewItems.value.length > 0
		|| validOrganizationPreviewItems.value.length > 0
		|| validItemPreviewItems.value.length > 0
		|| validConceptPreviewItems.value.length > 0
	)
})

const memoryPreviewEmptyDescription = computed(() => {
	switch (memoryPreviewExtractorCode.value) {
		case 'scene_state':
			return '本次未提取到可寫回的場景狀態。你可以直接關閉預覽，或調整提示詞後重試。'
		case 'organization_state':
			return '本次未提取到可寫回的組織狀態。你可以直接關閉預覽，或調整提示詞後重試。'
		case 'item_state':
			return '本次未提取到可寫回的物品狀態。你可以直接關閉預覽，或調整提示詞後重試。'
		case 'concept_state':
			return '本次未提取到可寫回的概念掌握信息。你可以直接關閉預覽，或調整提示詞後重試。'
		default:
			return '本次未提取到可寫回的內容。'
	}
})

function getMemoryExtractorDisplayLabel(extractorCode: MemoryExtractorCode): string {
	switch (extractorCode) {
		case 'scene_state':
			return '場景狀態'
		case 'organization_state':
			return '組織狀態'
		case 'item_state':
			return '物品狀態'
		case 'concept_state':
			return '概念掌握'
		default:
			return '記憶'
	}
}

function buildPreviewEditKey(...parts: Array<string | number | null | undefined>): string {
	return parts
		.map(part => String(part ?? '').trim())
		.filter(Boolean)
		.join('::')
}

function isPreviewEditing(key: string): boolean {
	return activePreviewEditKey.value === key
}

function activatePreviewEdit(key: string) {
	activePreviewEditKey.value = key
}

function deactivatePreviewEdit(key?: string) {
	if (!key || activePreviewEditKey.value === key) {
		activePreviewEditKey.value = ''
	}
}

function splitPreviewLines(value: string): string[] {
	return String(value || '')
		.split(/\r?\n+/)
		.map(line => line.trim())
		.filter(Boolean)
}

function normalizePreviewLines(values: unknown): string[] {
	if (Array.isArray(values)) {
		return values
			.map(item => String(item || '').trim())
			.filter(Boolean)
	}
	const text = String(values || '').trim()
	return text ? [text] : []
}

function joinPreviewLines(values: unknown): string {
	return Array.isArray(values)
		? values.map(item => String(item || '').trim()).filter(Boolean).join('\n')
		: ''
}

function updatePreviewStringArray(target: Record<string, any>, key: string, value: string) {
	target[key] = splitPreviewLines(value)
}

function joinEventSummaryLines(values: unknown): string {
	return Array.isArray(values)
		? values.map(item => String(item?.summary || '').trim()).filter(Boolean).join('\n')
		: ''
}

function formatPreviewDisplayValue(value: unknown, fallback = '點擊修改'): string {
	const text = String(value || '').trim()
	return text || fallback
}

function formatPreviewDisplayLines(values: unknown, fallback = '點擊補充'): string[] {
	const lines = normalizePreviewLines(values)
	return lines.length ? lines : [fallback]
}

function formatEventSummaryDisplayLines(values: unknown, fallback = '點擊補充'): string[] {
	if (Array.isArray(values)) {
		const lines = values
			.map(item => String(item?.summary || '').trim())
			.filter(Boolean)
		return lines.length ? lines : [fallback]
	}
	return [fallback]
}

function updateRelationEventSummaries(target: Record<string, any>, value: string) {
	const lines = splitPreviewLines(value)
	const previous = Array.isArray(target.recent_event_summaries) ? target.recent_event_summaries : []
	target.recent_event_summaries = lines.map((summary, index) => {
		const oldItem = previous[index]
		return {
			...(oldItem && typeof oldItem === 'object' ? oldItem : {}),
			summary,
		}
	})
}

const activeContinuationConfig = reactive<{
	targetWordCount: number
	wordControlMode: ContinuationWordControlMode
}>({
	targetWordCount: 3000,
	wordControlMode: 'balanced',
})

function isCanceledRequest(error: unknown): boolean {
	const candidate = error as { code?: string; name?: string; message?: string }
	return candidate?.code === 'ERR_CANCELED'
		|| candidate?.name === 'CanceledError'
		|| candidate?.message === 'canceled'
		|| candidate?.message === 'CanceledError'
}

// 字號/行距（默認 16px / 1.8）
const fontSize = ref<number>(16)
const lineHeight = ref<number>(1.8)

// 潤色和擴寫的提示詞列表
const polishPrompts = ref<string[]>([])
const expandPrompts = ref<string[]>([])
const currentPolishPrompt = ref('潤色')
const currentExpandPrompt = ref('擴寫')
const fontSizePx = computed(() => `${fontSize.value}px`)
const lineHeightStr = computed(() => String(lineHeight.value))

const reviewPrompts = ref<string[]>([])
const currentReviewPrompt = ref('章節審核')
type PromptPickerKey = 'polish' | 'expand' | 'review'

const promptPicker = reactive<Record<PromptPickerKey, { visible: boolean; keyword: string }>>({
	polish: { visible: false, keyword: '' },
	expand: { visible: false, keyword: '' },
	review: { visible: false, keyword: '' }
})

function filterPromptsByKeyword(prompts: string[], keyword: string): string[] {
	const normalizedKeyword = keyword.trim().toLowerCase()
	if (!normalizedKeyword) return prompts
	return prompts.filter(prompt => prompt.toLowerCase().includes(normalizedKeyword))
}

const filteredPolishPrompts = computed(() => filterPromptsByKeyword(polishPrompts.value, promptPicker.polish.keyword))
const filteredExpandPrompts = computed(() => filterPromptsByKeyword(expandPrompts.value, promptPicker.expand.keyword))
const filteredReviewPrompts = computed(() => filterPromptsByKeyword(reviewPrompts.value, promptPicker.review.keyword))

function formatCategory(catKey: any) { return String(catKey) }

function formatReviewVerdict(verdict?: QualityGate | null | string): string {
	switch (verdict) {
		case 'pass':
			return '基本通過'
		case 'block':
			return '高風險攔截'
		default:
			return '建議修改'
	}
}

function getReviewVerdictTagType(verdict?: QualityGate | null | string): 'success' | 'warning' | 'danger' {
	switch (verdict) {
		case 'pass':
			return 'success'
		case 'block':
			return 'danger'
		default:
			return 'warning'
	}
}

function setText(text: string) {
	if (!view) return
	view.dispatch({
		changes: { from: 0, to: view.state.doc.length, insert: text || '' }
	})
}

function formatContinuationMode(mode: ContinuationWordControlMode): string {
	if (mode === 'prompt_only') return '提示詞約束'
	return '控制模式'
}

function buildChapterReviewTarget(
	chapterText: string,
	options: {
		title: string
		volumeNumber?: number | null
		chapterNumber?: number | null
		participants?: string[]
	}
): string {
	const lines: string[] = ['【章節信息】']
	lines.push(`標題：${options.title || '未命名章節'}`)
	if (options.volumeNumber != null) lines.push(`卷號：${options.volumeNumber}`)
	if (options.chapterNumber != null) lines.push(`章節號：${options.chapterNumber}`)
	if (options.participants?.length) lines.push(`參與實體：${options.participants.join('、')}`)
	lines.push(`正文字數：${computeWordCount(chapterText)}`)
	lines.push('', '【正文】', chapterText.trim())
	return lines.join('\n').trim()
}

async function handleAiQuickAction(command: 'polish' | 'expand') {
	if (command === 'polish') {
		await executePolish()
		return
	}
	if (command === 'expand') {
		await executeExpand()
	}
}

function computeSnapshotHash(input: string): string {
	let hash = 5381
	for (let index = 0; index < input.length; index += 1) {
		hash = ((hash << 5) + hash) ^ input.charCodeAt(index)
	}
	return `h${(hash >>> 0).toString(16)}`
}

function getSelectionWithLineInfo(): {
	text: string
	from: number
	to: number
	startLine: number
	endLine: number
	numberedText: string
	snapshotHash: string
} | null {
	if (!view) return null
	const { from, to } = view.state.selection.main
	if (from === to) return null
	const text = view.state.doc.sliceString(from, to)
	if (!text.trim()) return null
	const startLine = view.state.doc.lineAt(from).number
	const endLine = view.state.doc.lineAt(Math.max(from, to - 1)).number
	const numberedText = text
		.split('\n')
		.map((line, offset) => `${startLine + offset} | ${line}`)
		.join('\n')
	return {
		text,
		from,
		to,
		startLine,
		endLine,
		numberedText,
		snapshotHash: computeSnapshotHash(view.state.doc.toString()),
	}
}

function resolveContinuationDefaults() {
	let targetWordCount = 3000
	let wordControlMode: ContinuationWordControlMode = 'balanced'
	try {
		const storedTarget = Number(localStorage.getItem(`nf:chapter:continuation-target:${props.card.id}`) || '')
		if (Number.isFinite(storedTarget) && storedTarget > 0) targetWordCount = Math.floor(storedTarget)
		const storedMode = localStorage.getItem(`nf:chapter:continuation-mode:${props.card.id}`)
		if (storedMode === 'prompt_only' || storedMode === 'balanced') {
			wordControlMode = storedMode
		} else if (storedMode === 'strict') {
			wordControlMode = 'balanced'
		}
	} catch {
		// ignore localStorage errors
	}
	return { targetWordCount, wordControlMode, guidance: '' }
}

function getText(): string {
	return view ? view.state.doc.toString() : ''
}

function getSelectedText(): { text: string; from: number; to: number } | null {
	if (!view) return null
	const { from, to } = view.state.selection.main
	if (from === to) return null // 沒有選中內容
	return {
		text: view.state.doc.sliceString(from, to),
		from,
		to
	}
}

function replaceSelectedText(newText: string) {
	if (!view) return
	const { from, to } = view.state.selection.main
	view.dispatch({
		changes: { from, to, insert: newText },
		selection: { anchor: from + newText.length }
	})
}

type EditorTaskDoneKind = 'continue' | 'polish' | 'expand' | 'review'

function notifyEditorTaskDone(kind: EditorTaskDoneKind): void {
	const map = {
		continue: ['續寫完成', '章節續寫已完成。'],
		polish: ['潤色完成', '選區潤色已完成。'],
		expand: ['擴寫完成', '選區擴寫已完成。'],
		review: ['審閱完成', '審閱結果已生成。'],
	} as const
	const [title, body] = map[kind]
	notifyTaskDone({
		title,
		body,
		soundEnabled: assistantPrefs.taskDoneSoundEnabled.value,
		desktopNotificationEnabled: assistantPrefs.taskDoneDesktopNotificationEnabled.value,
	})
}

function appendAtEnd(delta: string) {
	if (!view || !delta) return
	const end = view.state.doc.length
	view.dispatch({
		changes: { from: end, to: end, insert: delta },
		// 滾動到文檔末尾
		effects: EditorView.scrollIntoView(end, { y: "end" })
	})
	// 滾動到底
	try {
		const scroller = (cmRoot.value?.querySelector('.cm-scroller') as HTMLElement) || cmRoot.value
		if (scroller) requestAnimationFrame(() => { scroller.scrollTop = scroller.scrollHeight })
	} catch {}
}


function initEditor() {
	if (!cmRoot.value) return
	const initialText = String((localCard.content as any)?.content || '')

	// 保存原始內容
	originalContent.value = initialText
	isDirty.value = false
	emit('update:dirty', false)

	const customKeymap = [
		{
			key: 'Enter',
			run: (v: EditorView) => {
				// 執行默認的換行
				insertNewline(v)
				return true
			}
		},
		{
			key: 'Mod-s', // Ctrl+S or Cmd+S
			run: (v: EditorView) => {
				handleSave()
				return true
			},
			preventDefault: true
		}
	]

	view = new EditorView({
		parent: cmRoot.value,
		state: EditorState.create({
			doc: initialText,
			extensions: [
				history(),
				keymap.of([...customKeymap, ...defaultKeymap, ...historyKeymap]),
				lineNumbers(),
				EditorView.lineWrapping,
				highlightField,
				// 關鍵：限制編輯器高度由父容器決定，而不是根據內容自動擴展
				EditorView.theme({
					"&": { height: "100%" },
					".cm-scroller": { overflow: "auto" }
				}),
				EditorState.transactionFilter.of((tr) => {
					if (!tr.docChanged) return tr
					if (!pendingAiEdit.value || allowPendingPreviewDocMutation) return tr
					const now = Date.now()
					if (now - lastPendingPreviewWarnAt > 1200) {
						lastPendingPreviewWarnAt = now
						ElMessage.warning('請先接受或拒絕當前替換建議')
					}
					return []
				}),
				// 點擊編輯器時清除高亮
				EditorView.domEventHandlers({
					mousedown: (e, view) => {
						if (pendingAiEdit.value) return false
						if (currentHighlight.value) {
							clearHighlight()
							return false
						}
						return false
					}
				}),
				EditorView.updateListener.of((update) => {
					if (!update.docChanged) return
					const txt = update.state.doc.toString()
					wordCount.value = computeWordCount(txt)

					// 檢測dirty狀態
					const newDirty = txt !== originalContent.value
					if (newDirty !== isDirty.value) {
						isDirty.value = newDirty
						emit('update:dirty', newDirty)
					}

					localCard.content = {
						...(localCard.content || {}),
						content: txt,
						word_count: wordCount.value,
						volume_number: (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number,
						chapter_number: (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number,
						title: (localCard.content as any)?.title ?? localCard.title,
					}
					if (props.chapter) {
						emit('update:chapter', {
							title: (localCard.content as any)?.title ?? localCard.title,
							volume_number: (localCard.content as any)?.volume_number,
							chapter_number: (localCard.content as any)?.chapter_number,
							entity_list: (localCard.content as any)?.entity_list || [],
							content: (localCard.content as any)?.content || ''
						})
					}
				})
			]
		})
	})
	// 初始化字數
	wordCount.value = computeWordCount(getText())
	ready.value = true

	// 添加右鍵菜單監聽器到 CodeMirror 的 DOM 元素
	if (view && cmRoot.value) {
		const editorDom = cmRoot.value.querySelector('.cm-editor') as HTMLElement
		if (editorDom) {
			editorDom.addEventListener('contextmenu', handleEditorContextMenu)
			console.log('✅ [ContextMenu] 右鍵菜單監聽器已添加')
		} else {
			console.warn('⚠️ [ContextMenu] 未找到 .cm-editor 元素')
		}
	}
}


// 加載可用提示詞列表
async function loadPrompts() {
	try {
		const options = await getAIConfigOptions()
		const allPrompts = options?.prompts || []

		// 獲取所有提示詞名稱
		const allPromptNames = allPrompts.map(p => p.name)
		reviewPrompts.value = allPromptNames.length > 0 ? allPromptNames : ['章節審核']

		// 潤色和擴寫都使用所有可用提示詞
		polishPrompts.value = allPromptNames.length > 0 ? allPromptNames : ['潤色']
		expandPrompts.value = allPromptNames.length > 0 ? allPromptNames : ['擴寫']

		// 設置默認選中的提示詞
		if (allPromptNames.includes('潤色')) {
			currentPolishPrompt.value = '潤色'
		} else if (allPromptNames.length > 0) {
			currentPolishPrompt.value = allPromptNames[0]
		}

		if (allPromptNames.includes('擴寫')) {
			currentExpandPrompt.value = '擴寫'
		} else if (allPromptNames.length > 0) {
			currentExpandPrompt.value = allPromptNames[0]
		}

		if (allPromptNames.includes('章節審核')) {
			currentReviewPrompt.value = '章節審核'
		} else if (allPromptNames.length > 0) {
			currentReviewPrompt.value = allPromptNames[0]
		}
	} catch (e) {
		console.error('Failed to load prompts:', e)
		reviewPrompts.value = ['章節審核']
		polishPrompts.value = ['潤色']
		expandPrompts.value = ['擴寫']
	}
}


// 處理標題編輯（正文頁大標題）
async function handleTitleBlur() {
	if (!titleElement.value) return
	const newTitle = titleElement.value.textContent?.trim() || ''
	if (newTitle && newTitle !== localCard.title) {
		await saveTitle(newTitle)
	} else {
		// 恢復原標題
		if (titleElement.value) titleElement.value.textContent = localCard.title
	}
}

async function handleTitleEnter() {
	if (!titleElement.value) return
	titleElement.value.blur() // 觸發 blur 事件統一保存
}

// 保存標題：同時更新 card.title 與 content.title，保證上下文使用的 @self.content.title 爲最新
async function saveTitle(newTitle: string) {
	try {
		const trimmed = newTitle.trim()
		if (!trimmed) return
		localCard.title = trimmed
		localCard.content = {
			...(localCard.content || {}),
			// 僅更新 title 字段，正文內容等保持不變
			...(localCard.content as any),
			title: trimmed,
		}
		const updatePayload: CardUpdate = {
			title: trimmed,
			content: localCard.content as any,
		}
		await cardStore.modifyCard(localCard.id, updatePayload)
		ElMessage.success('標題已更新')
	} catch (e) {
		ElMessage.error('標題更新失敗')
		// 恢復原標題
		if (titleElement.value) titleElement.value.textContent = localCard.title
	}
}

// 保存正文：可選接收來自父級的最新標題，一次性寫入 card.title 與 content.title
async function handleSave(newTitle?: string) {
	if (props.chapter) { emit('save'); return }
	const effectiveTitle = (typeof newTitle === 'string' && newTitle.trim()) ? newTitle.trim() : localCard.title
	if (effectiveTitle && effectiveTitle !== localCard.title) {
		localCard.title = effectiveTitle
	}
	const nextContent = {
		...localCard.content,
		content: getText(),
		word_count: wordCount.value,
		volume_number: (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number,
		chapter_number: (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number,
		// 始終把最新標題寫入 content.title，供上下文模板和篩選使用
		title: effectiveTitle || (localCard.content as any)?.title || localCard.title,
	}
	const updatePayload: CardUpdate = {
		title: effectiveTitle,
		content: nextContent as any,
		needs_confirmation: false,  // 清除 AI 修改標記，觸發工作流
	}
	localCard.content = nextContent as any
	await cardStore.modifyCard(localCard.id, updatePayload)

	// 保存成功後重置dirty狀態
	originalContent.value = getText()
	isDirty.value = false
	emit('update:dirty', false)

	// 返回保存的內容供歷史版本使用
	return updatePayload.content
}

function resolveLlmConfigId(): number | undefined {
	const p = perCardParams.value || editingParams.value
	return p?.llm_config_id
}

function resolvePromptName(): string | undefined {
	const p = perCardParams.value || editingParams.value
	return p?.prompt_name
}

function resolveSampling() {
	const src: any = perCardParams.value || editingParams.value || {}
	return { temperature: src.temperature, max_tokens: src.max_tokens, timeout: src.timeout }
}

function buildExtractRunOptions(
	opts?: ChapterExtractRunOptions,
	fallbackLlmConfigId?: number
): ChapterExtractRunOptions | null {
	const llmConfigId = typeof opts?.llm_config_id === 'number' ? opts.llm_config_id : fallbackLlmConfigId
	if (!llmConfigId) return null
	return {
		llm_config_id: llmConfigId,
		temperature: typeof opts?.temperature === 'number' ? opts.temperature : undefined,
		max_tokens: typeof opts?.max_tokens === 'number' ? opts.max_tokens : undefined,
		timeout: typeof opts?.timeout === 'number' ? opts.timeout : undefined,
	}
}

function formatFactsFromContext(ctx: any | null | undefined): string {
	try {
		if (!ctx) return ''
		const factsStruct: any = (ctx as any)?.facts_structured || {}
		const lines: string[] = []
		if (Array.isArray(factsStruct.fact_summaries) && factsStruct.fact_summaries.length) {
			lines.push('關鍵事實:')
			for (const s of factsStruct.fact_summaries) lines.push(`- ${s}`)
		}
		if (Array.isArray(factsStruct.relation_summaries) && factsStruct.relation_summaries.length) {
			lines.push('關係摘要:')
			for (const r of factsStruct.relation_summaries) {
				lines.push(`- ${r.a} ↔ ${r.b}（${r.kind}）`)
				if (r.a_to_b_addressing || r.b_to_a_addressing) {
					const a1 = r.a_to_b_addressing ? `A稱B：${r.a_to_b_addressing}` : ''
					const b1 = r.b_to_a_addressing ? `B稱A：${r.b_to_a_addressing}` : ''
					if (a1 || b1) lines.push(`  · ${[a1, b1].filter(Boolean).join(' ｜ ')}`)
				}
				if (Array.isArray(r.recent_dialogues) && r.recent_dialogues.length) {
					lines.push('  · 對話樣例:')
					for (const d of r.recent_dialogues) lines.push(`    - ${d}`)
				}
				if (Array.isArray(r.recent_event_summaries) && r.recent_event_summaries.length) {
					lines.push('  · 近期事件:')
					for (const ev of r.recent_event_summaries) {
						const tag = [ev?.volume_number != null ? `卷${ev.volume_number}` : null, ev?.chapter_number != null ? `章${ev.chapter_number}` : null].filter(Boolean).join(' ')
						lines.push(`    - ${ev.summary}${tag ? `（${tag}）` : ''}`)
					}
				}
			}
		}
		if (Array.isArray(factsStruct.item_summaries) && factsStruct.item_summaries.length) {
			lines.push('物品摘要:')
			for (const item of factsStruct.item_summaries) {
				lines.push(`- ${item.name}${item.category ? `（${item.category}）` : ''}`)
				if (item.description) lines.push(`  · 描述: ${item.description}`)
				if (item.current_state) lines.push(`  · 當前狀態: ${item.current_state}`)
				if (item.owner_hint) lines.push(`  · 歸屬提示: ${item.owner_hint}`)
				if (item.power_or_effect) lines.push(`  · 作用/效果: ${item.power_or_effect}`)
				if (item.constraints) lines.push(`  · 限制條件: ${item.constraints}`)
			}
		}
		if (Array.isArray(factsStruct.concept_summaries) && factsStruct.concept_summaries.length) {
			lines.push('概念摘要:')
			for (const concept of factsStruct.concept_summaries) {
				lines.push(`- ${concept.name}${concept.category ? `（${concept.category}）` : ''}`)
				if (concept.description) lines.push(`  · 描述: ${concept.description}`)
				if (concept.rule_definition) lines.push(`  · 規則定義: ${concept.rule_definition}`)
				if (concept.mastery_hint) lines.push(`  · 掌握提示: ${concept.mastery_hint}`)
				if (concept.cost) lines.push(`  · 代價: ${concept.cost}`)
				if (Array.isArray(concept.known_by) && concept.known_by.length) lines.push(`  · 已知掌握者: ${concept.known_by.join('、')}`)
				if (Array.isArray(concept.counter_relations) && concept.counter_relations.length) lines.push(`  · 剋制/對立: ${concept.counter_relations.join('、')}`)
			}
		}
		const text = lines.join('\n')
		if (text) return text
		const subgraph = (ctx as any)?.facts_subgraph
		return subgraph ? String(subgraph) : ''
	} catch { return '' }
}

function formatReviewCreatedAt(value?: string | null): string {
	if (!value) return ''
	try {
		return new Intl.DateTimeFormat('zh-CN', {
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
		}).format(new Date(value))
	} catch {
		return value
	}
}

async function executeReview() {
	if (!ensureNoPendingAiEdit()) return

	const chapterText = getText().trim()
	if (!chapterText) {
		ElMessage.warning('請先輸入本章正文後再審核')
		return
	}

	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) {
		ElMessage.error('請先設置有效的模型ID')
		return
	}

	reviewLoading.value = true
	reviewText.value = ''
	reviewDraft.value = null
	const abortController = new AbortController()
	reviewAbortController.value = abortController
	try {
		let resolvedContextTemplate = ''
		try {
			resolvedContextTemplate = getResolvedContext(reviewContextKindValue.value, 'review')
		} catch (e) {
			console.error('Failed to resolve context template for review:', e)
		}
		const volumeNumber = (props.contextParams as any)?.volume_number ?? (localCard.content as any)?.volume_number
		const chapterNumber = (props.contextParams as any)?.chapter_number ?? (localCard.content as any)?.chapter_number
		const participants = extractParticipantsForCurrentChapter()
		const factsText = formatFactsFromContext(props.prefetched).trim()
		const requestPayload: ReviewRunRequest = {
			card_id: props.card.id,
			project_id: projectStore.currentProject?.id || props.card.project_id,
			title: localCard.title || (localCard.content as any)?.title || '未命名章節',
			review_type: 'chapter',
			review_profile: 'generic_card_review',
			target_type: 'card',
			target_field: 'content.content',
			target_text: buildChapterReviewTarget(chapterText, {
				title: localCard.title || (localCard.content as any)?.title || '未命名章節',
				volumeNumber: volumeNumber ?? null,
				chapterNumber: chapterNumber ?? null,
				participants,
			}),
			context_info: resolvedContextTemplate.trim() || undefined,
			facts_info: factsText || undefined,
			content_snapshot: chapterText,
			llm_config_id: llmConfigId,
			prompt_name: currentReviewPrompt.value || '章節審核',
			meta: {
				source: 'chapter_editor',
				card_type_name: props.card.card_type?.name || '',
			},
		}

		try {
			const { temperature, max_tokens, timeout } = resolveSampling()
			if (typeof temperature === 'number') requestPayload.temperature = temperature
			if (typeof max_tokens === 'number') requestPayload.max_tokens = Math.min(max_tokens, 4096)
			if (typeof timeout === 'number') requestPayload.timeout = timeout
		} catch {}

		const result = await runReview(requestPayload, { signal: abortController.signal }).catch((e) => {
			if (isCanceledRequest(e)) {
				ElMessage.info('審核已中斷')
				return null
			}
			throw e
		})
		if (!result) return
		reviewText.value = result.review_text
		reviewDraft.value = result.draft
		reviewDialogVisible.value = true
		notifyEditorTaskDone('review')
		ElMessage.success('章節審核完成')
	} catch (e) {
		console.error('章節審核失敗:', e)
		ElMessage.error('章節審核失敗')
	} finally {
		if (reviewAbortController.value === abortController) {
			reviewAbortController.value = null
		}
		reviewLoading.value = false
	}
}

async function handleCreateOrUpdateReviewCard() {
	if (!reviewDraft.value) return
	reviewCardSaving.value = true
	try {
		const saved = await upsertReviewCard({
			project_id: projectStore.currentProject?.id || props.card.project_id,
			target_card_id: props.card.id,
			target_title: localCard.title || (localCard.content as any)?.title || '未命名章節',
			review_type: reviewDraft.value.review_type,
			review_profile: reviewDraft.value.review_profile,
			target_field: reviewDraft.value.review_target_field || null,
			review_text: reviewText.value,
			quality_gate: reviewDraft.value.quality_gate,
			prompt_name: reviewDraft.value.prompt_name,
			llm_config_id: reviewDraft.value.llm_config_id || undefined,
			content_snapshot: reviewDraft.value.target_snapshot || undefined,
			meta: reviewDraft.value.meta || {},
		})
		reviewDraft.value.existing_review_card_id = saved.card_id
		await cardStore.fetchCards(projectStore.currentProject?.id || props.card.project_id)
		window.dispatchEvent(new CustomEvent('nf:review-history-refresh'))
		ElMessage.success('審核結果卡片已更新')
	} catch (error) {
		console.error('Failed to upsert review result card:', error)
		ElMessage.error('創建審核結果卡片失敗')
	} finally {
		reviewCardSaving.value = false
	}
}

async function executeAIContinuation() {
	if (!ensureNoPendingAiEdit()) return
	const defaults = resolveContinuationDefaults()
	continuationDialogState.targetWordCount = defaults.targetWordCount
	continuationDialogState.wordControlMode = defaults.wordControlMode
	continuationDialogState.guidance = defaults.guidance
	continuationDialogVisible.value = true
}

function handleContinuationDialogConfirm(payload: {
	targetWordCount: number
	wordControlMode: ContinuationWordControlMode
	guidance: string
}) {
	activeContinuationConfig.targetWordCount = payload.targetWordCount
	activeContinuationConfig.wordControlMode = payload.wordControlMode
	try {
		localStorage.setItem(`nf:chapter:continuation-target:${props.card.id}`, String(payload.targetWordCount))
		localStorage.setItem(`nf:chapter:continuation-mode:${props.card.id}`, payload.wordControlMode)
		localStorage.removeItem(`nf:chapter:continuation-guidance:${props.card.id}`)
	} catch {
		// ignore localStorage errors
	}
	void runContinuationWithConfig(payload)
}

async function runContinuationWithConfig(payload: {
	targetWordCount: number
	wordControlMode: ContinuationWordControlMode
	guidance: string
}) {
	if (!ensureNoPendingAiEdit()) return
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { ElMessage.error('請先設置有效的模型ID'); return }
	const promptName = resolvePromptName()
	if (!promptName) { ElMessage.error('未設置生成任務名（prompt）'); return }

	aiLoading.value = true

	// 1. 解析卡片的上下文槽位（上下文注入的引用內容）
	let resolvedContextTemplate = ''
	try {
		resolvedContextTemplate = getResolvedContext(generationContextKindValue.value, 'generation')
	} catch (e) {
		console.error('Failed to resolve context template:', e)
	}

	// 2. 格式化事實子圖（參與實體）
	// 3. 組合完整的上下文信息
	const contextParts: string[] = []
	if (resolvedContextTemplate) {
		contextParts.push(`【引用上下文】\n${resolvedContextTemplate}`)
	}
	const contextInfoBlock = contextParts.join('\n\n')

	// 4. 計算已有內容字數
	const existingText = getText()
	const existingWordCount = computeWordCount(existingText)

	const requestData: ContinuationRequest = {
		previous_content: existingText,
		context_info: contextInfoBlock,
		existing_word_count: existingWordCount,
		llm_config_id: llmConfigId,
		stream: true,
		prompt_name: promptName,
		...(props.contextParams || {}) as any,
	} as any
	;(requestData as any).target_word_count = payload.targetWordCount
	;(requestData as any).word_control_mode = payload.wordControlMode
	;(requestData as any).continuation_guidance = payload.guidance || undefined

	try {
		const { temperature, max_tokens, timeout } = resolveSampling()
		if (typeof temperature === 'number') (requestData as any).temperature = temperature
		if (typeof max_tokens === 'number') (requestData as any).max_tokens = max_tokens
		if (typeof timeout === 'number') (requestData as any).timeout = timeout
	} catch {}

	try {
		const autoParticipants = extractParticipantsForCurrentChapter()
		if (autoParticipants.length) (requestData as any).participants = autoParticipants
	} catch {}

	applyContinuationScope(requestData)

	if (view) { view.focus(); const end = view.state.doc.length; view.dispatch({ selection: { anchor: end } }) }

	executeAIGeneration(requestData, false, '續寫', undefined, undefined, 'continue')
}

function handlePolishPromptChange(promptName: string) {
	currentPolishPrompt.value = promptName
	promptPicker.polish.visible = false
	promptPicker.polish.keyword = ''
	ElMessage.success(`已切換潤色提示詞爲: ${promptName}`)
}

function handleExpandPromptChange(promptName: string) {
	currentExpandPrompt.value = promptName
	promptPicker.expand.visible = false
	promptPicker.expand.keyword = ''
	ElMessage.success(`已切換擴寫提示詞爲: ${promptName}`)
}

function handleReviewPromptChange(promptName: string) {
	currentReviewPrompt.value = promptName
	promptPicker.review.visible = false
	promptPicker.review.keyword = ''
	ElMessage.success(`已切換審核提示詞爲: ${promptName}`)
}

function handlePromptPickerShow(activeKey: PromptPickerKey) {
	for (const key of Object.keys(promptPicker) as PromptPickerKey[]) {
		if (key !== activeKey) {
			promptPicker[key].visible = false
			promptPicker[key].keyword = ''
		}
	}
}

function handlePromptPickerHide(key: PromptPickerKey) {
	promptPicker[key].keyword = ''
}

async function executePolish() {
	await executeAIEdit(currentPolishPrompt.value, undefined, undefined, 'polish')
}

async function executeExpand() {
	await executeAIEdit(currentExpandPrompt.value, undefined, undefined, 'expand')
}

// 右鍵菜單處理函數
function handleEditorContextMenu(e: MouseEvent) {
	console.log(' [ContextMenu] 右鍵事件觸發')

	// 檢查是否有選中文本
	const selection = getSelectionWithLineInfo()
	if (!selection || !selection.text.trim()) {
		console.log('⚠️ [ContextMenu] 沒有選中文本，使用默認菜單')
		return // 沒有選中文本，使用默認右鍵菜單
	}


	e.preventDefault()
	e.stopPropagation()

	// 保存選中的文本信息
	contextMenu.selectedText = selection
	contextMenu.visible = true
	contextMenu.expanded = false
	contextMenu.userRequirement = ''

	// 設置自定義高亮，替代默認選中效果
	setHighlight(selection.from, selection.to)

	// 計算菜單位置（避免超出屏幕）
	const menuWidth = 280
	const menuHeight = 200
	let x = e.clientX
	let y = e.clientY

	if (x + menuWidth > window.innerWidth) {
		x = window.innerWidth - menuWidth - 10
	}
	if (y + menuHeight > window.innerHeight) {
		y = window.innerHeight - menuHeight - 10
	}

	contextMenu.x = x
	contextMenu.y = y


	// 延遲註冊點擊外部關閉的監聽器，避免立即觸發
	setTimeout(() => {
		if (!contextMenuClickListenerAdded) {
			window.addEventListener('click', handleClickOutside, { capture: true })
			contextMenuClickListenerAdded = true
		}
	}, 100)
}

let contextMenuClickListenerAdded = false

function expandContextMenu() {
	contextMenu.expanded = true
	// 自動聚焦輸入框
	nextTick(() => {
		const input = document.querySelector('.context-menu-popup textarea') as HTMLTextAreaElement
		if (input) {
			input.focus()
		} else {
			console.warn('⚠️ [ContextMenu] 未找到輸入框')
		}
	})
}

function closeContextMenu() {
	contextMenu.visible = false
	contextMenu.expanded = false
	contextMenu.userRequirement = ''
	contextMenu.selectedText = null

	// 移除點擊外部關閉的監聽器
	if (contextMenuClickListenerAdded) {
		window.removeEventListener('click', handleClickOutside, { capture: true })
		contextMenuClickListenerAdded = false
	}
}

async function handleContextMenuPolish() {
	const requirement = contextMenu.userRequirement.trim()
	const selectedText = contextMenu.selectedText
	closeContextMenu()
	await executeAIEdit(currentPolishPrompt.value, requirement || undefined, selectedText || undefined, 'polish')
}

async function handleContextMenuExpand() {
	const requirement = contextMenu.userRequirement.trim()
	const selectedText = contextMenu.selectedText
	closeContextMenu()
	await executeAIEdit(currentExpandPrompt.value, requirement || undefined, selectedText || undefined, 'expand')
}

async function handleContextMenuReference() {
	const selectedText = contextMenu.selectedText
	if (!selectedText || !selectedText.text.trim()) {
		closeContextMenu()
		ElMessage.warning('請先選中要引用的正文片段')
		return
	}
	if (isDirty.value) {
		const persisted = await editorStore.persistActiveChapterDraft()
		if (!persisted) {
			closeContextMenu()
			return
		}
	}
	closeContextMenu()
	const projectId = projectStore.currentProject?.id || props.card.project_id
	if (!projectId) {
		ElMessage.error('未找到當前項目，無法引用')
		return
	}
	const projectName = projectStore.currentProject?.name || ''
	const excerptRef = {
		refType: 'chapter_excerpt',
		projectId,
		projectName,
		cardId: props.card.id,
		cardTitle: localCard.title || props.card.title || '',
		fieldPath: 'content',
		startLine: selectedText.startLine,
		endLine: selectedText.endLine,
		text: selectedText.text,
		numberedText: selectedText.numberedText,
		snapshotHash: selectedText.snapshotHash,
		source: 'manual',
		// 兼容舊協議：若助手側尚未升級，會按整卡引用字段讀取 content
		content: {
			text: selectedText.text,
			startLine: selectedText.startLine,
			endLine: selectedText.endLine,
			numberedText: selectedText.numberedText,
			snapshotHash: selectedText.snapshotHash,
		},
	}
	assistantStore.addInjectedRefDirect(excerptRef as any, 'manual')
	emit('switch-tab', 'assistant')
	ElMessage.success(`已引用第 ${selectedText.startLine}-${selectedText.endLine} 行到靈感助手`)
}

async function executeAIEdit(
	promptName: string,
	userRequirement?: string,
	selectedTextInput?: { text: string; from: number; to: number },
	notifyKind?: EditorTaskDoneKind
) {
	if (!ensureNoPendingAiEdit()) return

	const selectedText = selectedTextInput || getSelectedText()
	if (!selectedText) {
		ElMessage.warning(`請先選中要${promptName}的內容`)
		return
	}

	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) {
		ElMessage.error('請先設置有效的模型ID')
		return
	}

	aiLoading.value = true

	// 獲取完整文本
	const fullText = getText()

	// 1. 解析上下文槽位（引用上下文）
	let resolvedContextTemplate = ''
	try {
		resolvedContextTemplate = getResolvedContext(generationContextKindValue.value, 'generation')
	} catch (e) {
		console.error('Failed to resolve context template:', e)
	}

	// 2. 格式化事實子圖（參與實體）

	// 3. 組合上下文信息：引用上下文 + 事實子圖 + 用戶要求 + 上文 + 選中內容 + 下文
	const contextParts: string[] = []
	if (resolvedContextTemplate) {
		contextParts.push(`【引用上下文】\n${resolvedContextTemplate}`)
	}
	if (userRequirement) {
		contextParts.push(`【用戶要求】\n${userRequirement}`)
	}

	// 提取上文（選中內容之前）
	const beforeText = fullText.substring(0, selectedText.from)
	if (beforeText.trim()) {
		// 截取最後1000字作爲上文
		const truncatedBefore = beforeText.length > 1000 ? '...' + beforeText.slice(-1000) : beforeText
		contextParts.push(`【上文】\n${truncatedBefore}`)
	}

	// 選中的內容
	contextParts.push(`【需要${promptName}的內容】\n${selectedText.text}`)

	// 提取下文（選中內容之後）
	const afterText = fullText.substring(selectedText.to)
	if (afterText.trim()) {
		// 截取前500字作爲下文
		const truncatedAfter = afterText.length > 500 ? afterText.slice(0, 500) + '...' : afterText
		contextParts.push(`【下文】\n${truncatedAfter}`)
	}
	const contextInfoBlock = contextParts.join('\n\n')

	const requestData: ContinuationRequest = {
		previous_content: '', // 潤色/擴寫時爲空，所有上下文都在 context_info 中
		context_info: contextInfoBlock,
		llm_config_id: llmConfigId,
		stream: true,
		prompt_name: promptName,
		append_continuous_novel_directive: false, // 潤色/擴寫不需要"連續輸出"指令
		...(props.contextParams || {}) as any,
	} as any

	try {
		const { temperature, max_tokens, timeout } = resolveSampling()
		if (typeof temperature === 'number') (requestData as any).temperature = temperature
		if (typeof max_tokens === 'number') (requestData as any).max_tokens = max_tokens
		if (typeof timeout === 'number') (requestData as any).timeout = timeout
	} catch {}

	try {
		const autoParticipants = extractParticipantsForCurrentChapter()
		if (autoParticipants.length) (requestData as any).participants = autoParticipants
	} catch {}

	applyContinuationScope(requestData)

	executeAIGeneration(requestData, true, promptName, selectedText.from, selectedText.to, notifyKind)
}

function acceptPendingAiEdit() {
	if (!view || !pendingAiEdit.value) return
	if (pendingAiEdit.value.generating) {
		ElMessage.warning('正在生成中，請稍後')
		return
	}
	const pending = pendingAiEdit.value
	const previewText = view.state.doc.sliceString(pending.previewFrom, pending.previewTo)
	runWithPendingPreviewMutation(() => {
		view!.dispatch({
			changes: { from: pending.originalFrom, to: pending.previewTo, insert: previewText },
			selection: { anchor: pending.originalFrom + previewText.length }
		})
	})
	pendingAiEdit.value = null
	clearHighlight()
	ElMessage.success('已接受替換')
}

function rejectPendingAiEdit() {
	if (!view || !pendingAiEdit.value) return
	if (pendingAiEdit.value.generating) {
		interruptStream()
	}
	const pending = pendingAiEdit.value
	runWithPendingPreviewMutation(() => {
		view!.dispatch({
			changes: { from: pending.previewFrom, to: pending.previewTo, insert: '' },
			selection: { anchor: pending.originalTo }
		})
	})
	pendingAiEdit.value = null
	clearHighlight()
	ElMessage.info('已拒絕替換，保留原文')
}

function executeAIGeneration(
	requestData: ContinuationRequest,
	replaceMode = false,
	taskName = 'AI生成',
	replaceFrom?: number,
	replaceTo?: number,
	notifyKind?: EditorTaskDoneKind
) {
	let accumulated = ''
	let isFirstChunk = true
	let outputStartPos = replaceFrom ?? 0
	let currentOutputLength = 0
	aiStreamCanceled = false

	if (view) {
		view.focus()
		if (!replaceMode) {
			// 續寫模式：光標移到末尾
			const end = view.state.doc.length
			view.dispatch({ selection: { anchor: end } })
			outputStartPos = end
		} else if (replaceFrom !== undefined && replaceTo !== undefined) {
			const originalText = view.state.doc.sliceString(replaceFrom, replaceTo)
			outputStartPos = replaceTo
			pendingAiEdit.value = {
				originalFrom: replaceFrom,
				originalTo: replaceTo,
				originalText,
				previewFrom: replaceTo,
				previewTo: replaceTo,
				generating: true
			}
		}
	}

	streamHandle = generateContinuationStreaming(
		requestData,
		(chunk) => {
			if (!chunk) return
			let delta = chunk
			if (accumulated && chunk.startsWith(accumulated)) {
				delta = chunk.slice(accumulated.length)
			}
			if (delta) {
				const normalized = String(delta)
					.replace(/\r/g, '')
					.replace(/\n+/g, m => (m.length === 2 ? '\n' : m))

				if (replaceMode) {
					// 替換模式：保留原文，在其後追加預覽內容
					if (view) {
						const pending = pendingAiEdit.value
						const pos = pending ? pending.previewTo : view.state.selection.main.head
						runWithPendingPreviewMutation(() => {
							view!.dispatch({
								changes: { from: pos, to: pos, insert: normalized },
								selection: { anchor: pos + normalized.length }
							})
						})
						currentOutputLength += normalized.length
						if (pendingAiEdit.value) {
							pendingAiEdit.value.previewTo = pos + normalized.length
							setCompareHighlight(
								pendingAiEdit.value.originalFrom,
								pendingAiEdit.value.originalTo,
								pendingAiEdit.value.previewFrom,
								pendingAiEdit.value.previewTo
							)
						} else {
							updateHighlight(outputStartPos, outputStartPos + currentOutputLength)
						}
					}
				} else {
					// 續寫模式：追加到末尾
					appendAtEnd(normalized)
					currentOutputLength += normalized.length
					// 動態更新高亮範圍
					updateHighlight(outputStartPos, outputStartPos + currentOutputLength)
				}
			}
			if (chunk.length > accumulated.length) accumulated = chunk
		},
		() => {
			const wasCanceled = aiStreamCanceled
			aiStreamCanceled = false
			aiLoading.value = false
			streamHandle = null
			if (replaceMode && pendingAiEdit.value) {
				pendingAiEdit.value.generating = false
			}
			try {
				if (!replaceMode) {
					let text = getText() || ''
					// 壓縮恰好兩個換行爲一個，>=3 不動
					text = text.replace(/\n+/g, m => (m.length === 2 ? '\n' : m))
					setText(text)
				}
			} catch {}
			console.log('✅ [AI] 生成完成，高亮已保留（點擊編輯器任意位置可清除）')
			if (replaceMode) {
				ElMessage.success(`${taskName}完成，已生成替換建議`)
			} else {
				ElMessage.success(`${taskName}完成！`)
			}
			if (!wasCanceled && notifyKind) {
				notifyEditorTaskDone(notifyKind)
			}
		},
		(error) => {
			aiStreamCanceled = false
			aiLoading.value = false
			streamHandle = null
			if (replaceMode && view && pendingAiEdit.value) {
				runWithPendingPreviewMutation(() => {
					view!.dispatch({
						changes: {
							from: pendingAiEdit.value!.previewFrom,
							to: pendingAiEdit.value!.previewTo,
							insert: ''
						},
						selection: { anchor: pendingAiEdit.value!.originalTo }
					})
				})
				pendingAiEdit.value = null
			}
			clearHighlight()
			console.error(`${taskName}失敗:`, error)
			ElMessage.error(`${taskName}失敗`)
		}
	)
}

function interruptStream() {
	try { reviewAbortController.value?.abort(); } catch {}
	if (streamHandle) aiStreamCanceled = true
	try { streamHandle?.cancel(); } catch {}
}

function applyContinuationScope(requestData: ContinuationRequest) {
	try {
		const scopeProjectId =
			(projectStore.currentProject?.id as number | undefined)
			?? ((localCard as any)?.project_id as number | undefined)
			?? ((props.card as any)?.project_id as number | undefined)
			?? ((props.contextParams as any)?.project_id as number | undefined)

		const scopeVolumeNumber =
			((props.contextParams as any)?.volume_number as number | undefined)
			?? ((localCard.content as any)?.volume_number as number | undefined)

		const scopeChapterNumber =
			((props.contextParams as any)?.chapter_number as number | undefined)
			?? ((localCard.content as any)?.chapter_number as number | undefined)

		if (Number.isFinite(scopeProjectId as number)) (requestData as any).project_id = scopeProjectId
		if (Number.isFinite(scopeVolumeNumber as number)) (requestData as any).volume_number = scopeVolumeNumber
		if (Number.isFinite(scopeChapterNumber as number)) (requestData as any).chapter_number = scopeChapterNumber
	} catch {}
}

function extractParticipantsForCurrentChapter(): string[] {
	try {
		const list = (localCard.content as any)?.entity_list
		if (Array.isArray(list)) {
			return list.map((x:any) => typeof x === 'string' ? x : (x?.name || '')).filter((s:string) => !!s).slice(0, 6)
		}
	} catch {}
	return []
}

function extractParticipantsWithTypeForCurrentChapter(): { name: string, type: string }[] {
	const result: { name: string, type: string }[] = []
	try {
		const entityList = (localCard.content as any)?.entity_list
		if (!Array.isArray(entityList)) return []

		const allCards = cards.value || []
		const cardMap = new Map(allCards.map(c => [c.title, c]))

		for (const item of entityList) {
			const name = (typeof item === 'string' ? item : item?.name)?.trim()
			if (!name) continue

			let type = 'unknown'
			if (typeof item !== 'string' && item.entity_type) {
				type = item.entity_type
			} else if (cardMap.has(name)) {
				const card = cardMap.get(name)
				// 簡單的從卡片類型名推斷實體類型
				const cardTypeName = card?.card_type?.name || ''
				if (cardTypeName.includes('角色')) type = 'character'
				else if (cardTypeName.includes('組織')) type = 'organization'
				else if (cardTypeName.includes('場景')) type = 'scene'
				else if (cardTypeName.includes('物品')) type = 'item'
				else if (cardTypeName.includes('概念')) type = 'concept'
			}
			result.push({ name, type })
		}
	} catch (e) {
		console.error("Failed to extract participants with type:", e)
	}
	return result.slice(0, 10) // 適當放寬數量限制
}

function getExistingCardTitleSet(cardTypeName: ManagedCardTypeName): Set<string> {
	const set = new Set<string>()
	for (const card of cards.value || []) {
		if (card?.card_type?.name !== cardTypeName) continue
		const title = String(card?.title || '').trim()
		if (title) set.add(title)
	}
	return set
}

function collectMissingCardNotices(items: Array<{ title?: string | null; cardTypeName: ManagedCardTypeName; entityType: ManagedEntityType }>): MissingCardNotice[] {
	const grouped = new Map<ManagedCardTypeName, Set<string>>()
	const notices: MissingCardNotice[] = []
	for (const item of items) {
		const title = String(item.title || '').trim()
		if (!title) continue
		let existingTitles = grouped.get(item.cardTypeName)
		if (!existingTitles) {
			existingTitles = getExistingCardTitleSet(item.cardTypeName)
			grouped.set(item.cardTypeName, existingTitles)
		}
		if (existingTitles.has(title)) continue
		const key = `${item.cardTypeName}:${title}`
		if (notices.some(entry => entry.key === key)) continue
		notices.push({
			key,
			title,
			cardTypeName: item.cardTypeName,
			entityType: item.entityType,
		})
	}
	return notices
}

function buildRelationMissingCardNotices(relations: Array<{ a?: string; b?: string }>): MissingCardNotice[] {
	const participantTypeMap = new Map(
		extractParticipantsWithTypeForCurrentChapter()
			.filter(item => item.type in ENTITY_TYPE_TO_CARD_TYPE_NAME)
			.map(item => [item.name.trim(), item.type as ManagedEntityType]),
	)
	const candidates: Array<{ title: string; cardTypeName: ManagedCardTypeName; entityType: ManagedEntityType }> = []
	for (const relation of relations || []) {
		for (const rawName of [relation?.a, relation?.b]) {
			const title = String(rawName || '').trim()
			if (!title) continue
			const entityType = participantTypeMap.get(title)
			if (!entityType) continue
			candidates.push({
				title,
				cardTypeName: ENTITY_TYPE_TO_CARD_TYPE_NAME[entityType],
				entityType,
			})
		}
	}
	return collectMissingCardNotices(candidates)
}

function getParticipantNamesByType(entityType: ManagedEntityType): string[] {
	const result = new Set<string>()
	for (const item of extractParticipantsWithTypeForCurrentChapter()) {
		if (item.type !== entityType) continue
		const title = String(item.name || '').trim()
		if (title) result.add(title)
	}
	return Array.from(result)
}

function collectStaleParticipantNotices(
	entityType: ManagedEntityType,
	extractedNames: Iterable<string>,
): ParticipantReviewNotice[] {
	const extractedSet = new Set(
		Array.from(extractedNames)
			.map(name => String(name || '').trim())
			.filter(Boolean),
	)
	return getParticipantNamesByType(entityType)
		.filter(name => !extractedSet.has(name))
		.map(name => ({
			key: `${entityType}:${name}`,
			title: name,
			cardTypeName: ENTITY_TYPE_TO_CARD_TYPE_NAME[entityType],
			entityType,
		}))
}

const dynamicMissingCards = computed(() => collectMissingCardNotices(
	validDynamicPreviewRoles.value.map(role => ({
		title: role.name,
		cardTypeName: '角色卡' as ManagedCardTypeName,
		entityType: 'character' as ManagedEntityType,
	})),
))

const relationMissingCards = computed(() => buildRelationMissingCardNotices(validRelationPreviewItems.value))

const dynamicParticipantReviewNotices = computed(() => collectStaleParticipantNotices(
	'character',
	validDynamicPreviewRoles.value.map(role => role.name),
))

const memoryPrimaryMissingCards = computed(() => {
	if (!memoryPreviewData.value || !memoryPreviewExtractorCode.value) return [] as MissingCardNotice[]
	if (memoryPreviewExtractorCode.value === 'scene_state') {
		return collectMissingCardNotices(
			validScenePreviewItems.value.map(item => ({
				title: item.name,
				cardTypeName: '場景卡' as ManagedCardTypeName,
				entityType: 'scene' as ManagedEntityType,
			})),
		)
	}
	if (memoryPreviewExtractorCode.value === 'organization_state') {
		return collectMissingCardNotices(
			validOrganizationPreviewItems.value.map(item => ({
				title: item.name,
				cardTypeName: '組織卡' as ManagedCardTypeName,
				entityType: 'organization' as ManagedEntityType,
			})),
		)
	}
	if (memoryPreviewExtractorCode.value === 'item_state') {
		return collectMissingCardNotices(
			validItemPreviewItems.value.map(item => ({
				title: item.name,
				cardTypeName: '物品卡' as ManagedCardTypeName,
				entityType: 'item' as ManagedEntityType,
			})),
		)
	}
	if (memoryPreviewExtractorCode.value === 'concept_state') {
		return collectMissingCardNotices(
			validConceptPreviewItems.value.map(item => ({
				title: item.name,
				cardTypeName: '概念卡' as ManagedCardTypeName,
				entityType: 'concept' as ManagedEntityType,
			})),
		)
	}
	return [] as MissingCardNotice[]
})

const memoryParticipantReviewNotices = computed(() => {
	if (!memoryPreviewData.value || !memoryPreviewExtractorCode.value) return [] as ParticipantReviewNotice[]
	if (memoryPreviewExtractorCode.value === 'scene_state') {
		return collectStaleParticipantNotices(
			'scene',
			validScenePreviewItems.value.map(item => item.name),
		)
	}
	if (memoryPreviewExtractorCode.value === 'organization_state') {
		return collectStaleParticipantNotices(
			'organization',
			validOrganizationPreviewItems.value.map(item => item.name),
		)
	}
	if (memoryPreviewExtractorCode.value === 'item_state') {
		return collectStaleParticipantNotices(
			'item',
			validItemPreviewItems.value.map(item => item.name),
		)
	}
	if (memoryPreviewExtractorCode.value === 'concept_state') {
		return collectStaleParticipantNotices(
			'concept',
			validConceptPreviewItems.value.map(item => item.name),
		)
	}
	return [] as ParticipantReviewNotice[]
})

const memoryMissingCards = computed(() => memoryPrimaryMissingCards.value)

function extractCharacterParticipantsForCurrentChapter(): string[] {
	try {
		const list = (localCard.content as any)?.entity_list
		const result: string[] = []
		const characterNames = new Set<string>((cards.value || [])
			.filter((c:any) => c?.card_type?.name === '角色卡')
			.map((c:any) => (c?.title || '').trim())
			.filter((s:string) => !!s))
		if (Array.isArray(list)) {
			for (const item of list) {
				if (typeof item === 'string') {
					const nm = (item || '').trim()
					if (nm && characterNames.has(nm)) result.push(nm)
				} else if (item && typeof item === 'object') {
					const nm = (item.name || '').trim()
					const t = (item.entity_type || '').trim()
					if (nm && (t === 'character' || characterNames.has(nm))) result.push(nm)
				}
			}
		}
		return Array.from(new Set(result)).slice(0, 6)
	} catch {}
	return []
}


// 觸發“動態信息提取”（右欄調用）
editorStore.setTriggerExtractDynamicInfo(async (opts) => {
	if (typeof opts?.llm_config_id === 'number') {
		await extractDynamicInfoWithLlm(opts.llm_config_id, opts)
	} else {
		await extractDynamicInfo()
	}
})

// 觸發“關係提取入圖”（右欄調用）
editorStore.setTriggerExtractRelations(async (opts) => {
	if (typeof opts?.llm_config_id === 'number') {
		await extractRelationsWithLlm(opts.llm_config_id, opts)
	} else {
		await handleIngestRelations()
	}
})

editorStore.setTriggerExtractSceneState(async (opts) => {
	if (typeof opts?.llm_config_id === 'number') {
		await extractMemoryByCode('scene_state', opts.llm_config_id, opts)
	}
})

editorStore.setTriggerExtractOrganizationState(async (opts) => {
	if (typeof opts?.llm_config_id === 'number') {
		await extractMemoryByCode('organization_state', opts.llm_config_id, opts)
	}
})

editorStore.setTriggerExtractItemState(async (opts) => {
	if (typeof opts?.llm_config_id === 'number') {
		await extractMemoryByCode('item_state', opts.llm_config_id, opts)
	}
})

editorStore.setTriggerExtractConceptState(async (opts) => {
	if (typeof opts?.llm_config_id === 'number') {
		await extractMemoryByCode('concept_state', opts.llm_config_id, opts)
	}
})

// 跨組件替換
editorStore.setApplyChapterReplacements(async (pairs) => {
	if (!view) return
	let original = getText() || ''
	let replaced = original
	for (const pair of (pairs || [])) {
		if ((pair as any)?.mode === 'line_range') {
			const op = pair as any
			const startLine = Number(op.startLine)
			const endLine = Number(op.endLine)
			if (!Number.isFinite(startLine) || !Number.isFinite(endLine) || startLine <= 0 || endLine < startLine) {
				ElMessage.warning('按行替換失敗：無效的行號範圍')
				continue
			}
			const lines = replaced.split('\n')
			if (endLine > lines.length) {
				ElMessage.warning('按行替換失敗：行號超出正文範圍')
				continue
			}
			const replacementLines = String(op.newText ?? '').split('\n')
			lines.splice(startLine - 1, endLine - startLine + 1, ...replacementLines)
			replaced = lines.join('\n')
			continue
		}
		const from = (pair as any)?.from
		if (!from) continue
		const safeFrom = String(from).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
		replaced = replaced.replace(new RegExp(safeFrom, 'g'), String((pair as any)?.to ?? ''))
	}
	setText(replaced)
})

// 靈感助手引用正文片段時，需要先確認保存當前正文，
// 這樣後端按行替換工具才能看到最新文本與行號。
editorStore.setPersistActiveChapterDraft(async () => {
	if (!view) return false
	if (!isDirty.value) return true
	try {
		await ElMessageBox.confirm(
			'你引用的正文片段包含未保存修改。爲確保靈感助手按行替換時能定位到最新正文，需要先保存當前章節。是否現在保存？',
			'請先保存章節',
			{
				type: 'warning',
				confirmButtonText: '保存後繼續',
				cancelButtonText: '取消',
			},
		)
		await handleSave()
		return true
	} catch {
		return false
	}
})

async function extractDynamicInfo() {
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { ElMessage.error('請先選擇一個有效的AI參數配置（模型）'); return }
	await extractDynamicInfoWithLlm(llmConfigId, { llm_config_id: llmConfigId })
}

async function extractDynamicInfoWithLlm(llmConfigId: number, opts?: ChapterExtractRunOptions) {
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		if (!projectId) { ElMessage.error('未找到當前項目ID'); return }
		const participants = extractParticipantsWithTypeForCurrentChapter()
		const chapterText = getText() || ''
		const extraContext = (props.contextParams as any)?.extra_context_fn()
		const runOptions = buildExtractRunOptions(opts, llmConfigId)
		const data = await extractDynamicInfoOnly({
			project_id: projectId,
			text: chapterText,
			participants,
			llm_config_id: llmConfigId,
			temperature: runOptions?.temperature,
			max_tokens: runOptions?.max_tokens,
			timeout: runOptions?.timeout,
			extra_context: extraContext,
		} as any)
		previewData.value = data
		await ensureEditorMainTabVisible()
		previewDialogVisible.value = true
	} catch (e) {
		console.error(e)
		ElMessage.error('提取動態信息失敗')
	}
}

async function confirmApplyUpdates() {
	if (isDynamicPreviewEmpty.value) {
		previewDialogVisible.value = false
		previewData.value = null
		return
	}
	dynamicPreviewApplying.value = true
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		const sanitizedPreviewData = buildSanitizedDynamicPreviewData()
		if (!projectId || !sanitizedPreviewData) { previewDialogVisible.value = false; return }
		const modify: any[] = []
		try {
			for (const role of (sanitizedPreviewData.info_list || [])) {
				const name = role.name
				const di: any = role.dynamic_info || {}
				for (const catKey of Object.keys(di)) {
					const items = di[catKey] || []
					for (const it of items) {
						if (typeof it.weight === 'number' && it.id && it.id > 0) {
							modify.push({ name, dynamic_type: catKey, id: it.id, weight: it.weight })
						}
					}
				}
			}
		} catch {}
		const payload: any = { ...sanitizedPreviewData }
		if (modify.length) payload.modify_info_list = modify
		const resp = await updateDynamicInfoOnly({
			project_id: projectId,
			data: payload as any,
			queue_size: 5,
		})
		if (resp?.success) {
			let appendedCount = 0
			try {
				appendedCount = await appendParticipantsToCurrentChapter(collectConfirmedDynamicParticipantNames())
			} catch (syncError) {
				console.error(syncError)
				ElMessage.warning('動態信息已寫入，但同步本章參與實體失敗')
			}
			ElMessage.success(`動態信息已更新：${resp.updated_card_count} 個角色卡${appendedCount > 0 ? `，並補充 ${appendedCount} 個參與實體` : ''}`)
			try { await cardStore.fetchCards(projectId) } catch {}
		} else {
			ElMessage.warning('未檢測到需要更新的動態信息')
		}
	} catch (e) {
		console.error(e)
		ElMessage.error('更新動態信息失敗')
	} finally {
		dynamicPreviewApplying.value = false
		previewDialogVisible.value = false
		previewData.value = null
	}
}

async function handleIngestRelations() {
	const llmConfigId = resolveLlmConfigId()
	if (!llmConfigId) { ElMessage.error('請先選擇一個有效的AI參數配置（模型）'); return }
	await extractRelationsWithLlm(llmConfigId, { llm_config_id: llmConfigId })
}

async function confirmIngestRelationsFromPreview() {
	if (isRelationsPreviewEmpty.value) {
		relationsPreviewVisible.value = false
		relationsPreview.value = null
		return
	}
	relationsPreviewApplying.value = true
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		const sanitizedRelationsPreview = buildSanitizedRelationsPreviewData()
		if (!projectId || !sanitizedRelationsPreview) { relationsPreviewVisible.value = false; return }
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number
		const resp = await ingestRelationsFromPreview({ project_id: projectId, data: sanitizedRelationsPreview, volume_number: vol, chapter_number: ch })
		ElMessage.success(`已寫入關係/別名：${resp.written} 條`)
	} catch (e) {
		console.error(e)
		ElMessage.error('關係入圖失敗')
	} finally {
		relationsPreviewApplying.value = false
		relationsPreviewVisible.value = false
		relationsPreview.value = null
	}
}

function removePreviewItem(roleName: string, catKey: string, index: number) {
	if (!previewData.value) return
	const role = previewData.value.info_list.find(r => r.name === roleName)
	if (role) {
		const di: Record<string, any[]> = (role as any).dynamic_info || {}
		const catItems = di[catKey] || []
		if (catItems.length > index) {
			catItems.splice(index, 1)
			if (catItems.length === 0) {
				delete di[catKey]
				if (Object.keys(di).length === 0) {
					delete (role as any).dynamic_info
				}
			}
			(role as any).dynamic_info = di
		}
	}
}

async function extractRelationsWithLlm(llmConfigId: number, opts?: ChapterExtractRunOptions) {
	try {
		const text = getText() || ''
		const participants = extractParticipantsWithTypeForCurrentChapter()
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number
		const runOptions = buildExtractRunOptions(opts, llmConfigId)

		let mergedText = text
		try {
			const factsText = formatFactsFromContext(props.prefetched)
			if (factsText) mergedText = `【已知事實子圖】\n${factsText}\n\n正文如下：\n${text}`
		} catch {}

		const data = await extractRelationsOnly({
			text: mergedText,
			participants,
			llm_config_id: llmConfigId,
			temperature: runOptions?.temperature,
			max_tokens: runOptions?.max_tokens,
			timeout: runOptions?.timeout,
			volume_number: vol,
			chapter_number: ch,
		} as any)
		relationsPreview.value = data
		await ensureEditorMainTabVisible()
		relationsPreviewVisible.value = true
	} catch (e) {
		console.error(e)
		ElMessage.error('關係抽取失敗')
	}
}

async function extractMemoryByCode(extractorCode: MemoryExtractorCode, llmConfigId: number, opts?: ChapterExtractRunOptions) {
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		if (!projectId) { ElMessage.error('未找到當前項目ID'); return }
		const text = getText() || ''
		const participants = extractParticipantsWithTypeForCurrentChapter()
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number
		const extraContext = (props.contextParams as any)?.extra_context_fn?.()
		const runOptions = buildExtractRunOptions(opts, llmConfigId)

		let mergedText = text
		try {
			const factsText = formatFactsFromContext(props.prefetched)
			if (factsText) mergedText = `【已知事實子圖】\n${factsText}\n\n正文如下：\n${text}`
		} catch {}

		const data = await extractMemoryPreview({
			project_id: projectId,
			extractor_code: extractorCode,
			text: mergedText,
			participants,
			llm_config_id: llmConfigId,
			temperature: runOptions?.temperature,
			max_tokens: runOptions?.max_tokens,
			timeout: runOptions?.timeout,
			extra_context: extraContext,
			volume_number: vol,
			chapter_number: ch,
		})
		memoryPreviewExtractorCode.value = extractorCode
		memoryPreviewData.value = data.preview_data
		await ensureEditorMainTabVisible()
		memoryPreviewVisible.value = true
	} catch (e) {
		console.error(e)
		ElMessage.error(`${getMemoryExtractorDisplayLabel(extractorCode)}提取失敗`)
	}
}

function openCreateCardFromPreview(item: MissingCardNotice) {
	window.dispatchEvent(new CustomEvent('nf:open-create-card', {
		detail: {
			title: item.title,
			cardTypeName: item.cardTypeName,
		},
	}))
}

function normalizeParticipantEntityName(entry: any): string {
	return typeof entry === 'string' ? entry.trim() : String(entry?.name || '').trim()
}

async function appendParticipantsToCurrentChapter(names: string[]): Promise<number> {
	const cardId = Number((props.card as any)?.id || (localCard as any)?.id || 0)
	if (!cardId) return 0

	const currentList = Array.isArray((localCard.content as any)?.entity_list)
		? [...((localCard.content as any).entity_list as any[])]
		: []
	const existingNames = new Set(currentList.map(normalizeParticipantEntityName).filter(Boolean))
	const additions: string[] = []

	for (const rawName of names || []) {
		const name = String(rawName || '').trim()
		if (!name || existingNames.has(name)) continue
		existingNames.add(name)
		additions.push(name)
		currentList.push(name)
	}

	if (!additions.length) return 0

	const baseContent = {
		...((props.card as any)?.content || {}),
		...((localCard.content as any) || {}),
		entity_list: currentList,
	}
	const axiosResp: any = await updateCardRaw(cardId, { content: baseContent } as CardUpdate)
	const updatedCard = axiosResp?.data as CardRead | undefined
	const index = cards.value.findIndex((c: any) => c.id === cardId)
	if (index !== -1 && updatedCard) {
		const existingCard = cards.value[index] as any
		;(cards.value as any)[index] = { ...existingCard, ...updatedCard, content: baseContent }
	}
	;(localCard.content as any).entity_list = currentList
	return additions.length
}

function collectConfirmedDynamicParticipantNames(): string[] {
	const missingTitles = new Set(dynamicMissingCards.value.map(item => item.title))
	const names = validDynamicPreviewRoles.value
		.map(role => String(role?.name || '').trim())
		.filter(name => !!name && !missingTitles.has(name))
	return Array.from(new Set(names))
}

function collectConfirmedMemoryParticipantNames(): string[] {
	if (!memoryPreviewData.value || !memoryPreviewExtractorCode.value) return []
	const missingTitles = new Set(memoryMissingCards.value.map(item => item.title))
	let names: string[] = []
	switch (memoryPreviewExtractorCode.value) {
		case 'scene_state':
			names = validScenePreviewItems.value.map(item => String(item?.name || '').trim())
			break
		case 'organization_state':
			names = validOrganizationPreviewItems.value.map(item => String(item?.name || '').trim())
			break
		case 'item_state':
			names = validItemPreviewItems.value.map(item => String(item?.name || '').trim())
			break
		case 'concept_state':
			names = validConceptPreviewItems.value.map(item => String(item?.name || '').trim())
			break
		default:
			names = []
	}
	return Array.from(new Set(names.filter(name => !!name && !missingTitles.has(name))))
}

function buildSanitizedDynamicPreviewData() {
	if (!previewData.value) return null
	return {
		...previewData.value,
		info_list: validDynamicPreviewRoles.value,
	}
}

function buildSanitizedRelationsPreviewData() {
	if (!relationsPreview.value) return null
	return {
		...relationsPreview.value,
		relations: validRelationPreviewItems.value,
	}
}

function buildSanitizedMemoryPreviewData() {
	if (!memoryPreviewData.value) return null
	return {
		...memoryPreviewData.value,
		scenes: validScenePreviewItems.value,
		organizations: validOrganizationPreviewItems.value,
		items: validItemPreviewItems.value,
		concepts: validConceptPreviewItems.value,
	}
}

async function ensureEditorMainTabVisible() {
	window.dispatchEvent(new CustomEvent('nf:switch-main-tab', {
		detail: { tab: 'editor' },
	}))
	await nextTick()
}

async function removeParticipantFromCurrentChapter(item: ParticipantReviewNotice) {
	const cardId = Number((props.card as any)?.id || (localCard as any)?.id || 0)
	if (!cardId) {
		ElMessage.warning('未找到當前章節卡片，無法更新參與實體')
		return
	}
	const currentList = Array.isArray((localCard.content as any)?.entity_list)
		? [...((localCard.content as any).entity_list as any[])]
		: []
	const nextList = currentList.filter(entry => {
		const name = typeof entry === 'string' ? entry : entry?.name
		return String(name || '').trim() !== item.title
	})
	if (nextList.length === currentList.length) {
		ElMessage.warning(`${item.title} 當前不在本章參與實體列表中`)
		return
	}
	try {
		const baseContent = {
			...((props.card as any)?.content || {}),
			entity_list: nextList,
		}
		await cardStore.modifyCard(cardId, { content: baseContent } as any)
		;(localCard.content as any).entity_list = nextList
		ElMessage.success(`已將 ${item.title} 移出本章參與實體`)
	} catch (error) {
		console.error(error)
		ElMessage.error('更新本章參與實體失敗')
	}
}

function removeRelationPreviewItem(index: number, row?: any) {
	if (!relationsPreview.value?.relations?.length) return
	if (row) {
		const targetIndex = relationsPreview.value.relations.indexOf(row)
		if (targetIndex >= 0) {
			relationsPreview.value.relations.splice(targetIndex, 1)
			return
		}
	}
	relationsPreview.value.relations.splice(index, 1)
}

function removeMemoryCardPreviewItem(kind: 'scenes' | 'organizations' | 'items' | 'concepts', index: number, row?: any) {
	if (!memoryPreviewData.value) return
	const list = Array.isArray((memoryPreviewData.value as any)[kind]) ? (memoryPreviewData.value as any)[kind] : []
	if (row) {
		const targetIndex = list.indexOf(row)
		if (targetIndex >= 0) {
			list.splice(targetIndex, 1)
			return
		}
	}
	list.splice(index, 1)
}

function closeMemoryPreview() {
	memoryPreviewVisible.value = false
	memoryPreviewData.value = null
	memoryPreviewExtractorCode.value = ''
}

async function applyMemoryPreviewConfirm() {
	if (isMemoryPreviewEmpty.value) {
		closeMemoryPreview()
		return
	}
	memoryPreviewApplying.value = true
	try {
		const projectId = projectStore.currentProject?.id || (localCard as any).project_id
		const sanitizedMemoryPreviewData = buildSanitizedMemoryPreviewData()
		if (!projectId || !sanitizedMemoryPreviewData || !memoryPreviewExtractorCode.value) {
			closeMemoryPreview()
			return
		}
		const participants = extractParticipantsWithTypeForCurrentChapter()
		const vol = (localCard as any)?.content?.volume_number ?? (props.contextParams as any)?.volume_number
		const ch = (localCard as any)?.content?.chapter_number ?? (props.contextParams as any)?.chapter_number
		const resp = await applyMemoryPreview({
			project_id: projectId,
			extractor_code: memoryPreviewExtractorCode.value,
			data: sanitizedMemoryPreviewData as Record<string, any>,
			participants,
			volume_number: vol,
			chapter_number: ch,
		})
		if (resp?.success) {
			const label = getMemoryExtractorDisplayLabel(memoryPreviewExtractorCode.value)
			let appendedCount = 0
			try {
				appendedCount = await appendParticipantsToCurrentChapter(collectConfirmedMemoryParticipantNames())
			} catch (syncError) {
				console.error(syncError)
				ElMessage.warning('提取結果已寫入，但同步本章參與實體失敗')
			}
			ElMessage.success(`${label}已寫入：${resp.updated_card_count} 張卡片${appendedCount > 0 ? `，並補充 ${appendedCount} 個參與實體` : ''}`)
			try { await cardStore.fetchCards(projectId) } catch {}
		} else {
			ElMessage.warning('未檢測到需要寫入的記憶')
		}
	} catch (e) {
		console.error(e)
		ElMessage.error('寫入擴展記憶失敗')
	} finally {
		memoryPreviewApplying.value = false
		closeMemoryPreview()
	}
}

onMounted(() => {
	initEditor()
	loadPrompts()
	const defaults = resolveContinuationDefaults()
	activeContinuationConfig.targetWordCount = defaults.targetWordCount
	activeContinuationConfig.wordControlMode = defaults.wordControlMode
	try {
		const title = props.card?.title || ''
		const vol = Number((props.contextParams as any)?.volume_number ?? (props.card as any)?.content?.volume_number ?? NaN)
		const ch = Number((props.contextParams as any)?.chapter_number ?? (props.card as any)?.content?.chapter_number ?? NaN)
		editorStore.setCurrentContextInfo({ title, volume: Number.isNaN(vol) ? null : vol, chapter: Number.isNaN(ch) ? null : ch })
	} catch {}

	// ESC 鍵關閉右鍵菜單
	window.addEventListener('keydown', handleKeyDown)
})

function handleClickOutside(e: MouseEvent) {
	if (!contextMenu.visible) return
	const target = e.target as HTMLElement
	// 點擊菜單外部時關閉
	if (!target.closest('.context-menu-popup')) {
		closeContextMenu()
	}
}

// 按 ESC 鍵關閉菜單
function handleKeyDown(e: KeyboardEvent) {
	if (contextMenu.visible && e.key === 'Escape') {
		closeContextMenu()
	}
}

onUnmounted(() => {
	// 移除右鍵菜單監聽器
	if (cmRoot.value) {
		const editorDom = cmRoot.value.querySelector('.cm-editor') as HTMLElement
		if (editorDom) {
			editorDom.removeEventListener('contextmenu', handleEditorContextMenu)
		}
	}

	try { view?.destroy() } catch {}
	editorStore.setApplyChapterReplacements(null)
	editorStore.setPersistActiveChapterDraft(null)
	editorStore.setTriggerExtractDynamicInfo(null)
	editorStore.setTriggerExtractRelations(null)
	editorStore.setTriggerExtractSceneState(null)
	editorStore.setTriggerExtractOrganizationState(null)
	editorStore.setTriggerExtractItemState(null)
	editorStore.setTriggerExtractConceptState(null)
	try { reviewAbortController.value?.abort(); } catch {}
	try { streamHandle?.cancel(); } catch {}

	// 移除事件監聽
	window.removeEventListener('keydown', handleKeyDown)

	// 清理右鍵菜單的點擊監聽器（如果還在）
	if (contextMenuClickListenerAdded) {
		window.removeEventListener('click', handleClickOutside, { capture: true })
		contextMenuClickListenerAdded = false
	}
})

// 恢復歷史版本內容
async function restoreContent(versionContent: any) {
	try {
		// 提取章節正文內容
		const textContent = typeof versionContent === 'string'
			? versionContent
			: (versionContent?.content || '')

		// 更新編輯器內容
		setText(textContent)

		// 更新 localCard.content 的各個字段（保持響應式）
		if (typeof versionContent === 'object') {
			Object.assign(localCard.content, versionContent)
		}
		// 確保 content 字段是正確的文本
		localCard.content.content = textContent

		// 更新原始內容（避免觸發dirty）
		originalContent.value = textContent
		isDirty.value = false
		emit('update:dirty', false)

		// 更新字數
		wordCount.value = computeWordCount(textContent)

	} catch (e) {
		console.error('Failed to restore content:', e)
		throw e
	}
}

// 暴露方法供父組件調用
defineExpose({
	handleSave,
	restoreContent
})

/* NF_ASSISTANT_BATCH_PATCH_BEGIN */
type NfAssistantPatchItem = {
  id?: number
  index?: number
  card_id?: number
  field_path?: string
  start_line?: number | null
  end_line?: number | null
  old_text?: string
  original_text?: string
  new_text?: string
  context_before?: string
  context_after?: string
  instruction?: string
  status?: 'pending' | 'accepted' | 'rejected' | 'conflict'
  _from?: number
  _to?: number
}

const nfAssistantPatchQueue = ref<NfAssistantPatchItem[]>([])
const nfAssistantPatchIndex = ref(0)
const nfAssistantPatchTotal = computed(() => nfAssistantPatchQueue.value.length)
const nfAssistantPatchCurrentNo = computed(() => nfAssistantPatchTotal.value ? nfAssistantPatchIndex.value + 1 : 0)

function nfAssistantCurrentCardId(): number | null {
  const c: any = (props as any)?.card
  const lc: any = (localCard as any)?.value ?? (localCard as any)
  const id = Number(c?.id ?? lc?.id)
  return Number.isFinite(id) ? id : null
}

function nfAssistantCurrentText(): string {
  if (view) return view.state.doc.toString()
  const lc: any = (localCard as any)?.value ?? (localCard as any)
  const content = lc?.content ?? (props as any)?.card?.content
  if (typeof content === 'string') return content
  if (typeof content?.content === 'string') return content.content
  if (typeof content?.text === 'string') return content.text
  return ''
}

function nfAssistantOffsetFromLine(text: string, line: number | null | undefined): number | null {
  if (!line || line < 1) return null
  if (line === 1) return 0
  let pos = 0
  for (let i = 1; i < line; i++) {
    const n = text.indexOf('\n', pos)
    if (n < 0) return null
    pos = n + 1
  }
  return pos
}

function nfAssistantNearestIndex(text: string, needle: string, near: number | null): number {
  if (!needle) return -1
  let best = -1
  let bestDist = Number.MAX_SAFE_INTEGER
  let pos = text.indexOf(needle)
  while (pos >= 0) {
    const dist = near == null ? 0 : Math.abs(pos - near)
    if (dist < bestDist) {
      best = pos
      bestDist = dist
    }
    pos = text.indexOf(needle, pos + Math.max(1, needle.length))
  }
  return best
}

function nfAssistantLocatePatch(patch: NfAssistantPatchItem): { from: number, to: number } | null {
  const text = nfAssistantCurrentText()
  const oldText = String(patch.old_text ?? patch.original_text ?? '')
  const expected = nfAssistantOffsetFromLine(text, patch.start_line)

  const exact = nfAssistantNearestIndex(text, oldText, expected)
  if (exact >= 0) return { from: exact, to: exact + oldText.length }

  const before = String(patch.context_before ?? '')
  const after = String(patch.context_after ?? '')
  if (before && after) {
    const b = nfAssistantNearestIndex(text, before, expected)
    if (b >= 0) {
      const start = b + before.length
      const a = text.indexOf(after, start)
      if (a >= start) return { from: start, to: a }
    }
  }

  if (patch.start_line && patch.end_line) {
    const from = nfAssistantOffsetFromLine(text, patch.start_line)
    const afterEnd = nfAssistantOffsetFromLine(text, patch.end_line + 1)
    if (from != null) {
      const to = afterEnd == null ? text.length : Math.max(from, afterEnd - 1)
      return { from, to }
    }
  }

  return null
}

function nfAssistantScrollToRange(range: { from: number, to: number }) {
  if (!view) return
  view.focus()
  view.dispatch({
    selection: { anchor: range.from },
    effects: EditorView.scrollIntoView(range.from, { y: 'center' })
  })
}

function nfAssistantClearCurrentPreview() {
  if (!view || !pendingAiEdit.value) return
  const p: any = pendingAiEdit.value
  if (p.source !== 'assistant_batch_patch') return
  runWithPendingPreviewMutation(() => {
    view!.dispatch({
      changes: { from: p.previewFrom, to: p.previewTo, insert: '' },
      selection: { anchor: p.originalTo }
    })
  })
  pendingAiEdit.value = null
  clearHighlight()
}

function nfAssistantOpenPatch(index: number) {
  if (!view) return
  if (!nfAssistantPatchQueue.value.length) return

  if (pendingAiEdit.value) {
    const p: any = pendingAiEdit.value
    if (p.source === 'assistant_batch_patch') {
      nfAssistantClearCurrentPreview()
    } else {
      ElMessage.warning('請先接受或拒絕當前替換建議')
      return
    }
  }

  nfAssistantPatchIndex.value = Math.max(0, Math.min(index, nfAssistantPatchQueue.value.length - 1))
  const patch = nfAssistantPatchQueue.value[nfAssistantPatchIndex.value]
  if (patch.status && patch.status !== 'pending') return

  const range = nfAssistantLocatePatch(patch)
  if (!range) {
    patch.status = 'conflict'
    ElMessage.warning(`建議 #${nfAssistantPatchIndex.value + 1} 無法自動定位，已標記爲衝突`)
    nfAssistantOpenNextPending(nfAssistantPatchIndex.value + 1)
    return
  }

  const original = view.state.doc.sliceString(range.from, range.to)
  const newText = String(patch.new_text ?? '')
  patch._from = range.from
  patch._to = range.to

  runWithPendingPreviewMutation(() => {
    view!.dispatch({
      changes: { from: range.to, to: range.to, insert: newText },
      selection: { anchor: range.to + newText.length }
    })
  })

  ;(pendingAiEdit as any).value = {
    originalFrom: range.from,
    originalTo: range.to,
    originalText: original,
    previewFrom: range.to,
    previewTo: range.to + newText.length,
    generating: false,
    source: 'assistant_batch_patch',
    patchId: patch.id ?? patch.index ?? (nfAssistantPatchIndex.value + 1),
  }

  setCompareHighlight(range.from, range.to, range.to, range.to + newText.length)
  nfAssistantScrollToRange(range)
  ElMessage.info(`正在查看建議 #${nfAssistantPatchIndex.value + 1} / ${nfAssistantPatchTotal.value}`)
}

function nfAssistantOpenNextPending(fromIndex: number = nfAssistantPatchIndex.value + 1) {
  if (!nfAssistantPatchQueue.value.length) return
  for (let i = fromIndex; i < nfAssistantPatchQueue.value.length; i++) {
    if (!nfAssistantPatchQueue.value[i].status || nfAssistantPatchQueue.value[i].status === 'pending') {
      nfAssistantOpenPatch(i)
      return
    }
  }
  for (let i = 0; i < fromIndex; i++) {
    if (!nfAssistantPatchQueue.value[i].status || nfAssistantPatchQueue.value[i].status === 'pending') {
      nfAssistantOpenPatch(i)
      return
    }
  }
  nfAssistantPatchQueue.value = []
  nfAssistantPatchIndex.value = 0
}

function nfAssistantHasCurrentBatchPreview(): boolean {
  const p = pendingAiEdit.value as any
  return !!view && !!p && p.source === 'assistant_batch_patch'
}

function nfAssistantIsPendingPatch(patch: NfAssistantPatchItem | undefined): boolean {
  return !!patch && (!patch.status || patch.status === 'pending')
}

function nfAssistantOpenPendingInDirection(direction: -1 | 1) {
  if (!nfAssistantPatchQueue.value.length) return
  let index = nfAssistantPatchIndex.value + direction
  while (index >= 0 && index < nfAssistantPatchQueue.value.length) {
    if (nfAssistantIsPendingPatch(nfAssistantPatchQueue.value[index])) {
      nfAssistantOpenPatch(index)
      return
    }
    index += direction
  }
}

function nfAssistantPatchPrev() {
  nfAssistantOpenPendingInDirection(-1)
}

function nfAssistantPatchNext() {
  nfAssistantOpenPendingInDirection(1)
}

async function nfAssistantPatchAcceptCurrent() {
  if (!nfAssistantPatchQueue.value.length) {
    acceptPendingAiEdit()
    return
  }
  if (!nfAssistantHasCurrentBatchPreview()) {
    ElMessage.warning('當前沒有可接受的批量建議預覽')
    return
  }
  const idx = nfAssistantPatchIndex.value
  acceptPendingAiEdit()
  if (pendingAiEdit.value) return
  if (nfAssistantPatchQueue.value[idx]) nfAssistantPatchQueue.value[idx].status = 'accepted'
  nfAssistantOpenNextPending(idx + 1)
}

async function nfAssistantPatchRejectCurrent() {
  if (!nfAssistantPatchQueue.value.length) {
    rejectPendingAiEdit()
    return
  }
  if (!nfAssistantHasCurrentBatchPreview()) {
    ElMessage.warning('當前沒有可拒絕的批量建議預覽')
    return
  }
  const idx = nfAssistantPatchIndex.value
  rejectPendingAiEdit()
  if (pendingAiEdit.value) return
  if (nfAssistantPatchQueue.value[idx]) nfAssistantPatchQueue.value[idx].status = 'rejected'
  nfAssistantOpenNextPending(idx + 1)
}

function nfAssistantHandlePatchBatchEvent(event: Event) {
  const detail = (event as CustomEvent).detail
  if (!detail || detail.kind !== 'assistant_text_patch_batch' || !Array.isArray(detail.patches)) return

  const currentId = nfAssistantCurrentCardId()
  const targetId = Number(detail.card_id)
  if (currentId && targetId && currentId !== targetId) {
    console.warn(`Patch proposals target card #${targetId}, current card #${currentId}`)
    return
  }
  if (pendingAiEdit.value && (pendingAiEdit.value as any).source !== 'assistant_batch_patch') {
    ElMessage.warning('請先接受或拒絕當前替換建議')
    return
  }

  nfAssistantPatchQueue.value = detail.patches.map((p: any, i: number) => ({
    ...p,
    id: p.id ?? i + 1,
    index: i + 1,
    status: 'pending',
  }))
  nfAssistantPatchIndex.value = 0
  nfAssistantOpenPatch(0)
}

onMounted(() => {
  window.addEventListener('nf-assistant-text-patch-batch', nfAssistantHandlePatchBatchEvent as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('nf-assistant-text-patch-batch', nfAssistantHandlePatchBatchEvent as EventListener)
})
/* NF_ASSISTANT_BATCH_PATCH_END */

</script>

<style scoped>
/* 提示詞下拉菜單項 */
.prompt-item {
	display: flex;
	justify-content: space-between;
	align-items: center;
	width: 100%;
}

.check-icon {
	color: var(--el-color-primary);
	font-size: 16px;
	margin-left: 8px;
}

/* 高亮選中的提示詞 */
:deep(.is-selected) {
	background-color: var(--el-color-primary-light-9);
	color: var(--el-color-primary);
	font-weight: 600;
}

/* 最外層容器：固定高度，防止整體滾動 */
.chapter-studio {
	display: flex;
	flex-direction: column;
	height: 100%;
	min-height: 0;
	overflow: hidden; /* 關鍵：防止整體滾動 */
}

.toolbar {
	padding: 8px 8px; /* 灰色區域與內部白框上下左右間距保持一致 */
	border-bottom: 1px solid var(--el-border-color-light);
	background: var(--el-fill-color-lighter);
	display: flex;
	flex-direction: column;
	gap: 8px;
	flex-shrink: 0;
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.toolbar-row {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: nowrap;
	overflow-x: auto;
	overflow-y: hidden;
	scrollbar-width: thin;
}

.toolbar-status-row {
	display: flex;
	align-items: center;
	gap: 12px;
	min-width: 0;
}

.toolbar-status-spacer {
	flex: 1 1 auto;
	min-width: 0;
}

.toolbar-divider {
	width: 1px;
	height: 20px;
	background: var(--el-border-color-light);
	margin: 0 4px;
}

.toolbar-group {
	display: flex;
	align-items: center;
	gap: 6px;
	padding: 4px 10px;
	background: var(--el-fill-color-blank);
	border-radius: 6px;
	border: 1px solid var(--el-border-color-lighter);
}

.toolbar-group-ai {
	gap: 8px;
	flex: 0 0 auto;
	min-width: 0;
	padding: 8px 12px;
}

.group-label {
	font-size: 12px;
	color: var(--el-text-color-secondary);
	margin-right: 4px;
	font-weight: 500;
}

.flex-spacer {
	flex-grow: 1;
}

.ai-action-bar {
	display: flex;
	align-items: center;
	gap: 8px;
	flex-wrap: nowrap;
	flex: 0 0 auto;
}

.ai-config-entry {
	max-width: none;
	width: auto;
	margin-right: 0;
}

.ai-status-strip {
	display: flex;
	flex-wrap: nowrap;
	gap: 8px;
	flex: 0 0 auto;
	max-width: 100%;
	overflow-x: auto;
	overflow-y: hidden;
	scrollbar-width: none;
}

.ai-status-strip::-webkit-scrollbar {
	display: none;
}

.status-pill {
	display: inline-flex;
	align-items: center;
	padding: 4px 10px;
	border-radius: 999px;
	border: 1px solid var(--el-border-color-lighter);
	background: var(--el-fill-color-light);
	color: var(--el-text-color-secondary);
	font-size: 12px;
	line-height: 1.5;
	white-space: nowrap;
}

.review-button-label {
	display: inline-flex;
	align-items: center;
	gap: 6px;
}

.review-loading-icon {
	animation: review-spin 1s linear infinite;
}

.prompt-settings-panel {
	display: flex;
	flex-direction: column;
	gap: 12px;
}

.prompt-settings-title {
	font-size: 13px;
	font-weight: 600;
	color: var(--el-text-color-primary);
}

.prompt-settings-item {
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.prompt-settings-item label {
	font-size: 12px;
	color: var(--el-text-color-secondary);
}

.editor-content-wrapper {
	flex: 1;
	display: flex;
	flex-direction: column;
	min-height: 0; /* 允許flex子元素正確收縮 */
	overflow: hidden; /* 防止wrapper本身滾動 */
}

.chapter-header {
	padding: 16px 32px 14px;
	border-bottom: 1px solid var(--el-border-color-light);
	background: var(--el-fill-color-lighter);
	display: flex;
	align-items: center;
	flex-shrink: 0;
}

.title-section {
	flex: 1;
	display: flex;
	align-items: center;
	gap: 16px;
}

.chapter-title {
	margin: 0;
	font-size: 28px;
	font-weight: 600;
	color: var(--el-text-color-primary);
	line-height: 1.4;
	outline: none;
	padding: 6px 12px;
	border-radius: 6px;
	transition: all 0.2s ease;
	cursor: text;
	flex: 1;
	caret-color: var(--el-color-primary);
}

.chapter-title:hover {
	background-color: var(--el-fill-color-light);
}

.chapter-title:focus {
	background-color: var(--el-fill-color);
	box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}

.title-meta {
	display: flex;
	align-items: center;
	gap: 6px;
	color: var(--el-text-color-secondary);
	font-size: 14px;
	white-space: nowrap;
}

.word-count-icon {
	font-size: 16px;
}

.word-count-text {
	font-weight: 500;
}

.editor-content {
	flex: 1 1 0; /* flex-basis爲0，避免被內容撐開 */
	min-height: 0; /* 允許flex子元素正確收縮和滾動 */
	overflow: hidden;
	background-color: var(--el-bg-color);
	position: relative;
}

.ai-replace-review-bar {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 12px;
	padding: 8px 12px;
	border-top: 1px solid var(--el-border-color-light);
	background: var(--el-fill-color-lighter);
}

.review-hint {
	font-size: 12px;
	color: var(--el-text-color-secondary);
}

.review-actions {
	display: flex;
	gap: 8px;
}

.review-dialog-footer {
	display: flex;
	justify-content: flex-end;
	gap: 8px;
}

/* CodeMirror 內部樣式 */
.editor-content :deep(.cm-editor) {
	height: 100% !important; /* 強制佔滿容器高度，不自動擴展 */
	outline: none;
	line-height: 1.8;
	color: var(--el-text-color-primary);
	background-color: transparent;
}

/* 確保 CodeMirror 的滾動容器正確工作 */
.editor-content :deep(.cm-scroller) {
	overflow-y: auto !important; /* 強制垂直滾動 */
	overflow-x: auto !important;
	max-height: 100% !important; /* 防止超出父容器 */
}
.editor-content :deep(.cm-content) {
	padding: 20px;
	color: var(--el-text-color-primary);
	font-size: v-bind(fontSizePx);
	line-height: v-bind(lineHeightStr);
	caret-color: var(--el-color-primary);
}

.editor-content :deep(.cm-line) {
	caret-color: inherit;
}

.editor-content :deep(.cm-gutters) {
	background: var(--el-fill-color-lighter);
	color: var(--el-text-color-secondary);
	border-right: 1px solid var(--el-border-color-light);
}

.editor-content :deep(.cm-lineNumbers .cm-gutterElement) {
	padding: 0 10px 0 8px;
	font-size: 12px;
}

.editor-content :deep(.cm-cursor),
.editor-content :deep(.cm-dropCursor) {
	border-left-color: var(--el-color-primary) !important;
}

.editor-content :deep(.cm-cursorLayer .cm-cursor) {
	border-left-width: 2px !important;
	box-shadow: 0 0 0 1px color-mix(in srgb, var(--el-color-primary) 38%, transparent);
}

.editor-content :deep(.cm-selectionBackground) {
	background: color-mix(in srgb, var(--el-color-primary) 20%, transparent) !important;
}

/* 取消高亮行背景，保證純文本閱讀觀感 */
.editor-content :deep(.cm-activeLine) {
	background-color: transparent;
}
.role-block { margin-bottom: 16px; }
.cat-title { font-weight: 600; margin: 8px 0; }
.preview-entity-name-input {
	margin-bottom: 10px;
	max-width: 320px;
}
.preview-read-field {
	min-height: 32px;
	padding: 6px 10px;
	border: 1px solid transparent;
	border-radius: 8px;
	background: transparent;
	color: var(--el-text-color-primary);
	line-height: 1.6;
	cursor: text;
	transition: background-color .18s ease, border-color .18s ease;
}

.preview-read-field:hover {
	background: var(--el-fill-color-light);
	border-color: var(--el-border-color-lighter);
}

.preview-read-field--title {
	margin-bottom: 10px;
	max-width: 320px;
	font-weight: 600;
}

.preview-read-field--multiline {
	min-height: 52px;
	white-space: normal;
}

.preview-read-field__line + .preview-read-field__line {
	margin-top: 4px;
}

.preview-table :deep(.el-input__wrapper),
.preview-table :deep(.el-textarea__inner),
.preview-table :deep(.el-select__wrapper) {
	background: transparent;
	box-shadow: none;
	border-radius: 8px;
}

.preview-table :deep(.el-input__wrapper:hover),
.preview-table :deep(.el-textarea__inner:hover),
.preview-table :deep(.el-select__wrapper:hover) {
	background: var(--el-fill-color-light);
	box-shadow: 0 0 0 1px var(--el-border-color-lighter);
}

.preview-table :deep(.el-input.is-focus .el-input__wrapper),
.preview-table :deep(.el-select.is-focus .el-select__wrapper),
.preview-table :deep(.el-textarea__inner:focus) {
	background: var(--el-bg-color);
	box-shadow: 0 0 0 1px var(--el-color-primary);
}

.preview-table :deep(.el-table__cell) {
	vertical-align: top;
}

.preview-evidence-editor {
	display: flex;
	flex-direction: column;
	gap: 8px;
	padding: 4px 0;
}

.preview-evidence-summary {
	min-width: 260px;
}

.preview-evidence-item {
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.preview-evidence-item__label {
	font-size: 12px;
	color: var(--el-text-color-secondary);
}
.preview-block {
	background: var(--el-fill-color-light);
	padding: 12px;
	border-radius: 6px;
	max-height: 60vh;
	overflow: auto;
}
.event-meta {
	color: var(--el-text-color-secondary);
	margin-left: 8px;
}

.preview-writeback-note {
	padding: 10px 12px;
	margin-bottom: 16px;
	border-radius: 8px;
	background: var(--el-fill-color-light);
	color: var(--el-text-color-secondary);
	font-size: 13px;
	line-height: 1.6;
}

.preview-bottom-tip {
	margin-top: 16px;
}

.preview-dialog-header {
	display: flex;
	flex-direction: column;
	gap: 4px;
}

.preview-dialog-header__title {
	font-size: 16px;
	font-weight: 600;
	color: var(--el-text-color-primary);
}

.preview-dialog-header__note {
	font-size: 12px;
	line-height: 1.5;
	color: var(--el-text-color-secondary);
}

.missing-card-panel {
	margin-bottom: 16px;
}

.participant-review-panel {
	margin-bottom: 16px;
}

.missing-card-list {
	display: flex;
	flex-direction: column;
	gap: 8px;
	margin-top: 12px;
}

.missing-card-item {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 10px 12px;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	background: var(--el-fill-color-light);
}

.review-dialog-body {
	display: flex;
	flex-direction: column;
	gap: 18px;
	max-height: 72vh;
	overflow: auto;
}

.review-overview {
	padding: 16px;
	border-radius: 10px;
	background: var(--el-fill-color-light);
	border: 1px solid var(--el-border-color-lighter);
}

.review-overview-main {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-bottom: 10px;
}

.review-score {
	font-size: 14px;
	color: var(--el-text-color-secondary);
	font-weight: 600;
}

.review-summary {
	margin: 0;
	line-height: 1.7;
	color: var(--el-text-color-primary);
}

.review-text-block {
	padding: 16px;
	border-radius: 10px;
	border: 1px solid var(--el-border-color-lighter);
	background: var(--el-bg-color);
}

:deep(.review-markdown) {
	color: var(--el-text-color-primary);
	font-size: 14px;
	line-height: 1.8;
	word-break: break-word;
}

:deep(.review-markdown h1),
:deep(.review-markdown h2),
:deep(.review-markdown h3),
:deep(.review-markdown h4),
:deep(.review-markdown h5),
:deep(.review-markdown h6) {
	margin-top: 0;
	color: var(--el-text-color-primary);
}

:deep(.review-markdown p),
:deep(.review-markdown li),
:deep(.review-markdown blockquote) {
	color: var(--el-text-color-primary);
}

:deep(.review-markdown pre) {
	background: var(--el-fill-color-extra-light);
	border: 1px solid var(--el-border-color-lighter);
}

:deep(.review-markdown code) {
	background: var(--el-fill-color-light);
	color: var(--el-text-color-primary);
}

/* 右鍵快速編輯菜單 */
.context-menu-popup {
	position: fixed;
	z-index: 9999;
	background: var(--el-bg-color-overlay);
	border: 1px solid var(--el-border-color);
	border-radius: 8px;
	box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
	padding: 12px;
	min-width: 280px;
	max-width: 400px;
	animation: fadeInScale 0.15s ease-out;
}

@keyframes fadeInScale {
	from {
		opacity: 0;
		transform: scale(0.95);
	}
	to {
		opacity: 1;
		transform: scale(1);
	}
}

.context-menu-compact {
	display: flex;
	justify-content: center;
	gap: 8px;
}

.context-menu-expanded {
	display: flex;
	flex-direction: column;
}

.context-menu-actions {
	display: flex;
	gap: 8px;
	justify-content: space-between;
}

.context-menu-actions .el-button {
	flex: 1;
}

.prompt-picker-panel {
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.prompt-picker-caption {
	font-size: 12px;
	color: var(--el-text-color-secondary);
}

.prompt-picker-list {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	background: var(--el-bg-color);
}

.prompt-picker-item {
	width: 100%;
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	padding: 8px 10px;
	border: 0;
	background: transparent;
	color: var(--el-text-color-primary);
	font-size: 13px;
	text-align: left;
	cursor: pointer;
}

.prompt-picker-item:hover {
	background: var(--el-fill-color-light);
}

.prompt-picker-item.is-active {
	background: var(--el-color-primary-light-9);
	color: var(--el-color-primary);
	font-weight: 600;
}

.prompt-picker-empty {
	padding: 18px 12px;
	font-size: 12px;
	text-align: center;
	color: var(--el-text-color-secondary);
}

:deep(.chapter-ai-prompt-popper) {
	padding: 10px !important;
}

:deep(.review-prompt-dropdown .el-scrollbar__wrap) {
	max-height: 320px;
	overflow-y: auto;
}

@keyframes review-spin {
	from { transform: rotate(0deg); }
	to { transform: rotate(360deg); }
}

/* 自定義 AI 高亮效果 */
.editor-content :deep(.cm-ai-highlight) {
	background: linear-gradient(120deg,
		rgba(96, 165, 250, 0.2) 0%,
		rgba(129, 140, 248, 0.2) 50%,
		rgba(96, 165, 250, 0.2) 100%);
	background-size: 200% 100%;
	animation: highlightPulse 2s ease-in-out infinite;
	border-radius: 2px;
	padding: 2px 0;
	box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.3);
}

.editor-content :deep(.cm-ai-original-highlight) {
	background: rgba(148, 163, 184, 0.18);
	color: rgba(100, 116, 139, 0.95);
	border-radius: 2px;
	padding: 2px 0;
	box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.3);
}

.editor-content :deep(.cm-ai-preview-highlight) {
	background: rgba(96, 165, 250, 0.18);
	color: rgba(37, 99, 235, 0.98);
	border-radius: 2px;
	padding: 2px 0;
	box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.35);
}

@keyframes highlightPulse {
	0%, 100% {
		background-position: 0% 50%;
	}
	50% {
		background-position: 100% 50%;
	}
}

/* 暗色模式下的高亮 */
.dark .editor-content :deep(.cm-ai-highlight) {
	background: linear-gradient(120deg,
		rgba(59, 130, 246, 0.25) 0%,
		rgba(99, 102, 241, 0.25) 50%,
		rgba(59, 130, 246, 0.25) 100%);
	background-size: 200% 100%;
	box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.4);
}

.dark .editor-content :deep(.cm-ai-original-highlight) {
	background: rgba(100, 116, 139, 0.26);
	color: rgba(203, 213, 225, 0.95);
	box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.45);
}

.dark .editor-content :deep(.cm-ai-preview-highlight) {
	background: rgba(59, 130, 246, 0.24);
	color: rgba(147, 197, 253, 0.98);
	box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.45);
}

.dark .chapter-title {
	caret-color: #93c5fd;
}

.dark .editor-content :deep(.cm-gutters) {
	background: color-mix(in srgb, var(--el-fill-color-darker) 86%, #0f172a);
	color: var(--el-text-color-secondary);
	border-right-color: var(--el-border-color);
}

.dark .editor-content :deep(.cm-selectionBackground) {
	background: rgba(59, 130, 246, 0.28) !important;
}

.dark .editor-content,
.dark .editor-content :deep(.cm-editor),
.dark .editor-content :deep(.cm-scroller) {
	background: #242b36 !important;
}

.dark .editor-content :deep(.cm-content),
.dark .editor-content :deep(.cm-line) {
	caret-color: #ffffff !important;
}

.dark .editor-content :deep(.cm-cursor),
.dark .editor-content :deep(.cm-dropCursor),
.dark .editor-content :deep(.cm-cursorLayer .cm-cursor) {
	border-left-color: #ffffff !important;
	border-left-width: 3px !important;
	box-shadow:
		0 0 0 1px rgba(255, 255, 255, 0.45),
		0 0 12px rgba(191, 219, 254, 0.58);
}
</style>
