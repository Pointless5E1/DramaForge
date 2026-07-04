"""項目創建觸發器節點"""
from typing import Optional
from pydantic import BaseModel, Field

from ..base import BaseNode
from ...registry import register_node


class TriggerProjectCreatedInput(BaseModel):
    """項目創建觸發器輸入"""
    template: Optional[str] = Field(
        None,
        description="模板名稱（可選）。只觸發指定模板的項目創建，如 'snowflake'。留空則匹配所有模板"
    )


class TriggerProjectCreatedOutput(BaseModel):
    """項目創建觸發器輸出"""
    project_id: int = Field(..., description="項目ID")
    template: Optional[str] = Field(None, description="模板名稱（如 'snowflake'）")


@register_node
class TriggerProjectCreatedNode(BaseNode):
    """項目創建觸發器
    
    當新項目創建時觸發工作流。
    
    輸出字段：
        - project_id: 項目ID
        - template: 模板名稱（如果指定了模板）
    
    過濾條件：
        - template: 只觸發指定模板的項目創建（可選）
    
    示例:
        # 監聽所有項目創建
        trigger = Trigger.ProjectCreated()
        
        # 只監聽雪花創作法模板
        trigger = Trigger.ProjectCreated(template="snowflake")
        
        # 使用觸發器輸出
        card = Card.Create(
            project_id=trigger.project_id,
            card_type="核心藍圖",
            title="核心藍圖"
        )
    """
    
    node_type = "Trigger.ProjectCreated"
    category = "trigger"
    label = "項目創建觸發器"
    description = "當新項目創建時觸發"
    
    input_model = TriggerProjectCreatedInput
    output_model = TriggerProjectCreatedOutput
    
    async def execute(self, inputs: TriggerProjectCreatedInput):
        """從上下文中讀取觸發器數據並輸出
        
        觸發器數據在工作流啓動時通過 initial_context["__trigger_data__"] 注入，
        可以通過 self.context.variables 訪問。
        """
        # 從上下文的 variables 中獲取觸發器數據
        trigger_data = self.context.variables.get("__trigger_data__", {})
        
        yield TriggerProjectCreatedOutput(
            project_id=trigger_data.get("project_id"),
            template=trigger_data.get("template")
        )
