import asyncio
from typing import Any, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger

from ...registry import register_node
from ..base import BaseNode


class LogicDelayInput(BaseModel):
    """延遲輸入"""
    input: Any = Field(None, description="輸入數據（透傳）")
    seconds: float = Field(1.0, description="延遲秒數")


class LogicDelayOutput(BaseModel):
    """延遲輸出"""
    output: Any = Field(None, description="輸出數據（透傳）")


@register_node
class LogicDelayNode(BaseNode[LogicDelayInput, LogicDelayOutput]):
    node_type = "Logic.Delay"
    category = "logic"
    label = "延遲"
    description = "延遲指定時間後繼續"
    
    input_model = LogicDelayInput
    output_model = LogicDelayOutput

    async def execute(self, inputs: LogicDelayInput) -> AsyncIterator[LogicDelayOutput]:
        """延遲節點"""
        logger.info(f"[Delay] 延遲 {inputs.seconds} 秒")
        await asyncio.sleep(inputs.seconds)
        
        yield LogicDelayOutput(output=inputs.input)
