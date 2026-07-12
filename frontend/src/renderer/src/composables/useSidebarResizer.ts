import { ref } from 'vue'

export function useSidebarResizer() {
  const minLeftWidth = 180
  const maxLeftWidth = 400
  const minRightWidth = 280
  const maxRightWidth = 500
  const leftSidebarWidth = ref(285)
  // 讓五個正文工具頁籤（助手、審核、實體、提取、大綱）預設完整可見。
  const rightSidebarWidth = ref(359)
  let resizing = ref<'left' | 'right' | null>(null)
  let startX = 0
  let startWidth = 0

  function startResizing(side: 'left' | 'right') {
    resizing.value = side
    startX = window.event instanceof MouseEvent ? window.event.clientX : 0
    startWidth = side === 'left' ? leftSidebarWidth.value : rightSidebarWidth.value
    document.body.style.cursor = 'col-resize'
    window.addEventListener('mousemove', handleResizing)
    window.addEventListener('mouseup', stopResizing)
  }

  function handleResizing(e: MouseEvent) {
    if (!resizing.value) return
    if (resizing.value === 'left') {
      let newWidth = startWidth + (e.clientX - startX)
      newWidth = Math.max(minLeftWidth, Math.min(maxLeftWidth, newWidth))
      leftSidebarWidth.value = newWidth
    } else if (resizing.value === 'right') {
      let newWidth = startWidth - (e.clientX - startX)
      newWidth = Math.max(minRightWidth, Math.min(maxRightWidth, newWidth))
      rightSidebarWidth.value = newWidth
    }
  }

  function stopResizing() {
    resizing.value = null
    document.body.style.cursor = ''
    window.removeEventListener('mousemove', handleResizing)
    window.removeEventListener('mouseup', stopResizing)
  }

  return {
    leftSidebarWidth,
    rightSidebarWidth,
    startResizing
  }
}
