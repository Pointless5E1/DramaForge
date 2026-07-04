from typing import Any, Dict, AsyncIterator
from pydantic import Field, BaseModel
from loguru import logger

from ...registry import register_node
from ..base import BaseNode
from ...expressions import evaluate_expression


class LogicAssertInput(BaseModel):
    """斷言節點輸入"""
    condition: str = Field(..., description="斷言條件表達式")
    message: str = Field("斷言失敗", description="失敗時的錯誤消息")


class LogicAssertOutput(BaseModel):
    """斷言節點輸出（空）"""
    pass


@register_node
class LogicAssertNode(BaseNode[LogicAssertInput, LogicAssertOutput]):
    """斷言節點
    
    驗證條件是否爲真，如果爲假則停止工作流執行。
    用於替代 Logic.End 節點，實現條件驗證和提前退出。
    """
    node_type = "Logic.Assert"
    category = "logic"
    label = "斷言"
    description = "驗證條件，失敗則停止工作流"
    
    input_model = LogicAssertInput
    output_model = LogicAssertOutput

    async def execute(self, inputs: LogicAssertInput) -> AsyncIterator[LogicAssertOutput]:
        """執行斷言驗證"""
        try:
            # 準備求值環境
            eval_context = {
                **self.context.variables
            }
            
            # 評估條件表達式
            result = evaluate_expression(inputs.condition, eval_context)
            is_true = bool(result)
            
            if not is_true:
                # 斷言失敗，拋出異常
                logger.error(f"[Assert] 斷言失敗: {inputs.condition} - {inputs.message}")
                raise AssertionError(f"斷言失敗: {inputs.message}")
            
            # 斷言成功，繼續執行
            logger.info(f"[Assert] 斷言通過: {inputs.condition}")
            yield LogicAssertOutput()
        
        except Exception as e:
            if isinstance(e, AssertionError):
                raise
            logger.error(f"[Assert] 條件求值失敗: {e}")
            raise ValueError(f"斷言條件求值失敗: {str(e)}")
