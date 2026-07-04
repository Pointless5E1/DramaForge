"""事件總線系統

統一的事件發佈-訂閱機制，支持裝飾器註冊和自動發現。
"""

from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class Event:
    """事件基類
    
    Attributes:
        name: 事件名稱
        data: 事件數據
        source: 事件源
    """
    name: str
    data: Dict[str, Any]
    source: Optional[str] = None


# 事件處理器註冊表
_EVENT_HANDLERS: Dict[str, List[Callable]] = {}


def on_event(event_name: str):
    """裝飾器：註冊事件處理器
    
    用法:
        @on_event("card.saved")
        def handle_card_saved(event: Event):
            ...
    
    Args:
        event_name: 事件名稱
        
    Returns:
        裝飾器函數
    """
    def decorator(func: Callable):
        if event_name not in _EVENT_HANDLERS:
            _EVENT_HANDLERS[event_name] = []
        _EVENT_HANDLERS[event_name].append(func)
        logger.debug(f"[事件註冊] {event_name} -> {func.__name__}")
        return func
    return decorator


def emit_event(event_name: str, data: Dict[str, Any], source: Optional[str] = None) -> None:
    """發佈事件
    
    Args:
        event_name: 事件名稱
        data: 事件數據
        source: 事件源
    """
    event = Event(name=event_name, data=data, source=source)
    handlers = _EVENT_HANDLERS.get(event_name, [])
    
    if not handlers:
        logger.debug(f"[事件發佈] {event_name} - 無處理器")
        return
    
    logger.info(f"[事件發佈] {event_name} - {len(handlers)}個處理器")
    
    for handler in handlers:
        try:
            handler(event)
        except Exception as e:
            logger.error(f"[事件處理失敗] {event_name} - {handler.__name__}: {e}")


def get_event_handlers(event_name: str) -> List[Callable]:
    """獲取指定事件的所有處理器
    
    Args:
        event_name: 事件名稱
        
    Returns:
        處理器列表
    """
    return _EVENT_HANDLERS.get(event_name, []).copy()


def get_all_events() -> List[str]:
    """獲取所有已註冊的事件名稱
    
    Returns:
        事件名稱列表
    """
    return list(_EVENT_HANDLERS.keys())


def discover_event_handlers():
    """記錄已註冊的事件處理器數量
    
    所有事件處理器模塊已在 app.services.__init__.py 中導入，
    裝飾器在包導入時自動執行註冊。
    """
    total_handlers = sum(len(handlers) for handlers in _EVENT_HANDLERS.values())
    logger.debug(f"[事件發現] 已加載 {len(_EVENT_HANDLERS)} 個事件，共 {total_handlers} 個處理器")


def clear_handlers(event_name: Optional[str] = None) -> None:
    """清除事件處理器（主要用於測試）
    
    Args:
        event_name: 事件名稱，如果爲None則清除所有
    """
    if event_name is None:
        _EVENT_HANDLERS.clear()
        logger.debug("[事件系統] 清除所有處理器")
    else:
        _EVENT_HANDLERS.pop(event_name, None)
        logger.debug(f"[事件系統] 清除 {event_name} 的處理器")
