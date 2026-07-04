"""
工具調用結果的標準化類型定義

使用 Pydantic 定義工具返回值的結構，確保類型安全和字段清晰。
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolResultStatus(str, Enum):
    """工具執行狀態枚舉"""
    SUCCESS = "success"
    FAILED = "failed"
    WARNING = "warning"
    CONFIRMATION_REQUIRED = "confirmation_required"  # 需要用戶確認


class ToolResult(BaseModel):
    """
    工具調用的標準返回格式
    
    所有助手工具都應該返回此格式或其子類，以確保返回值的一致性和可預測性。
    """
    success: bool = Field(description="操作是否成功")
    status: ToolResultStatus = Field(
        default=ToolResultStatus.SUCCESS,
        description="操作狀態"
    )
    message: str = Field(description="給 LLM 的消息（簡潔描述結果）")
    
    # 可選字段
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="返回的數據（如卡片內容、列表等）"
    )
    error: Optional[str] = Field(
        default=None,
        description="錯誤信息（失敗時提供詳細錯誤）"
    )
    
    class Config:
        use_enum_values = True  # 序列化時使用枚舉值


class ConfirmationRequest(ToolResult):
    """
    需要用戶確認的操作請求
    
    當工具需要用戶確認才能執行危險操作時，返回此類型。
    前端應檢測此類型並展示確認對話框。
    """
    success: bool = False
    status: ToolResultStatus = ToolResultStatus.CONFIRMATION_REQUIRED
    
    confirmation_id: str = Field(description="確認請求的唯一ID")
    action: str = Field(description="要執行的操作名稱（如 'delete_card'）")
    action_params: Dict[str, Any] = Field(description="操作的參數")
    warning: Optional[str] = Field(
        default=None,
        description="警告信息（如'此操作不可撤銷'）"
    )
    
    class Config:
        use_enum_values = True


class CardOperationResult(ToolResult):
    """
    卡片操作的返回結果
    
    用於創建、更新、刪除等卡片操作。
    """
    card_id: Optional[int] = Field(default=None, description="卡片ID")
    card_title: Optional[str] = Field(default=None, description="卡片標題")
    card_type: Optional[str] = Field(default=None, description="卡片類型")
    
    # AI 修改狀態
    needs_confirmation: Optional[bool] = Field(
        default=None,
        description="是否需要用戶確認（用於觸發工作流）"
    )
    
    # 對於創建/更新操作
    current_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="卡片的當前數據"
    )
    missing_fields: Optional[List[str]] = Field(
        default=None,
        description="缺失的必填字段路徑列表"
    )
    applied: Optional[int] = Field(
        default=None,
        description="成功執行的指令數"
    )
    failed: Optional[int] = Field(
        default=None,
        description="失敗的指令數"
    )
    
    class Config:
        use_enum_values = True


class CardSearchResult(ToolResult):
    """卡片搜索結果"""
    total: int = Field(default=0, description="搜索到的卡片總數")
    cards: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="卡片列表"
    )
    
    class Config:
        use_enum_values = True


# 輔助函數：將 ToolResult 轉換爲 Dict
def to_dict(result: ToolResult) -> Dict[str, Any]:
    """
    將 ToolResult 對象轉換爲字典（用於 LangChain 工具返回）
    
    Args:
        result: ToolResult 對象
        
    Returns:
        字典格式的結果
    """
    return result.model_dump(exclude_none=True, mode='json')
