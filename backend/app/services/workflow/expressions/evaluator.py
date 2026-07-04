"""表達式求值器（單引擎受控 eval）"""

from __future__ import annotations

import ast
import keyword
from functools import lru_cache
from typing import Any, Dict, Optional, Set

from loguru import logger

from .builtins import get_safe_global_names, get_safe_globals
from .context_view import unwrap_value, wrap_context


FORBIDDEN_NODE_TYPES = (
    ast.Lambda,
    ast.NamedExpr,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
)

FORBIDDEN_FUNC_NAMES = {
    "__import__",
    "eval",
    "exec",
    "open",
    "compile",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "input",
    "help",
    "breakpoint",
}

RESERVED_NAMES = set(keyword.kwlist) | {"True", "False", "None"}


class ExpressionSecurityError(ValueError):
    """表達式安全檢查錯誤"""


class _ExpressionGuard(ast.NodeVisitor):
    """表達式 AST 守衛"""

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("__"):
            raise ExpressionSecurityError(f"禁止訪問雙下劃線屬性: {node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id.startswith("__"):
            raise ExpressionSecurityError(f"禁止使用雙下劃線名稱: {node.id}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_FUNC_NAMES:
            raise ExpressionSecurityError(f"禁止調用函數: {node.func.id}")
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST):
        if isinstance(node, FORBIDDEN_NODE_TYPES):
            raise ExpressionSecurityError(f"不支持的表達式語法: {type(node).__name__}")
        super().generic_visit(node)


class _DependencyCollector(ast.NodeVisitor):
    """表達式依賴變量收集器"""

    def __init__(self):
        self.loaded_names: Set[str] = set()
        self.bound_names: Set[str] = set()

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self.loaded_names.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.bound_names.add(node.id)
        self.generic_visit(node)


def _analyze_tree(tree: ast.Expression) -> Set[str]:
    collector = _DependencyCollector()
    collector.visit(tree)

    safe_globals = get_safe_global_names()
    dependencies = collector.loaded_names - collector.bound_names
    dependencies = {
        name for name in dependencies
        if name not in safe_globals and name not in RESERVED_NAMES
    }
    return dependencies


def _parse_and_guard(expression: str) -> ast.Expression:
    tree = ast.parse(expression, mode="eval")
    _ExpressionGuard().visit(tree)
    return tree


@lru_cache(maxsize=1024)
def _compile_expression(expression: str) -> tuple[Any, tuple[str, ...]]:
    """編譯表達式並緩存"""
    tree = _parse_and_guard(expression)
    code = compile(tree, "<workflow-expression>", "eval")
    dependencies = tuple(sorted(_analyze_tree(tree)))
    return code, dependencies


def validate_expression_syntax(expression: str) -> list[str]:
    """校驗表達式語法與安全規則"""
    if not expression or not isinstance(expression, str):
        return ["表達式不能爲空"]

    try:
        _parse_and_guard(expression)
        return []
    except (SyntaxError, ExpressionSecurityError) as e:
        return [str(e)]
    except Exception as e:
        return [f"表達式校驗失敗: {e}"]


def get_expression_dependencies(expression: str) -> Set[str]:
    """提取表達式依賴變量名"""
    if not expression or not isinstance(expression, str):
        return set()
    try:
        _, dependencies = _compile_expression(expression)
        return set(dependencies)
    except Exception:
        return set()


class ExpressionEvaluator:
    """表達式求值器"""

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}

    def evaluate(self, expression: str) -> Any:
        if not expression or not isinstance(expression, str):
            return expression

        try:
            code, _ = _compile_expression(expression)
            runtime_env = get_safe_globals().copy()
            runtime_env.update(wrap_context(self.context))
            result = eval(code, runtime_env, runtime_env)
            return unwrap_value(result)
        except Exception as e:
            logger.error(f"表達式求值失敗: {expression}, 錯誤: {e}")
            raise ValueError(f"表達式求值失敗: {str(e)}")


def evaluate_expression(
    expression: str,
    context: Optional[Dict[str, Any]] = None
) -> Any:
    """便捷函數：求值表達式"""
    evaluator = ExpressionEvaluator(context)
    return evaluator.evaluate(expression)
