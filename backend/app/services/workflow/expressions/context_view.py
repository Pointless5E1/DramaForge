"""表達式上下文包裝器（簡化版）"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Dict


PRIMITIVE_TYPES = (
    str,
    int,
    float,
    bool,
    bytes,
    bytearray,
    complex,
    date,
    datetime,
    time,
)


class AttrDict(dict):
    """支持點號訪問的字典（缺失字段返回 None）"""

    def __getattr__(self, item: str) -> Any:
        if item.startswith("__"):
            raise AttributeError(item)
        return self.get(item, None)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, wrap_value(value))


def wrap_value(value: Any) -> Any:
    """遞歸包裝值，僅保留必要兼容能力（dict 點號訪問）"""
    if value is None:
        return None
    if isinstance(value, AttrDict):
        return value
    if isinstance(value, PRIMITIVE_TYPES):
        return value
    if isinstance(value, dict):
        wrapped = AttrDict()
        for key, item in value.items():
            wrapped[key] = item
        return wrapped
    if isinstance(value, list):
        return [wrap_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(wrap_value(item) for item in value)
    if isinstance(value, set):
        return {wrap_value(item) for item in value}
    return value


def unwrap_value(value: Any) -> Any:
    """遞歸反包裝值，輸出標準 Python 數據結構"""
    if isinstance(value, AttrDict):
        return {
            key: unwrap_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [unwrap_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(unwrap_value(item) for item in value)
    if isinstance(value, set):
        return {unwrap_value(item) for item in value}
    return value


def wrap_context(context: Dict[str, Any] | None) -> Dict[str, Any]:
    """包裝表達式上下文"""
    if not context:
        return {}
    return {
        key: wrap_value(value)
        for key, value in context.items()
    }

