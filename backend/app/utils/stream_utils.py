"""流式響應工具函數"""

import json
from typing import AsyncGenerator


async def wrap_sse_stream(generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    """將純文本流包裝爲 SSE (Server-Sent Events) 格式
    
    Args:
        generator: 異步文本生成器
        
    Yields:
        SSE 格式的數據流
    """
    async for item in generator:
        yield f"data: {json.dumps({'content': item}, ensure_ascii=False)}\n\n"
