from __future__ import annotations

from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field



# 擴展後的關係類型（中文枚舉，保持單一來源）
RelationKind = Literal[
    # 人物關係
    '同盟','隊友','同門','敵對','親屬','師徒','對手','夥伴','上級','下屬','指導',
    # 人物 ↔ 組織
    '隸屬','成員','領導','創立',
    # 實體與物品/概念
    '擁有','使用','修煉','領悟','承載','映射',
    # 組織 ↔ 場景
    '控制','位於',
    # 泛用與兜底
    '影響','剋制','關於','其他'
]
RelationStance = Literal['友好', '中立', '敵意']
RELATION_STANCES: tuple[RelationStance, ...] = ('友好', '中立', '敵意')

# 統一提供中英映射（單一來源）——保留兼容（如已有英文入圖/讀圖邏輯）
CN_TO_EN_KIND: Dict[str, str] = {
    '同盟': 'ally',
    '隊友': 'team',
    '同門': 'fellow',
    '敵對': 'enemy',
    '親屬': 'family',
    '師徒': 'mentor',
    '對手': 'rival',
    '夥伴': 'partner',
    '上級': 'superior',
    '下屬': 'subordinate',
    '指導': 'guide',

    '隸屬': 'member_of',
    '成員': 'member',
    '領導': 'lead',
    '創立': 'found',

    '擁有': 'own',
    '使用': 'use',
    '修煉': 'practice',
    '領悟': 'realize',
    '承載': 'carry',
    '映射': 'map_to',


    '控制': 'control',
    '位於': 'locate_in',

    '影響': 'influence',
    '剋制': 'counter',
    '關於': 'about',
    '其他': 'other',
}
EN_TO_CN_KIND: Dict[str, str] = {v: k for k, v in CN_TO_EN_KIND.items()}


class RecentEventSummary(BaseModel):
    summary: str = Field(description="A、B 之間近期發生事件的一句摘要（本次提取建議融合爲一條）")
    volume_number: Optional[int] = Field(default=None, description="發生的卷號（置空，系統可補全）")
    chapter_number: Optional[int] = Field(default=None, description="發生的章節號（置空，系統可補全）")


class RelationItem(BaseModel):
    a: str = Field(description="實體 A 名稱（參與者之一）")
    b: str = Field(description="實體 B 名稱（參與者之一）")
    kind: RelationKind = Field(description="關係類型（中文）")
    description: Optional[str] = Field(default=None, description="對該關係的簡要文字說明（可選）")
    # 互相稱呼（可選，無需出現在近期對話中）
    a_to_b_addressing: Optional[str] = Field(default=None, description="A 對 B 的稱呼詞，如：師兄、先生。僅當 A, B 均爲角色時提取。")
    b_to_a_addressing: Optional[str] = Field(default=None, description="B 對 A 的稱呼詞。僅當 A, B 均爲角色時提取。")
    # 近期證據（用於語氣一致性與事實回溯）——建議各 ≤3 條
    recent_dialogues: List[str] = Field(default_factory=list, description="近期對話片段（建議包含雙方各至少一句，可用 A:“…”, B:“…” 合併片段；長度≥20字）。僅當 A, B 均爲角色時提取。")
    recent_event_summaries: List[RecentEventSummary] = Field(default_factory=list, description="近期 A 與 B 直接發生在彼此之間的事件；若同一事實涉及三方或以上，僅在最直接的一對上記錄一次。優先記錄角色-角色的配對；當事件主體確係 A 與 B 爲角色-組織/組織-組織時再記錄相應關係，避免將組織背景誤當作雙邊事件。")
    # 立場（可選）：友好/中立/敵意
    stance: Optional[RelationStance] = Field(default=None, description="A 對 B 的總體立場（可選）")


class RelationExtraction(BaseModel):
    relations: List[RelationItem] = Field(default_factory=list) 
