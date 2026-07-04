"""Agent 構建器

提取 Agent 創建邏輯，供靈感助手和工作流節點複用。
"""

from typing import List, Optional
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from loguru import logger


def build_agent(
    model: BaseChatModel,
    tools: List[BaseTool],
    system_prompt: str,
    enable_summarization: bool = False,
    max_tokens_before_summary: int = 8192,
):
    """構建 LangChain Agent
    
    Args:
        model: LangChain ChatModel 實例
        tools: 工具列表
        system_prompt: 系統提示詞
        enable_summarization: 是否啓用上下文摘要
        max_tokens_before_summary: 摘要觸發的 token 閾值
        
    Returns:
        LangChain Agent 實例
    """
    middleware = []
    
    if enable_summarization:
        try:
            middleware.append(
                SummarizationMiddleware(
                    model=model,
                    max_tokens_before_summary=max_tokens_before_summary,
                )
            )
        except Exception as e:
            logger.warning(f"初始化 SummarizationMiddleware 失敗，將忽略上下文摘要: {e}")
    
    # 使用 LangChain 1.x 的 create_agent 創建帶工具的智能體
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
    )
    
    return agent
