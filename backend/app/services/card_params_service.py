"""卡片參數服務

負責卡片 AI 參數的合併、驗證等業務邏輯。
"""

from typing import Dict, Any
from sqlmodel import Session
from app.db.models import Card, LLMConfig
from loguru import logger


def merge_effective_ai_params(session: Session, card: Card) -> Dict[str, Any]:
    """合併卡片的有效 AI 參數
    
    合併邏輯：
    1. 基礎參數來自 CardType.ai_params
    2. 覆蓋參數來自 Card.ai_params
    3. 補齊缺失的 llm_config_id（選擇 ID 最小的 LLM）
    4. 規範化類型
    
    Args:
        session: 數據庫會話
        card: 卡片對象
        
    Returns:
        合併後的有效參數字典
    """
    # 獲取基礎參數（來自類型）
    base = (card.card_type.ai_params if card.card_type and card.card_type.ai_params else {}) or {}
    
    # 獲取覆蓋參數（來自實例）
    override = (card.ai_params or {})
    
    # 合併參數
    effective = {**base, **override}
    
    # 補齊 llm_config_id（如果缺失）
    if effective.get("llm_config_id") in (None, 0, "0", ""):
        try:
            # 選用 ID 最小的 LLM 作爲默認值
            llm = session.query(LLMConfig).order_by(LLMConfig.id.asc()).first()  # type: ignore
            if llm:
                effective["llm_config_id"] = int(getattr(llm, "id", 0))
        except Exception as e:
            logger.warning(f"獲取默認 LLM 配置失敗: {e}")
    
    # 規範化 llm_config_id 類型
    if effective.get("llm_config_id") is not None:
        try:
            effective["llm_config_id"] = int(effective.get("llm_config_id"))
        except (ValueError, TypeError):
            pass
    
    return effective
