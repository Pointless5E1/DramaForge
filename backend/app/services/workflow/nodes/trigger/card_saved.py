"""卡片保存觸發器節點"""
from typing import Optional
from pydantic import BaseModel, Field

from ..base import BaseNode
from ...registry import register_node


class TriggerCardSavedInput(BaseModel):
    """卡片保存觸發器輸入"""
    card_type: Optional[str] = Field(
        None,
        description="卡片類型名稱（可選）。只觸發指定類型的卡片保存，如 '核心藍圖'。留空則匹配所有類型"
    )
    on_create: bool = Field(
        False,
        description="是否在卡片創建時觸發"
    )
    on_update: bool = Field(
        True,
        description="是否在卡片更新時觸發"
    )


class TriggerCardSavedOutput(BaseModel):
    """卡片保存觸發器輸出"""
    card_id: int = Field(..., description="卡片ID")
    project_id: int = Field(..., description="項目ID")
    card_type: Optional[str] = Field(None, description="卡片類型名稱")
    is_created: bool = Field(..., description="是否是新創建的卡片（true=創建，false=更新）")


@register_node
class TriggerCardSavedNode(BaseNode):
    """卡片保存觸發器
    
    當卡片保存時觸發工作流（包括創建和更新）。
    
    輸出字段：
        - card_id: 卡片ID
        - project_id: 項目ID
        - card_type: 卡片類型名稱
        - is_created: 是否是新創建的卡片
    
    過濾條件：
        - card_type: 只觸發指定類型的卡片（可選）
        - on_create: 是否在創建時觸發（默認 false）
        - on_update: 是否在更新時觸發（默認 true）
    
    示例:
        # 監聽所有卡片保存
        trigger = Trigger.CardSaved()
        
        # 只監聽核心藍圖卡片的更新
        trigger = Trigger.CardSaved(
            card_type="核心藍圖",
            on_create=false,
            on_update=true
        )
        
        # 使用觸發器輸出
        card = Card.Get(card_id=trigger.card_id)
        
        # 提取關係
        relations = AI.ExtractRelations(
            card_id=trigger.card_id,
            project_id=trigger.project_id
        )
    """
    
    node_type = "Trigger.CardSaved"
    category = "trigger"
    label = "卡片保存觸發器"
    description = "當卡片保存時觸發"
    
    input_model = TriggerCardSavedInput
    output_model = TriggerCardSavedOutput
    
    async def execute(self, inputs: TriggerCardSavedInput):
        """從上下文中讀取觸發器數據並輸出
        
        觸發器數據在工作流啓動時通過 initial_context["__trigger_data__"] 注入，
        可以通過 self.context.variables 訪問。
        """
        # 從上下文的 variables 中獲取觸發器數據
        trigger_data = self.context.variables.get("__trigger_data__", {})

        card_type = trigger_data.get("card_type")
        if card_type is None:
            card_type = inputs.card_type
        
        yield TriggerCardSavedOutput(
            card_id=trigger_data.get("card_id"),
            project_id=trigger_data.get("project_id"),
            card_type=card_type,
            is_created=trigger_data.get("is_created", False)
        )
