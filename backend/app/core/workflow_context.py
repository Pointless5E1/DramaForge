from contextvars import ContextVar
from typing import List

# 定義上下文變量，用於存儲當前請求觸發的工作流運行ID列表
_workflow_runs_ctx: ContextVar[List[int]] = ContextVar("workflow_runs_ctx", default=[])

def init_workflow_context():
    """初始化上下文（在每個請求開始時調用）"""
    _workflow_runs_ctx.set([])

def add_triggered_run_id(run_id: int):
    """添加觸發的運行ID"""
    current_list = _workflow_runs_ctx.get()
    # ContextVar 的 get 返回的是同一個列表對象的引用（因爲 default 只是初始值，set 之後是新的）
    # 但爲了安全起見，我們應該確保我們在修改當前的列表
    # 注意：如果從未調用過 set，get() 會返回 default 的那個空列表。
    # 爲了避免跨請求污染（雖然 default 是共享的），中間件必須顯式 set([])。
    # 這裏我們假設中間件已經初始化了新的空列表。
    current_list.append(run_id)

def get_triggered_run_ids() -> List[int]:
    """獲取所有觸發的運行ID"""
    return _workflow_runs_ctx.get()

def clear_workflow_context():
    """清理上下文"""
    _workflow_runs_ctx.set([])
