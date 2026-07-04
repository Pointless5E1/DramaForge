from typing import Any, Dict, Optional, AsyncIterator
from loguru import logger
from pydantic import BaseModel, Field

from app.db.models import Card
from ...registry import register_node
from ..base import BaseNode, get_card_type_by_name


class CardCreateInput(BaseModel):
    """創建卡片輸入"""
    project_id: int = Field(..., description="項目ID（必須顯式傳遞）")
    card_type: str = Field(..., description="卡片類型名稱")
    title: str = Field(..., description="卡片標題")
    content: Dict[str, Any] = Field(default_factory=dict, description="卡片內容")
    parent: Optional[Dict[str, Any]] = Field(None, description="父卡片")


class CardCreateOutput(BaseModel):
    """創建卡片輸出
    
    直接返回卡片字段（扁平結構），便於後續節點訪問。
    """
    id: int = Field(..., description="卡片ID")
    title: str = Field(..., description="卡片標題")
    content: Dict[str, Any] = Field(..., description="卡片內容")
    card_type_id: int = Field(..., description="卡片類型ID")
    parent_id: Optional[int] = Field(None, description="父卡片ID")


@register_node
class CardCreateNode(BaseNode[CardCreateInput, CardCreateOutput]):
    """創建卡片節點。

    嚴格約束（給工作流編寫 Agent）：
    1) `content` 必須是字面量 dict（可靜態校驗），不要把整個 content 寫成字符串、`${...}` 或 `Logic.Expression.result`。
    2) 寫入前應先確認目標卡片類型 schema（字段名、必填項、字段類型），禁止臆造字段。
    3) 若需要動態內容，請在字段值層面引用已知輸出字段，避免整體對象動態拼裝。

    推薦流程：
    - 先查詢卡片類型 schema
    - 再按 schema 構造 `content={...}`
    """
    node_type = "Card.Create"
    category = "card"
    label = "創建卡片"
    description = "創建新卡片"
    
    input_model = CardCreateInput
    output_model = CardCreateOutput

    async def execute(self, inputs: CardCreateInput) -> AsyncIterator[CardCreateOutput]:
        """創建卡片節點"""
        # 1. 準備數據
        title = inputs.title
        if not title:
            raise ValueError("未提供卡片標題")

        content = inputs.content or {}
        
        # 檢查卡片類型
        card_type = get_card_type_by_name(self.context.session, inputs.card_type)
        if not card_type:
            raise ValueError(f"卡片類型不存在: {inputs.card_type}")
        
        # 使用顯式傳遞的 project_id
        project_id = inputs.project_id
        
        parent_data = inputs.parent or {}
        parent_id = parent_data.get("id")
        
        # 使用 CardService 創建卡片
        from app.services.card_service import CardService
        from app.schemas.card import CardCreate
        
        card_service = CardService(self.context.session)
        
        try:
            card_in = CardCreate(
                title=title,
                content=content,
                card_type_id=card_type.id,
                parent_id=parent_id,
                project_id=project_id
            )
            card = card_service.create(card_in, project_id)
            
        except Exception as e:
            logger.error(f"[Card.Create] 創建失敗: {e}")
            raise
        
        # 記錄受影響的卡片
        touched = self.context.variables.setdefault("touched_card_ids", [])
        if card.id not in touched:
            touched.append(card.id)
        
        logger.info(
            f"[Card.Create] 創建卡片: id={card.id}, title={card.title}, "
            f"type={inputs.card_type}"
        )
        
        yield CardCreateOutput(
            id=card.id,
            title=card.title,
            content=card.content,
            card_type_id=card.card_type_id,
            parent_id=card.parent_id
        )
