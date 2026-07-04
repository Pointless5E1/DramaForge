"""提示詞加載節點

從數據庫加載預設提示詞並渲染模板變量。
"""

from typing import Any, Dict, Optional, Union, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger
from sqlmodel import select

from ...registry import register_node
from ..base import BaseNode
from app.services.prompt_service import get_prompt, render_prompt
from app.db.models import Prompt


class PromptLoadInput(BaseModel):
    """提示詞加載輸入"""
    prompt_id: Union[int, str] = Field(
        ...,
        description="提示詞 ID 或 名稱",
        json_schema_extra={"x-component": "PromptSelect"}
    )
    variables: Optional[Dict[str, Any]] = Field(None, description="模板變量（用於渲染）")


class PromptLoadOutput(BaseModel):
    """提示詞加載輸出"""
    text: str = Field(..., description="渲染後的提示詞文本")


@register_node
class PromptLoadNode(BaseNode[PromptLoadInput, PromptLoadOutput]):
    """提示詞加載節點"""
    
    node_type = "Prompt.Load"
    category = "data"
    label = "加載提示詞"
    description = "從數據庫加載預設提示詞模板"
    
    input_model = PromptLoadInput
    output_model = PromptLoadOutput

    async def execute(self, inputs: PromptLoadInput) -> AsyncIterator[PromptLoadOutput]:
        """執行提示詞加載"""
        variables = inputs.variables or {}
        
        try:
            # 獲取提示詞
            prompt_obj = None
            
            # 支持通過 ID 或 Name 查找
            if isinstance(inputs.prompt_id, int):
                prompt_obj = get_prompt(self.context.session, inputs.prompt_id)
            else:
                # 按名稱查找
                statement = select(Prompt).where(Prompt.name == inputs.prompt_id)
                results = self.context.session.exec(statement)
                prompt_obj = results.first()
            
            if not prompt_obj:
                raise ValueError(f"未找到提示詞: {inputs.prompt_id}")
            
            # 合併全局變量
            template_vars = {
                **self.context.variables,
                **variables,
            }
            
            # 渲染提示詞
            rendered_text = render_prompt(prompt_obj.template, template_vars)
            
            logger.info(
                f"[Prompt.Load] 加載提示詞成功: prompt={inputs.prompt_id}, "
                f"length={len(rendered_text)}"
            )
            
            yield PromptLoadOutput(text=rendered_text)
            
        except Exception as e:
            logger.error(f"[Prompt.Load] 加載提示詞失敗: {e}")
            raise
