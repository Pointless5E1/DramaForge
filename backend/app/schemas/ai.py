from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal


ContinuationWordControlMode = Literal["prompt_only", "balanced"]

class ContinuationRequest(BaseModel):
    previous_content: str = Field(default="", description="已寫的章節內容")
    llm_config_id: int
    stream: bool = False
    # 可選上下文字段（向後兼容）
    project_id: Optional[int] = None
    volume_number: Optional[int] = None
    chapter_number: Optional[int] = None
    participants: Optional[List[str]] = None
    # 採樣與超時（可選）
    temperature: Optional[float] = Field(default=None, description="採樣溫度 0-2，留空使用模型默認")
    max_tokens: Optional[int] = Field(default=None, description="生成的最大token數，留空使用默認")
    timeout: Optional[float] = Field(default=None, description="生成超時(秒)，留空使用默認")
    # 上下文信息（引用上下文 + 事實子圖）
    context_info: Optional[str] = Field(default=None, description="上下文信息，包括引用內容和事實子圖")
    # 已有內容字數統計（用於指導續寫長度）
    existing_word_count: Optional[int] = Field(default=None, description="已有章節正文的字數統計")
    target_word_count: Optional[int] = Field(default=None, description="目標總字數")
    word_control_mode: Optional[ContinuationWordControlMode] = Field(
        default=None,
        description="字數控制模式：prompt_only / balanced",
    )
    continuation_guidance: Optional[str] = Field(default=None, description="續寫指導要求")
    budget_round_hint: Optional[int] = Field(default=None, description="預算運行時回灌的當前輪次提示")
    remaining_word_count_hint: Optional[int] = Field(default=None, description="預算運行時回灌的剩餘字數提示")
    is_final_round_hint: Optional[bool] = Field(default=None, description="預算運行時回灌的最後一輪標記")
    # 參數卡選擇的提示詞名稱（優先使用該提示詞作爲系統提示詞）
    prompt_name: Optional[str] = Field(default=None, description="參數卡選擇的提示詞名稱")
    # 是否追加"直接輸出連續的小說正文"尾綴（默認 True 兼容原有續寫）
    append_continuous_novel_directive: bool = Field(default=True, description="是否追加連續小說正文指令")

class ContinuationResponse(BaseModel):
    content: str


class AssistantChatRequest(BaseModel):
    """靈感助手對話請求（新格式）"""
    # 新格式：前端發送統一的上下文信息和用戶輸入
    context_info: str = Field(description="完整的項目上下文信息（包含項目結構、操作歷史、引用卡片等）")
    user_prompt: str = Field(default="", description="用戶當前輸入（可爲空）")
    
    # 必需字段
    project_id: int = Field(description="項目ID（用於工具調用作用域）")
    llm_config_id: int = Field(description="LLM配置ID")
    prompt_name: str = Field(default="靈感對話", description="系統提示詞名稱")
    
    # 可選參數
    temperature: Optional[float] = Field(default=None, description="採樣溫度 0-2")
    max_tokens: Optional[int] = Field(default=None, description="最大token數")
    timeout: Optional[float] = Field(default=None, description="超時秒數")
    stream: bool = Field(default=True, description="是否流式輸出")
    thinking_enabled: Optional[bool] = Field(default=None, description="是否啓用推理/Thinking 輸出（僅部分模型支持）")
    # 上下文摘要配置（僅靈感助手使用，前端可選傳入）
    context_summarization_enabled: Optional[bool] = Field(default=None, description="是否啓用上下文摘要中間件（對過長對話做摘要壓縮）")
    context_summarization_threshold: Optional[int] = Field(default=None, description="觸發上下文摘要的 token 閾值")
    react_mode_enabled: Optional[bool] = Field(default=None, description="是否啓用 React 文本協議工具調用模式")


class GeneralAIRequest(BaseModel):
    input: Dict[str, Any]
    llm_config_id: Optional[int] = None
    prompt_name: Optional[str] = None
    response_model_name: Optional[Dict[str, Any]] | Optional[str] = None
    response_model_schema: Optional[Dict[str, Any]] = None  # 用於動態創建模型
    # 採樣與超時（可選）
    temperature: Optional[float] = Field(default=None, description="採樣溫度 0-2，留空使用模型默認")
    max_tokens: Optional[int] = Field(default=None, description="生成的最大token數，留空使用默認")
    timeout: Optional[float] = Field(default=None, description="生成超時(秒)，留空使用默認")
    # 前端直接傳入的依賴（JSON 字符串，例如 {\"all_entity_names\":[...]}")
    deps: Optional[str] = Field(default=None, description="依賴注入數據(JSON字符串)，例如實體名稱列表等")
    # 是否過濾 AI 字段（基於 x-ai-exclude 標記）
    exclude_ai_fields: Optional[bool] = Field(default=True, description="是否過濾標記爲 x-ai-exclude 的字段")

    class Config:
        extra = 'ignore'
