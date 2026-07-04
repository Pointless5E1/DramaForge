"""初始化器註冊機制

提供裝飾器和自動發現功能，實現插件化的初始化系統。

使用方式：
    @initializer(name="prompts", order=10)
    def init_prompts(session: Session):
        ...
        
    # 自動發現並執行所有初始化器
    discover_and_run_initializers(session)
"""

from typing import Callable, List, Tuple
from sqlmodel import Session
from loguru import logger


# 全局註冊表：存儲所有初始化器
_INITIALIZERS: List[Tuple[int, str, Callable]] = []


def initializer(name: str, order: int = 100):
    """初始化器裝飾器
    
    將函數註冊爲初始化器，支持自動發現和按順序執行。
    
    Args:
        name: 初始化器名稱，用於日誌輸出
        order: 執行順序，數字越小越先執行（默認100）
        
    Example:
        @initializer(name="prompts", order=10)
        def init_prompts(session: Session):
            logger.info("初始化提示詞...")
    """
    def decorator(func: Callable):
        # 註冊到全局列表
        _INITIALIZERS.append((order, name, func))
        logger.debug(f"[初始化器註冊] {name} (order={order}) -> {func.__name__}")
        return func
    return decorator


def get_registered_initializers() -> List[Tuple[int, str, Callable]]:
    """獲取所有已註冊的初始化器
    
    Returns:
        按order排序的初始化器列表 [(order, name, func), ...]
    """
    return sorted(_INITIALIZERS, key=lambda x: x[0])


def discover_initializers():
    """記錄已註冊的初始化器數量
    
    所有初始化器模塊已在 app.bootstrap.__init__.py 中導入，
    裝飾器在包導入時自動執行註冊。
    """
    logger.debug(f"[初始化器發現] 已加載 {len(_INITIALIZERS)} 個初始化器")


def run_initializers(session: Session):
    """執行所有已註冊的初始化器
    
    按 order 順序依次執行初始化器。
    
    Args:
        session: 數據庫會話
    """
    initializers = get_registered_initializers()
    
    if not initializers:
        logger.warning("[初始化器] 未發現任何已註冊的初始化器")
        return
    
    logger.info(f"[初始化器] 發現 {len(initializers)} 個初始化器，開始執行...")
    
    for order, name, func in initializers:
        try:
            logger.info(f"[初始化器] 執行: {name} (order={order})")
            func(session)
        except Exception as e:
            logger.error(f"[初始化器] 執行失敗 {name}: {e}")
            raise


def discover_and_run_initializers(session: Session):
    """自動發現並執行所有初始化器
    
    這是主入口函數，完成：
    1. 自動發現所有初始化器模塊
    2. 按順序執行所有初始化器
    
    Args:
        session: 數據庫會話
    """
    discover_initializers()
    run_initializers(session)
