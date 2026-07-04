"""表達式執行環境（受控 builtins + helper）"""

from __future__ import annotations

import builtins as py_builtins
from functools import lru_cache
from typing import Any, Callable, Dict

from .functions import get_builtin_functions


ALLOWED_BUILTIN_NAMES = (
    "len",
    "sum",
    "min",
    "max",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "range",
    "enumerate",
    "zip",
    "any",
    "all",
    "abs",
    "round",
    "sorted",
)


@lru_cache(maxsize=1)
def get_safe_builtins() -> Dict[str, Any]:
    """獲取安全內置函數白名單"""
    return {
        name: getattr(py_builtins, name)
        for name in ALLOWED_BUILTIN_NAMES
        if hasattr(py_builtins, name)
    }


@lru_cache(maxsize=1)
def get_safe_helpers() -> Dict[str, Callable]:
    """獲取表達式 helper（兼容歷史函數庫）"""
    return get_builtin_functions()


@lru_cache(maxsize=1)
def get_safe_globals() -> Dict[str, Any]:
    """構造 eval 全局變量"""
    safe_builtins = get_safe_builtins()
    safe_helpers = get_safe_helpers()
    globals_dict: Dict[str, Any] = {
        "__builtins__": safe_builtins
    }

    # helper 與 builtins 同名時，以 builtins 爲準
    for name, func in safe_helpers.items():
        if name not in safe_builtins:
            globals_dict[name] = func

    return globals_dict


@lru_cache(maxsize=1)
def get_safe_global_names() -> set[str]:
    """獲取全局可見名字（用於依賴提取過濾）"""
    names = set(get_safe_builtins().keys())
    names.update(get_safe_helpers().keys())
    return names

