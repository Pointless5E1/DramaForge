/**
 * 指令流生成相關的類型定義
 * 
 * 與後端的 Pydantic 模型保持一致
 */

// ==================== 指令格式定義 ====================

/**
 * 指令操作類型
 */
export type InstructionOp = 'set' | 'append' | 'done'

/**
 * 基礎指令接口
 */
export interface InstructionBase {
  op: InstructionOp
}

/**
 * 設置字段值指令
 */
export interface SetInstruction extends InstructionBase {
  op: 'set'
  path: string  // JSON Pointer 格式，如 /name 或 /config/theme
  value: any    // 要設置的值
}

/**
 * 向數組追加元素指令
 */
export interface AppendInstruction extends InstructionBase {
  op: 'append'
  path: string  // JSON Pointer 格式的數組路徑
  value: any    // 要追加的元素
}

/**
 * 生成完成標誌指令
 */
export interface DoneInstruction extends InstructionBase {
  op: 'done'
}

/**
 * 指令聯合類型
 */
export type Instruction = SetInstruction | AppendInstruction | DoneInstruction

// ==================== 生成配置 ====================

/**
 * 卡片生成配置
 */
export interface GenerationConfig {
  mode?: 'instruction_stream'
  prompt_template?: string
  field_hints?: Record<string, string>
  field_order?: string[]
  custom?: Record<string, any>
}

// ==================== API 請求/響應模型 ====================

/**
 * 對話消息
 */
export interface ConversationMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

/**
 * 指令流生成請求
 */
export interface InstructionGenerateRequest {
  llm_config_id: number
  user_prompt?: string
  response_model_schema: Record<string, any>
  current_data?: Record<string, any>
  conversation_context?: ConversationMessage[]
  generation_config?: GenerationConfig
  prompt_template?: string
  context_info?: string
  project_id?: number
  volume_number?: number
  chapter_number?: number
  participants?: string[]
  temperature?: number
  max_tokens?: number
  timeout?: number
  deps?: string
}

// ==================== SSE 事件類型 ====================

/**
 * 思考事件（AI 的自然語言輸出）
 */
export interface ThinkingEvent {
  type: 'thinking'
  text: string
}

/**
 * 指令事件（已校驗的指令）
 */
export interface InstructionEvent {
  type: 'instruction'
  instruction: Instruction
}

/**
 * 警告事件（非致命錯誤）
 */
export interface WarningEvent {
  type: 'warning'
  text: string
}

/**
 * 錯誤事件（致命錯誤）
 */
export interface ErrorEvent {
  type: 'error'
  text: string
}

/**
 * 完成事件
 */
export interface DoneEvent {
  type: 'done'
  success?: boolean
  message?: string
}

/**
 * 流事件聯合類型
 */
export type StreamEvent = ThinkingEvent | InstructionEvent | WarningEvent | ErrorEvent | DoneEvent

// ==================== 生成面板消息類型 ====================

/**
 * 生成面板消息類型
 */
export type GenerationMessageType = 'thinking' | 'action' | 'system' | 'user' | 'warning' | 'error'

/**
 * 生成面板消息
 */
export interface GenerationMessage {
  type: GenerationMessageType
  content: string
  timestamp: number
}
