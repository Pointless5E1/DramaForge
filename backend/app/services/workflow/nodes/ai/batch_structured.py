import asyncio
import os
from typing import Any, Dict, List, Optional, AsyncIterator, Union, TYPE_CHECKING
from loguru import logger
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.core.llm_service import generate_structured
from ...registry import register_node
from ..base import BaseNode
from app.db.models import CardType
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from sqlmodel import select


class BatchStructuredInput(BaseModel):
    """批量結構化生成輸入"""
    items: List[Any] = Field(..., description="數據列表 (包含元數據)")
    llm_config_id: int = Field(..., description="LLM 配置 ID", json_schema_extra={"x-component": "LLMSelect"})
    prompt_template: str = Field(..., description="提示詞模板，支持 {{content}} 和 {{item.field}}", json_schema_extra={"x-component": "Textarea"})
    response_model_id: str = Field(..., description="響應模型", json_schema_extra={"x-component": "ResponseModelSelect"})
    concurrency: int = Field(30, description="最大併發數", ge=1)
    max_retries: int = Field(3, description="最大重試次數")
    temperature: float = Field(0.7, description="溫度參數")
    max_tokens: Optional[int] = Field(None, description="最大 token 數")
    timeout: Optional[float] = Field(150, description="超時時間(秒)")
    fail_soft: bool = Field(False, description="單項失敗時是否降級返回部分結果")
    use_instruction_flow: bool = Field(
        False,
        description="是否使用指令流模式（複雜結構推薦開啓，簡單結構可關閉以使用原生結構化）",
    )
    cache_key: Optional[str] = Field(None, description="緩存Key (用於斷點續傳)，若爲空則使用 item.path 或 index")


class BatchStructuredOutput(BaseModel):
    """批量結構化生成輸出"""
    results: List[Dict[str, Any]] = Field(..., description="提取結果列表")
    errors: List[Dict[str, Any]] = Field(..., description="錯誤項列表")


