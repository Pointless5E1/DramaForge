"""AI服務模塊

統一的LLM調用、結構化生成、續寫和助手服務。
"""

from .core.chat_model_factory import build_chat_model
from .core.llm_service import (
    generate_structured,
    generate_continuation_streaming,
)
from .assistant.assistant_service import (
    generate_assistant_chat_streaming,
)

__all__ = [
    'build_chat_model',
    'generate_structured',
    'generate_continuation_streaming',
    'generate_assistant_chat_streaming',
]
