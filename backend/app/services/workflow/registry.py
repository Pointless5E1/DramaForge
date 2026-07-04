"""工作流節點註冊機制

使用裝飾器自動註冊工作流節點，支持 Pydantic 模型和元數據。
"""

from typing import Dict, Callable, List, Optional
from loguru import logger
import inspect

from .types import NodeMetadata


# 節點註冊表
_NODE_REGISTRY: Dict[str, NodeMetadata] = {}


def register_node(cls):
    """類裝飾器：註冊類式工作流節點
    
    直接調用節點類的 get_metadata() 方法獲取 NodeMetadata 對象。
    """
    if not inspect.isclass(cls):
        raise TypeError("@register_node must be used on a class")

    # 檢查必需的屬性
    node_type = getattr(cls, "node_type", None)
    if not node_type:
        raise ValueError(f"Node class {cls.__name__} must define 'node_type'")

    # 直接調用節點的 get_metadata() 方法，返回 NodeMetadata 對象
    metadata = cls.get_metadata()
    
    _NODE_REGISTRY[node_type] = metadata
    logger.debug(f"[節點註冊] {node_type} ({metadata.category}) -> {cls.__name__}")
    return cls


def get_registered_nodes() -> Dict[str, Callable]:
    """獲取所有已註冊的節點執行器
    
    Returns:
        節點類型到執行類的映射
    """
    return {type_name: meta.executor for type_name, meta in _NODE_REGISTRY.items()}


def get_node_metadata(node_type: str) -> Optional[NodeMetadata]:
    """獲取節點元數據
    
    Args:
        node_type: 節點類型
        
    Returns:
        節點元數據，不存在則返回None
    """
    return _NODE_REGISTRY.get(node_type)


def get_all_node_metadata() -> List[NodeMetadata]:
    """獲取所有節點元數據
    
    Returns:
        節點元數據列表
    """
    return list(_NODE_REGISTRY.values())


def get_node_types() -> List[str]:
    """獲取所有已註冊的節點類型名稱
    
    Returns:
        節點類型名稱列表
    """
    return list(_NODE_REGISTRY.keys())


def get_nodes_by_category(category: str) -> List[NodeMetadata]:
    """按分類獲取節點
    
    Args:
        category: 分類名稱
        
    Returns:
        該分類下的所有節點元數據
    """
    return [meta for meta in _NODE_REGISTRY.values() if meta.category == category]


class NodeRegistry:
    """節點註冊表包裝類
    
    提供節點類型檢查和獲取接口
    """

    def has_node(self, node_type: str) -> bool:
        """檢查節點類型是否存在"""
        return node_type in _NODE_REGISTRY

    def get(self, node_type: str) -> Optional[Callable]:
        """獲取節點執行器"""
        meta = _NODE_REGISTRY.get(node_type)
        return meta.executor if meta else None
    
    def list_nodes(self) -> List[str]:
        """列出所有已註冊的節點類型"""
        return list(_NODE_REGISTRY.keys())


def discover_workflow_nodes():
    """記錄已註冊的工作流節點數量

    所有工作流節點模塊已在 app.services.workflow.__init__.py 中導入，
    裝飾器在包導入時自動執行註冊。
    """
    logger.info(f"[節點發現] 已加載 {len(_NODE_REGISTRY)} 個工作流節點")

    # 按分類統計
    categories = {}
    for meta in _NODE_REGISTRY.values():
        categories[meta.category] = categories.get(meta.category, 0) + 1

    for cat, count in categories.items():
        logger.debug(f"  - {cat}: {count} 個節點")
