<template>
  <div class="card-editor-host">
    <component
      :is="activeEditorComponent"
      :key="editorInstanceKey"
      :card="card"
      :prefetched="prefetched"
      @activate-card="emit('activate-card', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue';
import type { CardRead } from '@renderer/api/cards';

const props = defineProps<{
  card: CardRead;
  prefetched?: any;
}>();

const emit = defineEmits<{
  (e: 'activate-card', cardId: number): void;
}>();

// --- Editor Component Map ---
// This map allows us to resolve a string name to an actual component.
// 只有需要完全自定義外殼的編輯器纔在這裏註冊
// 如果只是內容編輯器不同（如章節正文的 CodeMirrorEditor），
// 應該通過 GenericCardEditor 的 content_editor_component 設定
const editorMap: Record<string, any> = {
  TagsEditor: defineAsyncComponent(() => import('../editors/TagsEditor.vue')),
  ReviewResultCardEditor: defineAsyncComponent(() => import('./ReviewResultCardEditor.vue')),
  // Add other custom editors here in the future
};

// --- Default Editor ---
const GenericCardEditor = defineAsyncComponent(() => import('./GenericCardEditor.vue'));


const activeEditorComponent = computed(() => {
  const customEditorName = props.card.card_type.editor_component;
  if (customEditorName && editorMap[customEditorName]) {
    return editorMap[customEditorName];
  }
  return GenericCardEditor;
});

// 劇本片段共用同一個編輯器實例，捲動切段時只更新資料與全域選取狀態。
// 其他卡片仍沿用逐卡重建，避免改變既有編輯器的生命週期語意。
const editorInstanceKey = computed(() =>
  props.card.card_type?.name === '劇本片段大綱' ? 'screenplay-segment-waterfall' : props.card.id
);
</script>

<style scoped>
.card-editor-host {
  height: 100%;
  width: 100%;
}
</style> 
