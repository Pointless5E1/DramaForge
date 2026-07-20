"""指令流生成相關的數據模型

定義了指令格式、生成請求和響應等數據結構。
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


# ==================== 指令格式定義 ====================

class InstructionBase(BaseModel):
    """指令基類"""
    op: str = Field(..., description="指令操作類型")


class SetInstruction(InstructionBase):
    """設置字段值指令"""
    op: Literal["set"] = "set"
    path: str = Field(..., description="JSON Pointer 格式的字段路徑，如 /name 或 /config/theme")
    value: Any = Field(..., description="要設置的值，可以是任意類型")


class AppendInstruction(InstructionBase):
    """向數組追加元素指令"""
    op: Literal["append"] = "append"
    path: str = Field(..., description="JSON Pointer 格式的數組路徑")
    value: Any = Field(..., description="要追加的元素")


class DoneInstruction(InstructionBase):
    """生成完成標誌指令"""
    op: Literal["done"] = "done"


# 聯合類型：所有指令類型
Instruction = SetInstruction | AppendInstruction | DoneInstruction


# ==================== 生成配置 ====================

class GenerationConfig(BaseModel):
    """卡片生成配置
    
    定義瞭如何生成卡片內容的策略和提示。
    """
    mode: Literal["instruction_stream"] = Field(
        default="instruction_stream",
        description="生成模式，當前僅支持指令流模式"
    )
    prompt_template: Optional[str] = Field(
        default=None,
        description="全局提示詞模板（可選）"
    )
    field_hints: Optional[Dict[str, str]] = Field(
        default=None,
        description="字段級生成提示，鍵爲字段路徑，值爲提示文本"
    )
    field_order: Optional[List[str]] = Field(
        default=None,
        description="建議的字段生成順序"
    )
    custom: Optional[Dict[str, Any]] = Field(
        default=None,
        description="自定義配置（擴展用）"
    )


# ==================== API 請求/響應模型 ====================

class ConversationMessage(BaseModel):
    """對話消息"""
    role: Literal["system", "user", "assistant"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息內容")


class InstructionGenerateRequest(BaseModel):
    """指令流生成請求"""
    
    # LLM 配置
    llm_config_id: int = Field(..., description="LLM 配置 ID")
    
    # 用戶輸入
    user_prompt: str = Field(default="", description="用戶輸入的提示詞或回覆")
    
    # Schema 定義
    response_model_schema: Dict[str, Any] = Field(..., description="目標數據結構的 JSON Schema")
    
    # 當前數據狀態
    current_data: Dict[str, Any] = Field(default_factory=dict, description="當前已生成的數據")
    
    # 對話上下文
    conversation_context: List[ConversationMessage] = Field(
        default_factory=list,
        description="對話歷史（前端維護）"
    )
    
    # 生成配置（可選）
    generation_config: Optional[GenerationConfig] = Field(
        default=None,
        description="生成配置，如果爲空則使用默認配置"
    )
    
    # 提示詞模板（可選，覆蓋默認）
    prompt_template: Optional[str] = Field(
        default=None,
        description="自定義提示詞模板"
    )
    
    # 上下文信息（可選）
    context_info: Optional[str] = Field(
        default=None,
        description="上下文注入信息（如相關實體、已有卡片等）"
    )

    # 可選的關係圖裝配範圍。劇本正文管線使用這些字段，按參與實體
    # 查詢事實子圖並合併到 context_info；其他卡片生成請求可不提供。
    project_id: Optional[int] = Field(default=None, description="專案 ID，用於查詢關係圖")
    volume_number: Optional[int] = Field(default=None, description="卷號或劇本集數")
    chapter_number: Optional[int] = Field(default=None, description="章節號或劇本片段號")
    participants: List[str] = Field(default_factory=list, description="參與實體名稱列表")
    
    # 採樣參數
    temperature: Optional[float] = Field(default=0.7, description="採樣溫度")
    max_tokens: Optional[int] = Field(default=None, description="最大生成 token 數")
    timeout: Optional[float] = Field(default=150, description="超時時間（秒）")
    
    # 依賴數據（如實體名列表）
    deps: Optional[str] = Field(default=None, description="依賴數據，用於校驗")


# ==================== SSE 事件類型 ====================

class ThinkingEvent(BaseModel):
    """思考事件（AI 的自然語言輸出）"""
    type: Literal["thinking"] = "thinking"
    text: str = Field(..., description="思考內容或提問")


class InstructionEvent(BaseModel):
    """指令事件（已校驗的指令）"""
    type: Literal["instruction"] = "instruction"
    instruction: Instruction = Field(..., description="指令對象")


class WarningEvent(BaseModel):
    """警告事件（非致命錯誤）"""
    type: Literal["warning"] = "warning"
    text: str = Field(..., description="警告信息")


class ErrorEvent(BaseModel):
    """錯誤事件（致命錯誤）"""
    type: Literal["error"] = "error"
    text: str = Field(..., description="錯誤信息")


class DoneEvent(BaseModel):
    """完成事件"""
    type: Literal["done"] = "done"
    success: bool = Field(default=True, description="是否成功完成")
    message: Optional[str] = Field(default=None, description="完成消息")


# 聯合類型：所有事件類型
StreamEvent = ThinkingEvent | InstructionEvent | WarningEvent | ErrorEvent | DoneEvent
