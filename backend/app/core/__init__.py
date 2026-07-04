"""核心模塊

包含事件系統、啓動初始化、配置管理等核心功能。
"""

# 事件系統
from .events import Event, on_event, emit_event, get_event_handlers, discover_event_handlers

# 配置系統
from .config import settings

# 注意：startup 和 shutdown 不在此導出，避免循環導入
# 使用時請直接從 app.core.startup 導入

__all__ = [
    # 事件系統
    'Event',
    'on_event',
    'emit_event',
    'get_event_handlers',
    'discover_event_handlers',
    # 配置系統
    'settings',
]
