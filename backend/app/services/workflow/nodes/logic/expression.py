"""表達式節點 - 數據轉換與提取"""

from __future__ import annotations

import inspect
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

from app.services.workflow.expressions import evaluate_expression
from app.services.workflow.expressions.builtins import get_safe_builtins
from app.services.workflow.expressions.functions import get_builtin_functions, get_helper_metadata
from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node


class ExpressionInput(BaseModel):
    """表達式節點輸入"""

    expression: str = Field(
        ...,
        description="Python 表達式（可以訪問所有已定義變量）",
        json_schema_extra={
            "x-component": "CodeEditor",
            "x-component-props": {
                "language": "python",
                "placeholder": "例如：card.content.field or []\n[item.name for item in items if item.name]"
            }
        },
    )


class ExpressionOutput(BaseModel):
    """表達式節點輸出"""

    result: Any = Field(..., description="表達式計算結果")


def _build_helper_docs() -> list[str]:
    helpers = get_builtin_functions()
    helper_meta = get_helper_metadata()
    if not helpers:
        return ["- （無業務 helper）"]

    ranked_names = sorted(
        helpers.keys(),
        key=lambda name: (helper_meta.get(name).priority if helper_meta.get(name) else 50, name),
        reverse=True,
    )

    lines: list[str] = ["### 推薦 helper（按優先級）"]
    for name in ranked_names[:3]:
        func = helpers[name]
        signature = str(inspect.signature(func))
        meta = helper_meta.get(name)
        summary = (meta.summary if meta else ((inspect.getdoc(func) or "").splitlines()[0] if inspect.getdoc(func) else "業務輔助函數")).strip()
        scenario = meta.scenario if meta else "通用"
        example = meta.example if meta else ""
        line = f"- `{name}{signature}`（場景：{scenario}，優先級：{meta.priority if meta else 50}）\n  - 說明：{summary}"
        if example:
            line += f"\n  - 示例：`{example}`"
        lines.append(line)

    lines.append("\n### 全量 helper 列表")
    for name in ranked_names:
        func = helpers[name]
        signature = str(inspect.signature(func))
        meta = helper_meta.get(name)
        summary = (meta.summary if meta else ((inspect.getdoc(func) or "").splitlines()[0] if inspect.getdoc(func) else "業務輔助函數")).strip()
        lines.append(f"- `{name}{signature}`：{summary}")
    return lines


def _build_builtin_docs() -> str:
    builtin_names = sorted(get_safe_builtins().keys())
    return ", ".join(f"`{name}`" for name in builtin_names)


def _build_expression_documentation() -> str:
    helper_lines = "\n".join(_build_helper_docs())
    builtin_line = _build_builtin_docs()

    return f"""
表達式節點用於執行**受控 Python 表達式**，適合做字段提取、列表轉換、條件拼裝。

## 核心規則（AI 必讀）
1. 節點輸出結構固定爲 `{{"result": <計算結果>}}`，後續節點必須通過 `.result` 訪問。
2. 可直接訪問工作流上下文變量（如 `project`、`cards`、`wait_xxx`）。
3. 推薦優先使用標準 Python 表達式語法（推導式、三元表達式、f-string）。
4. 字典支持點號訪問（如 `card.content.title`），缺失字段會按空值處理。

## 推薦寫法
```python
card.content.items or []
[item for item in items if item.status == "active"]
f"共處理 {{len(items)}} 項"
items if wait_ai.count > 0 else []
```

## 輸出訪問示例
```python
mapped = Logic.Expression(expression="{{item.id: item.name for item in cards}}")
Card.BatchUpsert(items=mapped.result)
```

## 可用 Python 內置函數
{builtin_line}

## 業務 helper（自動生成）
{helper_lines}
""".strip()


@register_node
class ExpressionNode(BaseNode):
    """表達式節點（受控 Python eval）"""

    node_type = "Logic.Expression"
    category = "logic"
    label = "表達式計算"
    description = "執行受控 Python 表達式，輸出 result"

    input_model = ExpressionInput
    output_model = ExpressionOutput

    @classmethod
    def get_metadata(cls):
        metadata = super().get_metadata()
        metadata.description = cls.description
        metadata.documentation = _build_expression_documentation()
        return metadata

    async def execute(self, input_data: ExpressionInput) -> AsyncIterator[ExpressionOutput]:
        """執行表達式"""
        expr_context = self.context.variables

        try:
            result = evaluate_expression(input_data.expression, expr_context)
            yield ExpressionOutput(result=result)
        except Exception as e:
            raise ValueError(
                f"表達式執行失敗: {str(e)}\n"
                f"表達式: {input_data.expression}\n"
                f"可用變量: {', '.join(expr_context.keys())}"
            )
