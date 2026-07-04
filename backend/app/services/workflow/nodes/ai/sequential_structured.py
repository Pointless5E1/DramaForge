
import copy
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING, Union

from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from app.db.models import CardType
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.core.llm_service import generate_structured
from ...expressions.evaluator import evaluate_expression
from ...registry import register_node
from ..base import BaseNode


class SequentialStructuredInput(BaseModel):
    """順序結構化生成輸入"""

    items: List[Any] = Field(..., description="數據列表（按順序處理）")
    llm_config_id: int = Field(..., description="LLM 配置 ID", json_schema_extra={"x-component": "LLMSelect"})
    prompt_template: str = Field(
        ...,
        description="提示詞模板，支持 {{content}} / {{item.xxx}} / {{carry.xxx}}",
        json_schema_extra={"x-component": "Textarea"},
    )
    response_model_id: str = Field(..., description="響應模型", json_schema_extra={"x-component": "ResponseModelSelect"})
    temperature: Optional[float] = Field(
        None,
        description="採樣溫度（可選，默認使用模型配置）",
        ge=0.0,
        le=2.0,
    )
    max_tokens: Optional[int] = Field(
        None,
        description="最大輸出 token（可選，默認使用模型配置）",
        ge=1,
    )
    timeout: Optional[float] = Field(
        None,
        description="單次調用超時秒數（可選，默認使用模型配置）",
        gt=0,
    )
    max_retries: int = Field(3, description="最大重試次數", ge=1)
    use_instruction_flow: bool = Field(
        False,
        description="是否使用指令流模式（複雜結構推薦開啓，簡單結構可關閉以使用原生結構化）",
    )
    overlap_size: int = Field(0, description="重疊窗口大小（可選，默認0）", ge=0)
    initial_carry: Optional[Dict[str, Any]] = Field(None, description="初始承接狀態")
    carry_extract_expr: Optional[str] = Field(
        None,
        description="從當前輪結果提取下一輪 carry 的表達式（可選）",
        json_schema_extra={"x-component": "Textarea"},
    )
    fail_soft: bool = Field(False, description="單項失敗時是否降級並繼續")


class SequentialStructuredOutput(BaseModel):
    """順序結構化生成輸出"""

    results: List[Dict[str, Any]] = Field(..., description="每輪結果（ai_result/meta/carry_in/carry_out）")
    final_carry: Dict[str, Any] = Field(..., description="最終 carry 狀態")
    errors: List[Dict[str, Any]] = Field(..., description="錯誤列表")


