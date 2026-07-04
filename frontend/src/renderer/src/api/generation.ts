import { API_BASE_URL } from './request'

import type {
  InstructionGenerateRequest,
  StreamEvent,
  Instruction
} from '@renderer/types/instruction'

/**
 * 生成參數
 */
export interface GenerateParams extends InstructionGenerateRequest {
  // 繼承所有請求參數
}

/**
 * 事件回調函數類型
 */
export interface GenerateCallbacks {
  onThinking?: (text: string) => void
  onInstruction?: (instruction: Instruction) => void
  onWarning?: (text: string) => void
  onError?: (text: string) => void
  onDone?: (success: boolean, message?: string, finalData?: any) => void
}

/**
 * 使用指令流生成
 * 
 * @param params 生成參數
 * @param callbacks 事件回調
 * @param signal 中斷信號（可選）
 */
export async function generateWithInstructionStream(
  params: GenerateParams,
  callbacks: GenerateCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const url = `${API_BASE_URL}/ai/generate/stream`

  try {
    // 發送 POST 請求
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params),
      signal
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP ${response.status}: ${errorText}`)
    }

    if (!response.body) {
      throw new Error('響應體爲空')
    }

    // 讀取 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        break
      }

      // 解碼數據塊
      buffer += decoder.decode(value, { stream: true })

      // 按行分割
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留不完整的行

      for (const line of lines) {
        if (!line.trim()) {
          continue
        }

        // 解析 SSE 格式
        const event = parseSSELine(line)
        if (event) {
          handleEvent(event, callbacks)
        }
      }
    }

    // 處理剩餘的緩衝區
    if (buffer.trim()) {
      const event = parseSSELine(buffer)
      if (event) {
        handleEvent(event, callbacks)
      }
    }
  } catch (error: any) {
    if (error.name === 'AbortError') {
      console.log('生成已中斷')
      return
    }

    console.error('生成失敗:', error)
    callbacks.onError?.(error.message || '生成失敗')
  }
}

/**
 * 解析 SSE 行
 * @param line SSE 格式的行
 * @returns 解析後的事件對象
 */
function parseSSELine(line: string): { event: string; data: any } | null {
  // SSE 格式：event: xxx\ndata: {...}
  // 或者簡化格式：data: {...}

  let eventType = 'message'
  let dataStr = ''

  const lines = line.split('\n')
  for (const l of lines) {
    if (l.startsWith('event:')) {
      eventType = l.slice(6).trim()
    } else if (l.startsWith('data:')) {
      dataStr = l.slice(5).trim()
    }
  }

  if (!dataStr) {
    return null
  }

  try {
    const data = JSON.parse(dataStr)
    return { event: eventType, data }
  } catch (e) {
    console.warn('解析 SSE 數據失敗:', dataStr)
    return null
  }
}

/**
 * 處理事件
 * @param event 事件對象
 * @param callbacks 回調函數
 */
function handleEvent(event: { event: string; data: any }, callbacks: GenerateCallbacks): void {
  const { data } = event
  const type = data.type || event.event

  switch (type) {
    case 'thinking':
      callbacks.onThinking?.(data.text)
      break

    case 'instruction':
      callbacks.onInstruction?.(data.instruction)
      break

    case 'warning':
      callbacks.onWarning?.(data.text)
      break

    case 'error':
      callbacks.onError?.(data.text)
      break

    case 'done':
      callbacks.onDone?.(data.success !== false, data.message, data.final_data)
      break

    default:
      console.warn('未知的事件類型:', type, data)
  }
}
