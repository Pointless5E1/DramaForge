"""卡片更新節點"""

from typing import Any, Dict, Optional, AsyncIterator
from pydantic import BaseModel, Field
from sqlalchemy.orm.attributes import flag_modified

from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node


class CardUpdateInput(BaseModel):
    """卡片更新輸入"""
    card_id: Optional[int] = Field(None, description="卡片ID（可選，可從上下文獲取）")
    content_merge: Dict[str, Any] = Field(
        default_factory=dict,
        description="要合併的內容（深度合併到現有內容）"
    )
    title: Optional[str] = Field(
        None,
        description="新標題（可選）"
    )


class CardUpdateOutput(BaseModel):
    """卡片更新輸出"""
    card_id: int = Field(..., description="更新後的卡片ID")
    success: bool = Field(True, description="是否更新成功")


@register_node
class CardUpdateNode(BaseNode):
    """卡片更新節點
    
    更新現有卡片的內容或標題。
    支持深度合併內容，不會覆蓋未指定的字段。
    
    示例：
    1. 清空列表字段：content_merge={"items": []}
    2. 更新嵌套字段：content_merge={"world_view": {"social_system": {"major_power_camps": []}}}
    3. 更新標題：title="新標題"

    嚴格約束（給工作流編寫 Agent）：
    - `content_merge` 必須是可靜態校驗的字面量 dict。
    - 禁止把整個 `content_merge` 寫成 `${...}`、`$expr.result` 或字符串拼接結果。
    - 更新字段必須符合目標卡片 schema，禁止寫入 schema 不存在字段。

    建議先確定目標卡片類型 schema，再構造 `content_merge`。
    """
    
    node_type = "Card.Update"
    category = "card"
    label = "更新卡片"
    description = "更新現有卡片的內容或標題"
    
    input_model = CardUpdateInput
    output_model = CardUpdateOutput
    
    async def execute(self, input_data: CardUpdateInput) -> AsyncIterator[CardUpdateOutput]:
        """執行卡片更新"""
        from sqlmodel import select
        from app.db.models import Card
        
        # 確定卡片ID
        card_id = input_data.card_id
        if not card_id:
            raise ValueError("必須提供 card_id")
        
        # 獲取卡片
        card = self.context.session.get(Card, card_id)
        if not card:
            raise ValueError(f"卡片不存在: card_id={card_id}")
        
        # 更新標題
        if input_data.title:
            card.title = input_data.title
        
        # 深度合併內容
        if input_data.content_merge:
            card.content = self._deep_merge(card.content or {}, input_data.content_merge)
            flag_modified(card, "content")
        
        # 保存
        self.context.session.add(card)
        self.context.session.commit()
        self.context.session.refresh(card)
        
        yield CardUpdateOutput(
            card_id=card.id,
            success=True
        )
    
    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """深度合併字典
        
        Args:
            base: 基礎字典
            update: 更新字典
            
        Returns:
            合併後的字典
        """
        result = base.copy()
        
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 遞歸合併嵌套字典
                result[key] = self._deep_merge(result[key], value)
            else:
                # 直接覆蓋
                result[key] = value
        
        return result
