"""示例節點 - 展示新的 BaseNode 接口使用

包含進度推送和流式執行的示例。
"""

from typing import List, Dict, Any, AsyncIterator, Union, TYPE_CHECKING
from pydantic import BaseModel, Field
from loguru import logger
import asyncio

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from ..base import BaseNode
from ...registry import register_node


# ============= Example.Process 節點 =============

class ExampleProcessInput(BaseModel):
    """示例處理節點輸入"""
    items: List[str] = Field(..., description="要處理的項目列表")
    delay: float = Field(0.5, description="每項處理延遲(秒)", ge=0.0, le=10.0)
    enable_progress: bool = Field(True, description="是否啓用進度推送")


class ExampleProcessOutput(BaseModel):
    """示例處理節點輸出"""
    results: List[Dict[str, Any]] = Field(..., description="處理結果列表")
    summary: Dict[str, Any] = Field(..., description="處理摘要")


@register_node
class ExampleProcessNode(BaseNode[ExampleProcessInput, ExampleProcessOutput]):
    """示例處理節點

    展示如何使用新的 BaseNode 接口：
    1. 使用 Pydantic 輸入輸出模型
    2. 實現流式執行和進度推送
    3. 類型安全的輸入輸出
    """

    node_type = "Example.Process"
    category = "example"
    label = "示例處理"
    description = "處理項目列表並推送進度（用於測試和演示）"

    input_model = ExampleProcessInput
    output_model = ExampleProcessOutput

    async def execute(self, inputs: ExampleProcessInput) -> AsyncIterator[Union['ProgressEvent', ExampleProcessOutput]]:
        """流式執行方法（支持進度推送和斷點續傳）
        
        斷點續傳機制：
        1. 從 self.context.checkpoint 讀取上次的進度
        2. 從中斷位置繼續處理
        3. 每次進度更新時保存檢查點數據
        """
        from ...engine.async_executor import ProgressEvent
        
        logger.info(f"[Example.Process] 開始處理 {len(inputs.items)} 個項目")

        # === 1. 讀取檢查點（自動注入）===
        checkpoint = getattr(self.context, 'checkpoint', None)
        start_index = checkpoint.get('processed_count', 0) if checkpoint else 0
        
        if start_index > 0:
            logger.info(f"[Example.Process] 從檢查點恢復: 已處理 {start_index}/{len(inputs.items)}")

        results = []
        total = len(inputs.items)
        
        # === 2. 從檢查點繼續處理 ===
        for i in range(start_index, total):
            item = inputs.items[i]
            
            # 模擬處理
            await asyncio.sleep(inputs.delay)
            result = {"item": item, "processed": True, "index": i}
            results.append(result)
            
            # === 3. 報告進度（自動保存檢查點）===
            if inputs.enable_progress:
                percent = ((i + 1) / total) * 100
                yield ProgressEvent(
                    percent=percent,
                    message=f"正在處理: {item} ({i+1}/{total})",
                    data={
                        'processed_count': i + 1,  # ✅ 輕量級：計數器
                        'last_item': item          # ✅ 輕量級：標識符
                    }
                )

        summary = {
            "total": len(inputs.items),
            "processed": len(results),
            "success_rate": 1.0
        }

        logger.info(f"[Example.Process] 處理完成: {summary}")

        # === 4. 返回最終結果 ===
        yield ExampleProcessOutput(
            results=results,
            summary=summary
        )

class BatchProcessInput(BaseModel):
    """批量處理節點輸入"""
    data: List[Any] = Field(..., description="要處理的數據列表")
    batch_size: int = Field(10, description="批次大小", ge=1, le=100)
    parallel: bool = Field(False, description="是否並行處理批次")


class BatchProcessOutput(BaseModel):
    """批量處理節點輸出"""
    results: List[Dict[str, Any]] = Field(..., description="處理結果列表")
    total_processed: int = Field(..., description="處理的總數")


@register_node
class BatchProcessNode(BaseNode[BatchProcessInput, BatchProcessOutput]):
    """批量處理節點

    展示批量處理和並行執行。
    """

    node_type = "Example.BatchProcess"
    category = "example"
    label = "批量處理"
    description = "批量處理數據，支持並行（用於測試和演示）"

    input_model = BatchProcessInput
    output_model = BatchProcessOutput

    async def execute(self, inputs: BatchProcessInput) -> AsyncIterator[BatchProcessOutput]:
        """批量處理執行"""
        logger.info(f"[Example.BatchProcess] 處理 {len(inputs.data)} 條數據，批次大小: {inputs.batch_size}")

        results = []

        # 分批處理
        for i in range(0, len(inputs.data), inputs.batch_size):
            batch = inputs.data[i:i + inputs.batch_size]

            if inputs.parallel:
                # 並行處理批次
                tasks = [self._process_item(item) for item in batch]
                batch_results = await asyncio.gather(*tasks)
            else:
                # 串行處理批次
                batch_results = []
                for item in batch:
                    result = await self._process_item(item)
                    batch_results.append(result)

            results.extend(batch_results)

        logger.info(f"[Example.BatchProcess] 處理完成: {len(results)} 條結果")

        yield BatchProcessOutput(
            results=results,
            total_processed=len(results)
        )

    async def _process_item(self, item: Any) -> Dict[str, Any]:
        """處理單個項目"""
        await asyncio.sleep(0.1)  # 模擬處理
        return {"item": item, "processed": True}
