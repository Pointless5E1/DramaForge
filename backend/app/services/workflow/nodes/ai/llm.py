"""LLM 生成節點

提供單輪 LLM 調用能力，支持提示詞模板和結構化輸出。
"""

import json
from typing import Any, Dict, Optional, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger

from ...registry import register_node
from ..base import BaseNode
from app.services.ai.core.chat_model_factory import build_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


# ============================================================
# Input/Output Models
# ============================================================

class LLMInput(BaseModel):
    """LLM 生成輸入"""
    user_prompt: str = Field(..., description="用戶提示詞")
    system_prompt: Optional[str] = Field(None, description="系統提示詞")
    llm_config_id: int = Field(..., description="LLM 配置 ID", gt=0)
    temperature: float = Field(0.7, description="溫度參數", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, description="最大生成 token 數", gt=0)
    timeout: int = Field(60, description="超時時間（秒）", gt=0)
    max_retry: int = Field(3, description="最大重試次數", ge=0, le=10)


class LLMOutput(BaseModel):
    """LLM 生成輸出"""
    response: str = Field(..., description="生成的文本")
    usage: Dict[str, Any] = Field(default_factory=dict, description="Token 使用統計")


def _extract_text(value: Any) -> str:
    """將模型返回內容穩健轉換爲純文本，避免 list/dict 觸發 response:str 校驗失敗。"""
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return "".join([part for part in parts if part])

    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text

        content = value.get("content")
        if content is not None:
            extracted = _extract_text(content)
            if extracted:
                return extracted

        for key in ("output_text", "message", "reasoning_content", "value"):
            field_val = value.get(key)
            if field_val is None:
                continue
            extracted = _extract_text(field_val)
            if extracted:
                return extracted

        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            return _extract_text(dumped)
        except Exception:
            pass

    if hasattr(value, "content"):
        try:
            return _extract_text(getattr(value, "content"))
        except Exception:
            pass

    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


# ============================================================
# Node Implementation
# ============================================================

@register_node
class LLMGenerateNode(BaseNode[LLMInput, LLMOutput]):
    """LLM 生成節點"""
    
    node_type = "AI.LLM"
    category = "ai"
    label = "LLM 調用"
    description = "調用大語言模型進行文本生成"
    
    input_model = LLMInput
    output_model = LLMOutput

    async def execute(self, input_data: LLMInput) -> AsyncIterator[LLMOutput]:
        """執行 LLM 調用"""
        
        # 構建 ChatModel (在重試循環外,避免重複構建)
        try:
            model = build_chat_model(
                session=self.context.session,
                llm_config_id=input_data.llm_config_id,
                temperature=input_data.temperature,
                max_tokens=input_data.max_tokens,
                timeout=input_data.timeout,
            )
        except Exception as e:
            logger.error(f"[AI.LLM] 構建模型失敗: {e}")
            raise ValueError(f"構建模型失敗: {str(e)}")
        
        # 構建消息
        messages = []
        if input_data.system_prompt:
            messages.append(SystemMessage(content=input_data.system_prompt))
        messages.append(HumanMessage(content=input_data.user_prompt))
        
        # 重試循環
        last_error = None
        for attempt in range(input_data.max_retry + 1):  # +1 因爲第一次不算重試
            try:
                # 調用模型
                response = await model.ainvoke(messages)
                
                # 提取文本（兼容 content 爲 list/dict 的模型返回）
                payload = response.content if hasattr(response, 'content') else response
                response_text = _extract_text(payload)
                
                # 提取 usage 信息
                usage = {}
                if hasattr(response, 'usage_metadata'):
                    usage = response.usage_metadata
                elif hasattr(response, 'response_metadata'):
                    meta = response.response_metadata
                    if isinstance(meta, dict):
                        usage = meta.get('usage', {})
                
                logger.info(
                    f"[AI.LLM] LLM 調用成功 (嘗試 {attempt + 1}/{input_data.max_retry + 1}): "
                    f"llm_config_id={input_data.llm_config_id}, response_length={len(response_text)}"
                )
                
                yield LLMOutput(
                    response=response_text,
                    usage=usage
                )
                return
                
            except Exception as e:
                last_error = e
                if attempt < input_data.max_retry:
                    logger.warning(
                        f"[AI.LLM] LLM 調用失敗 (嘗試 {attempt + 1}/{input_data.max_retry + 1}), "
                        f"將重試: {str(e)}"
                    )
                else:
                    logger.error(
                        f"[AI.LLM] LLM 調用失敗,已達最大重試次數 ({input_data.max_retry + 1}): {str(e)}"
                    )
        
        # 所有重試都失敗
        raise RuntimeError(f"LLM 調用失敗 (重試{input_data.max_retry}次後): {str(last_error)}")