@register_node
class BatchStructuredNode(BaseNode[BatchStructuredInput, BatchStructuredOutput]):
    node_type = "AI.BatchStructured"
    category = "ai"
    label = "批量結構化生成"
    description = "批量調用 LLM 進行結構化提取，支持併發和斷點續傳"
    
    input_model = BatchStructuredInput
    output_model = BatchStructuredOutput

    async def execute(self, inputs: BatchStructuredInput) -> AsyncIterator[Union['ProgressEvent', BatchStructuredOutput]]:
        """批量結構化生成（支持併發和斷點續傳）"""
        from ...engine.async_executor import ProgressEvent
        
        items = inputs.items
        if not isinstance(items, list):
            raise ValueError("輸入 items 必須是列表")

        if not items:
            yield BatchStructuredOutput(results=[], errors=[])
            return

        prompt_template = inputs.prompt_template
        if not prompt_template:
            raise ValueError("提示詞模板爲空")

        # === 1. 恢復檢查點 ===
        checkpoint = getattr(self.context, 'checkpoint', None)
        processed_indices = set(checkpoint.get('processed_indices', [])) if checkpoint else set()
        saved_results = checkpoint.get('partial_results', []) if checkpoint else []
        
        if processed_indices:
            logger.info(
                f"[BatchStructured] 從檢查點恢復: "
                f"已處理 {len(processed_indices)}/{len(items)}"
            )

        # 初始化結果列表
        results = [None] * len(items)
        errors = []
        total = len(items)
        
        # 恢復已保存的結果
        for saved_result in saved_results:
            if isinstance(saved_result, dict) and 'meta' in saved_result:
                for i, item in enumerate(items):
                    if item == saved_result['meta']:
                        results[i] = saved_result
                        break
        
        # 待處理的索引
        pending_indices = [i for i in range(len(items)) if i not in processed_indices]
        
        if not pending_indices:
            logger.info(f"[BatchStructured] 所有任務已完成")
            yield BatchStructuredOutput(
                results=[r for r in results if r is not None],
                errors=errors
            )
            return
        
        logger.info(
            f"[BatchStructured] 待處理 {len(pending_indices)} 個項目 "
            f"(已完成 {len(processed_indices)} 個, 併發限制: {inputs.concurrency})"
        )

        schema = self._get_schema(self.context.session, inputs)
        if not schema:
            raise ValueError(f"無法加載模型 Schema: {inputs.response_model_id}")
        dynamic_output = build_model_from_json_schema(
            f"BatchStructured_{inputs.response_model_id}",
            schema,
        )
        
        # === 2. 進度隊列 ===
        progress_queue = asyncio.Queue()
        
        # === 3. 單項處理函數 ===
        async def process_item(index):
            """處理單個項目"""
            item = items[index]
            
            try:
                # 準備內容
                content = ""
                path = item.get("path")
                
                if path and os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except Exception as e:
                        logger.error(f"讀取文件失敗: {path}, {e}")
                        content = f"[讀取失敗: {e}]"
                
                if not content and "content" in item:
                    content = item["content"]

                # 渲染 Prompt
                current_prompt = prompt_template.replace("{{content}}", str(content))
                for k, v in item.items():
                    if k != "content":
                        current_prompt = current_prompt.replace(f"{{{{item.{k}}}}}", str(v))
                
                # LLM 調用
                logger.info(f"[BatchStructured] Item {index}: 開始 LLM 調用")

                generated = await generate_structured(
                    session=self.context.session,
                    llm_config_id=inputs.llm_config_id,
                    user_prompt=current_prompt,
                    output_type=dynamic_output,
                    system_prompt=None,
                    deps="",
                    temperature=inputs.temperature,
                    max_tokens=inputs.max_tokens,
                    timeout=inputs.timeout or 150,
                    max_retries=inputs.max_retries,
                    use_instruction_flow=inputs.use_instruction_flow,
                    track_stats=True,
                    return_logs=True,
                )
                
                logger.info(f"[BatchStructured] Item {index}: ✅ LLM 調用完成")
                
                # 保存結果
                results[index] = {
                    "ai_result": generated["result"].model_dump(mode="json"),
                    "logs": generated["logs"],
                    "meta": item
                }
                
            except asyncio.CancelledError:
                logger.warning(f"[BatchStructured] Item {index}: 任務被取消")
                raise
            except Exception as e:
                logger.error(f"[BatchStructured] Item {index} 處理失敗: {e}")
                errors.append({"index": index, "item": item, "error": str(e)})
                results[index] = {"error": str(e), "meta": item}
            
            finally:
                # 通知進度
                processed_indices.add(index)
                await progress_queue.put(index)
        
        # === 4. 批量處理函數（單個任務）===
        async def process_all_batches():
            """分批處理所有待處理項目"""
            batch_size = inputs.concurrency
            
            for batch_start in range(0, len(pending_indices), batch_size):
                batch_indices = pending_indices[batch_start:batch_start + batch_size]
                
                logger.info(
                    f"[BatchStructured] 處理批次 {batch_start//batch_size + 1}: "
                    f"索引 {batch_indices}"
                )
                
                # 併發處理當前批次
                await asyncio.gather(
                    *[process_item(i) for i in batch_indices],
                    return_exceptions=True
                )
                
                logger.info(
                    f"[BatchStructured] 批次 {batch_start//batch_size + 1} 完成"
                )
        
        # === 5. 啓動處理並監聽進度 ===
        main_task = asyncio.create_task(process_all_batches())
        self.register_task(main_task)  # 只需註冊一個任務
        
        # 實時報告進度
        while not main_task.done():
            try:
                await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                
                # 報告進度
                percent = (len(processed_indices) / total) * 100
                current_results = [r for r in results if r is not None]
                
                yield ProgressEvent(
                    percent=percent,
                    message=f"已處理 {len(processed_indices)}/{total} 個項目",
                    data={
                        'processed_indices': list(processed_indices),
                        'partial_results': current_results
                    }
                )
            except asyncio.TimeoutError:
                continue
        
        # 等待主任務完成
        await main_task
        
        logger.info(
            f"[BatchStructured] 批量處理完成: "
            f"{len([r for r in results if r is not None])} 個成功, {len(errors)} 個失敗"
        )
        
        # === 6. 返回最終結果 ===
        yield BatchStructuredOutput(
            results=[r for r in results if r is not None],
            errors=errors
        )

    def _get_schema(self, session, inputs: BatchStructuredInput) -> Optional[Dict[str, Any]]:
        """根據配置獲取 JSON Schema
        """
        
        stmt = select(CardType).where(CardType.name == inputs.response_model_id)
        ct = session.exec(stmt).first()
        if ct and ct.json_schema:
            return ct.json_schema

        builtin_model = RESPONSE_MODEL_MAP.get(inputs.response_model_id)
        if builtin_model is not None:
            return builtin_model.model_json_schema(ref_template="#/$defs/{model}")
                
        return None