@register_node
class SequentialStructuredNode(BaseNode[SequentialStructuredInput, SequentialStructuredOutput]):
    """
    按順序執行結構化生成並承接 carry 的 AI 節點。
    用法要點：
    - `items` 按順序逐項處理，天然支持跨項上下文承接。
    - `prompt_template` 支持 `{{content}}`、`{{item.xxx}}`、`{{carry.xxx}}`、`{{overlap_size}}` 佔位。
    - 通過 `carry_extract_expr` 從本輪 `ai_result` 提取下一輪 carry（必須返回 dict 或 None）。
    - 可選透傳 `temperature/max_tokens/timeout`，細調結構化生成質量與穩定性。
    - 運行中會持續產出 `ProgressEvent`，並把 `partial_results/carry_state` 寫入 checkpoint，支持斷點恢復。
    """

    node_type = "AI.SequentialStructured"
    category = "ai"
    label = "順序結構化生成"
    description = "順序調用結構化生成，支持跨輪 carry 承接與斷點恢復"

    input_model = SequentialStructuredInput
    output_model = SequentialStructuredOutput

    async def execute(
        self,
        inputs: SequentialStructuredInput,
    ) -> AsyncIterator[Union["ProgressEvent", SequentialStructuredOutput]]:
        from ...engine.async_executor import ProgressEvent

        items = inputs.items
        if not isinstance(items, list):
            raise ValueError("輸入 items 必須是列表")

        if not inputs.prompt_template:
            raise ValueError("提示詞模板爲空")

        if not items:
            yield SequentialStructuredOutput(
                results=[],
                final_carry=copy.deepcopy(inputs.initial_carry or {}),
                errors=[],
            )
            return

        total = len(items)
        schema = self._get_schema(self.context.session, inputs)
        if not schema:
            raise ValueError(f"無法加載模型 Schema: {inputs.response_model_id}")
        dynamic_output = build_model_from_json_schema(
            f"SequentialStructured_{inputs.response_model_id}",
            schema,
        )

        checkpoint = getattr(self.context, "checkpoint", None) or {}
        results = self._normalize_result_list(checkpoint.get("partial_results", []))
        errors = self._normalize_result_list(checkpoint.get("errors", []))
        processed_indices = self._normalize_index_set(checkpoint.get("processed_indices", []), total)

        carry_state = checkpoint.get("carry_state")
        if not isinstance(carry_state, dict):
            carry_state = copy.deepcopy(inputs.initial_carry or {})

        current_index = checkpoint.get("current_index")
        if not isinstance(current_index, int):
            current_index = len(results)

        current_index = max(current_index, len(results), len(processed_indices))
        current_index = min(current_index, total)

        if current_index > 0:
            logger.info(
                f"[SequentialStructured] 從檢查點恢復: 已處理 {current_index}/{total}, "
                f"errors={len(errors)}"
            )

        if current_index >= total:
            yield SequentialStructuredOutput(
                results=results,
                final_carry=carry_state,
                errors=errors,
            )
            return

        for index in range(current_index, total):
            item = items[index]
            carry_in = copy.deepcopy(carry_state)

            try:
                rendered_prompt = self._render_prompt(
                    template=inputs.prompt_template,
                    item=item,
                    carry=carry_in,
                    overlap_size=inputs.overlap_size,
                )

                logger.info(f"[SequentialStructured] Item {index}: 開始 LLM 調用")
                generated = await generate_structured(
                    session=self.context.session,
                    llm_config_id=inputs.llm_config_id,
                    user_prompt=rendered_prompt,
                    output_type=dynamic_output,
                    system_prompt=None,
                    deps="",
                    temperature=inputs.temperature or 0.7,
                    max_tokens=inputs.max_tokens,
                    timeout=inputs.timeout or 150,
                    max_retries=inputs.max_retries,
                    use_instruction_flow=inputs.use_instruction_flow,
                    track_stats=True,
                    return_logs=True,
                )
                ai_result = generated["result"].model_dump(mode="json")
                logger.info(f"[SequentialStructured] Item {index}: ✅ LLM 調用完成")

                carry_out = self._extract_carry(
                    expr=inputs.carry_extract_expr,
                    ai_result=ai_result,
                    item=item,
                    carry=carry_in,
                    index=index,
                    results=results,
                    errors=errors,
                )

                result_item = {
                    "index": index,
                    "ai_result": ai_result,
                    "logs": generated["logs"],
                    "meta": item,
                    "carry_in": carry_in,
                    "carry_out": carry_out,
                }
                results.append(result_item)
                carry_state = carry_out
                processed_indices.add(index)

            except Exception as e:
                logger.error(f"[SequentialStructured] Item {index} 處理失敗: {e}")
                error_item = {"index": index, "item": item, "error": str(e)}
                errors.append(error_item)

                if not inputs.fail_soft:
                    raise

                results.append(
                    {
                        "index": index,
                        "error": str(e),
                        "meta": item,
                        "carry_in": carry_in,
                        "carry_out": carry_state,
                    }
                )
                processed_indices.add(index)

            percent = ((index + 1) / total) * 100
            yield ProgressEvent(
                percent=percent,
                message=f"已處理 {index + 1}/{total} 個項目",
                data={
                    "current_index": index + 1,
                    "processed_indices": sorted(processed_indices),
                    "carry_state": carry_state,
                    "partial_results": results,
                    "errors": errors,
                },
            )

        yield SequentialStructuredOutput(
            results=results,
            final_carry=carry_state,
            errors=errors,
        )

    def _render_prompt(
        self,
        template: str,
        item: Any,
        carry: Dict[str, Any],
        overlap_size: int,
    ) -> str:
        content = self._extract_content(item)
        rendered = template.replace("{{content}}", str(content))
        rendered = rendered.replace("{{item}}", self._to_text(item))
        rendered = rendered.replace("{{carry}}", self._to_text(carry))
        rendered = rendered.replace("{{overlap_size}}", str(overlap_size))

        rendered = self._render_prefix_fields(rendered, "item", item)
        rendered = self._render_prefix_fields(rendered, "carry", carry)
        return rendered

    def _render_prefix_fields(self, text: str, prefix: str, value: Any, path: Optional[List[str]] = None) -> str:
        current_path = path or []
        placeholder = "{{" + ".".join([prefix, *current_path]) + "}}"

        if current_path:
            text = text.replace(placeholder, self._to_text(value))

        if isinstance(value, dict):
            for key, child in value.items():
                text = self._render_prefix_fields(text, prefix, child, [*current_path, str(key)])

        return text

    def _extract_content(self, item: Any) -> str:
        if not isinstance(item, dict):
            return str(item)

        content = ""
        path = item.get("path")

        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    content = file.read()
            except Exception as e:
                logger.error(f"[SequentialStructured] 讀取文件失敗: {path}, {e}")
                content = f"[讀取失敗: {e}]"

        if not content and "content" in item:
            content = self._to_text(item.get("content"))

        return content

    def _extract_carry(
        self,
        expr: Optional[str],
        ai_result: Any,
        item: Any,
        carry: Dict[str, Any],
        index: int,
        results: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not expr:
            return copy.deepcopy(carry)

        next_carry = evaluate_expression(
            expr,
            {
                "ai_result": ai_result,
                "item": item,
                "carry": carry,
                "index": index,
                "results": results,
                "errors": errors,
            },
        )

        if next_carry is None:
            return {}

        if not isinstance(next_carry, dict):
            raise ValueError("carry_extract_expr 必須返回 dict 或 None")

        return next_carry

    def _normalize_result_list(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _normalize_index_set(self, value: Any, total: int) -> set[int]:
        if not isinstance(value, list):
            return set()

        normalized: set[int] = set()
        for item in value:
            try:
                index = int(item)
            except Exception:
                continue

            if 0 <= index < total:
                normalized.add(index)

        return normalized

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)

        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    def _get_schema(self, session, inputs: SequentialStructuredInput) -> Optional[Dict[str, Any]]:
        """根據配置獲取 JSON Schema"""

        stmt = select(CardType).where(CardType.name == inputs.response_model_id)
        ct = session.exec(stmt).first()
        if ct and ct.json_schema:
            return ct.json_schema

        builtin_model = RESPONSE_MODEL_MAP.get(inputs.response_model_id)
        if builtin_model is not None:
            return builtin_model.model_json_schema(ref_template="#/$defs/{model}")

        return None
