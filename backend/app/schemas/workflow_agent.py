from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowAgentMode(str, Enum):
    SUGGEST = "suggest"
    AUTO_APPLY = "auto_apply"


class WorkflowAgentChatRequest(BaseModel):
    workflow_id: int = Field(description="當前編輯工作流 ID")
    llm_config_id: int = Field(description="用於對話的 LLM 配置 ID")
    user_prompt: str = Field(default="", description="用戶輸入")
    mode: WorkflowAgentMode = Field(default=WorkflowAgentMode.SUGGEST, description="工作模式")
    conversation_id: Optional[str] = Field(default=None, description="會話 ID")

    temperature: Optional[float] = Field(default=None, description="採樣溫度")
    max_tokens: Optional[int] = Field(default=None, description="最大輸出 token")
    timeout: Optional[float] = Field(default=None, description="超時時間（秒）")
    thinking_enabled: Optional[bool] = Field(default=None, description="是否啓用推理輸出")
    react_mode_enabled: Optional[bool] = Field(default=None, description="是否啓用 React 文本協議模式")
    history_messages: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="前端傳入的會話歷史（簡化版），每項包含 role/content",
    )
    pending_code: Optional[str] = Field(
        default=None,
        description="前端當前未應用補丁對應的候選工作流代碼（若有）",
    )


class WorkflowPatchOp(BaseModel):
    op: str = Field(description="補丁操作類型")
    target_node: Optional[str] = Field(default=None, description="目標節點變量名")
    new_code: Optional[str] = Field(default=None, description="整份工作流代碼（replace_code 時使用）")
    new_block: Optional[str] = Field(default=None, description="插入的新節點塊")
    new_meta: Optional[Dict[str, Any]] = Field(default=None, description="更新後的節點元數據字段")
    new_call: Optional[str] = Field(default=None, description="更新後的節點調用表達式")
    old_name: Optional[str] = Field(default=None, description="重命名前舊變量")
    new_name: Optional[str] = Field(default=None, description="重命名後新變量")
    reason: Optional[str] = Field(default=None, description="操作原因")


class WorkflowPatchRequest(BaseModel):
    base_revision: str = Field(description="補丁基線版本")
    patch_ops: List[WorkflowPatchOp] = Field(default_factory=list, description="補丁操作列表")
    dry_run: bool = Field(default=False, description="是否僅預覽不落庫")


class WorkflowPatchResponse(BaseModel):
    success: bool
    workflow_id: int
    base_revision: str
    new_revision: Optional[str] = None
    applied_ops: int = 0
    changed_nodes: List[str] = Field(default_factory=list)
    diff: str = ""
    new_code: str = ""
    parse_result: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
