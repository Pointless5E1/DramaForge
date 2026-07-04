"""文本處理工具

純函數實現，無外部依賴。
"""


def truncate_text(text: str, limit: int, suffix: str = "\n...[已截斷]") -> str:
    """截斷文本到指定長度
    
    Args:
        text: 待截斷的文本
        limit: 最大長度
        suffix: 截斷後綴
        
    Returns:
        截斷後的文本
    """
    if len(text) <= limit:
        return text
    # 預留suffix長度，避免截斷後超出limit
    truncate_at = max(0, limit - len(suffix))
    return text[:truncate_at] + suffix
