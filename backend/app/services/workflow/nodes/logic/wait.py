"""Logic.Wait 節點 - 等待異步任務完成"""

from typing import Any, List, Union, AsyncIterator
from pydantic import BaseModel, Field, field_validator

from ...registry import register_node
from ..base import BaseNode


class WaitInput(BaseModel):
    """Wait 節點輸入"""
    input: Any = Field(None, description="輸入數據（透傳）")
    tasks: Union[str, List[str]] = Field(
        ...,
        description="要等待的異步任務變量名（單個或列表）",
        json_schema_extra={
            "x-component": "TaskSelect",
            "x-multiple": True
        }
    )
    
    @field_validator('tasks', mode='before')
    @classmethod
    def normalize_tasks(cls, v):
        """將單個任務轉換爲列表"""
        if isinstance(v, str):
            return [v]
        return v


class WaitOutput(BaseModel):
    """Wait 節點輸出"""
    waited_tasks: List[str] = Field(..., description="已等待的任務列表")
    count: int = Field(..., description="等待的任務數量")


@register_node
class WaitNode(BaseNode[WaitInput, WaitOutput]):
    """等待異步任務完成
    
    用於等待一個或多個異步任務完成後再繼續執行。
    
    示例：
        wait_result = Logic.Wait(tasks=["task_a", "task_b"])
    """
    
    node_type = "Logic.Wait"
    category = "logic"
    label = "等待任務"
    description = "等待一個或多個異步任務完成"
    
    input_model = WaitInput
    output_model = WaitOutput
    
    async def execute(self, inputs: WaitInput) -> AsyncIterator[WaitOutput]:
        """執行等待
        
        注意：實際的等待邏輯在 AsyncExecutor 中處理，
        這裏只是返回一個佔位結果。
        """
        yield WaitOutput(
            waited_tasks=inputs.tasks,
            count=len(inputs.tasks)
        )
