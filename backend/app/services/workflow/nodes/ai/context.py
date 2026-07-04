"""上下文組裝節點

複用 ContextService 爲工作流提供上下文裝配能力。
"""

from typing import Any, Dict, List, Optional, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger

from ...registry import register_node
from ..base import BaseNode
from app.services.context_service import assemble_context, ContextAssembleParams


class ContextAssembleInput(BaseModel):
    """上下文組裝輸入"""
    
    project_id: int = Field(..., description="項目ID（必須顯式傳遞）")
    participants: List[str] = Field(
        default_factory=list,
        description="參與者列表（角色/地點名稱）"
    )


class ContextAssembleOutput(BaseModel):
    """上下文組裝輸出"""
    
    context_text: str = Field(..., description="格式化的上下文文本")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="結構化上下文數據")


#未經校驗，暫時不顯示
# @register_node
class ContextAssembleNode(BaseNode):
    """上下文組裝節點"""
    
    node_type = "Context.Assemble"
    category = "context"
    label = "組裝上下文"
    description = "從知識圖譜中提取事實子圖，爲 LLM 提供結構化上下文"
    input_model = ContextAssembleInput
    output_model = ContextAssembleOutput

    async def execute(self, input_data: ContextAssembleInput) -> AsyncIterator[ContextAssembleOutput]:
        """執行上下文組裝"""
        
        # 使用顯式傳遞的項目ID
        project_id = input_data.project_id
        
        # 構建參數
        params = ContextAssembleParams(
            project_id=project_id,
            participants=input_data.participants,
            volume_number=None,
            chapter_number=None,
            current_draft_tail=None,
        )
        
        # 調用上下文服務
        result = assemble_context(self.context.session, params)
        
        logger.info(
            f"[Context.Assemble] 組裝上下文成功: project_id={project_id}, "
            f"participants={input_data.participants}"
        )
        
        yield ContextAssembleOutput(
            context_text=result.facts_subgraph,
            context_data=result.facts_structured or {},
        )
