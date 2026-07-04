"""工作流引擎類型定義

只包含新代碼式工作流系統使用的類型。
"""

from typing import Literal, Any, Callable, Dict
from dataclasses import dataclass, field
from datetime import datetime


# 節點狀態類型
NodeStatus = Literal["idle", "pending", "running", "success", "error", "skipped"]

# 運行狀態類型
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "paused", "timeout"]

# 錯誤處理策略
ErrorHandling = Literal["stop", "continue"]

# 日誌級別
LogLevel = Literal["debug", "info", "warn", "error"]


@dataclass
class NodeMetadata:
    """節點元數據"""
    type: str
    category: str
    label: str
    description: str
    documentation: str  # 完整的文檔（從 docstring 提取）
    input_schema: Dict[str, Any]  # 從 input_model 生成的 JSON Schema
    output_schema: Dict[str, Any]  # 從 output_model 生成的 JSON Schema
    executor: Callable  # 節點執行器類


@dataclass
class WorkflowSettings:
    """工作流執行設置"""
    max_execution_time: int | None = None  # 秒
    timeout: int = 300  # 節點默認超時時間（秒）
    error_handling: ErrorHandling = "stop"
    max_concurrency: int = 5  # 最大併發節點數
    log_level: LogLevel = "info"


@dataclass
class ExecutionContext:
    """節點執行上下文（簡化版，用於兼容舊節點）"""
    run_id: int
    node_id: str
    node_type: str
    config: dict[str, Any]
    inputs: dict[str, Any]
    variables: dict[str, Any]  # 全局變量
    node_outputs: dict[str, dict[str, Any]]  # 其他節點的輸出
    settings: WorkflowSettings
    session: Any  # SQLModel Session
    checkpoint: dict[str, Any] | None = None  # 檢查點數據（恢復時注入）
    """檢查點數據（恢復時由執行器注入）
    
    節點可以通過 self.context.checkpoint 訪問上次保存的檢查點數據。
    
    示例：
        checkpoint = getattr(self.context, 'checkpoint', None)
        if checkpoint:
            start_index = checkpoint.get('processed_count', 0)
        else:
            start_index = 0
    
    注意：
    - 只保存輕量級元數據（索引、計數器、ID等）
    - 不保存業務數據（卡片內容、處理結果等）
    - 大小限制：< 10KB
    """


@dataclass
class ExecutionEvent:
    """執行事件（用於 SSE 推送）"""
    type: str  # run.started | node.started | node.progress | node.completed | node.error | run.completed | run.paused | run.cancelled
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_sse(self) -> str:
        """轉換爲SSE格式"""
        import json
        return f"event: {self.type}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"

