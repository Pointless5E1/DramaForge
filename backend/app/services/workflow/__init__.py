"""工作流服務模塊

新一代代碼式工作流系統，支持：
- 代碼式 DSL 編輯
- 異步併發執行
- 節點類型系統
- 實時狀態推送（SSE）
- Agent 編排

## 使用方式

### 定義節點
```python
from app.services.workflow import register_node
from app.services.workflow.nodes.base import BaseNode
from pydantic import BaseModel
from typing import AsyncIterator

class MyNodeInput(BaseModel):
    value: str

class MyNodeOutput(BaseModel):
    result: str

@register_node
class MyNode(BaseNode):
    node_type = "My.Node"
    category = "custom"
    label = "我的節點"
    description = "節點描述"
    input_model = MyNodeInput
    output_model = MyNodeOutput
    
    async def execute(self, input_data: MyNodeInput) -> AsyncIterator[MyNodeOutput]:
        # 節點處理邏輯
        yield MyNodeOutput(result=f"處理: {input_data.value}")
```

### 自動發現（在啓動時調用）
```python
from app.services.workflow import discover_workflow_nodes
discover_workflow_nodes()
```
"""

from .registry import (
    get_registered_nodes,
    get_node_types,
    get_node_metadata,
    get_all_node_metadata,
    get_nodes_by_category,
    discover_workflow_nodes,
    register_node
)

from .engine import (
    WorkflowScheduler,
    StateManager,
    RunManager,
    AsyncExecutor
)

# 導入所有工作流節點模塊以觸發裝飾器註冊
from . import nodes  # noqa: F401

# 導入觸發器模塊以觸發事件處理器註冊
from . import triggers  # noqa: F401

__all__ = [
    # 註冊相關
    'get_registered_nodes',
    'get_node_types',
    'get_node_metadata',
    'get_all_node_metadata',
    'get_nodes_by_category',
    'discover_workflow_nodes',
    'register_node',
    # 引擎相關
    'WorkflowScheduler',
    'StateManager',
    'RunManager',
    'AsyncExecutor',
]
