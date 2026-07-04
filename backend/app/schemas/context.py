from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.relation_extract import RelationItem


class AssembleContextRequest(BaseModel):
	project_id: Optional[int] = Field(default=None, description="項目ID")
	volume_number: Optional[int] = Field(default=None, description="卷號")
	chapter_number: Optional[int] = Field(default=None, description="章節號")
	chapter_id: Optional[int] = Field(default=None, description="章節卡片ID（可選）")
	participants: Optional[List[str]] = Field(default=None, description="參與實體名稱列表")
	current_draft_tail: Optional[str] = Field(default=None, description="上下文模板（草稿尾部）")
	recent_chapters_window: Optional[int] = Field(default=None, description="最近窗口（保留，將來擴展）")


class ItemSummary(BaseModel):
	name: str = Field(..., description="物品名稱")
	category: str = Field(default="", description="物品類別")
	description: str = Field(default="", description="物品簡介")
	owner_hint: Optional[str] = Field(default=None, description="持有者提示")
	current_state: Optional[str] = Field(default=None, description="當前狀態")
	power_or_effect: Optional[str] = Field(default=None, description="能力或用途")
	constraints: Optional[str] = Field(default=None, description="限制條件")
	important_events: List[str] = Field(default_factory=list, description="重要事件")


class ConceptSummary(BaseModel):
	name: str = Field(..., description="概念名稱")
	category: str = Field(default="", description="概念類別")
	description: str = Field(default="", description="概念簡介")
	rule_definition: str = Field(default="", description="規則定義")
	cost: Optional[str] = Field(default=None, description="代價或成本")
	mastery_hint: Optional[str] = Field(default=None, description="掌握提示")
	known_by: List[str] = Field(default_factory=list, description="已知掌握者")
	counter_relations: List[str] = Field(default_factory=list, description="對立或剋制關係")


class FactsStructured(BaseModel):
	fact_summaries: List[str] = Field(default_factory=list, description="關鍵事實摘要")
	relation_summaries: List[RelationItem] = Field(default_factory=list, description="關係摘要（含近期對話/事件）")
	item_summaries: List[ItemSummary] = Field(default_factory=list, description="物品摘要")
	concept_summaries: List[ConceptSummary] = Field(default_factory=list, description="概念摘要")


class AssembleContextResponse(BaseModel):
	facts_subgraph: str = Field(default="", description="事實子圖的文本回顯（可選，僅回顯）")
	budget_stats: Dict[str, Any] = Field(default_factory=dict, description="上下文字數預算統計（可能包含嵌套 parts dict）")
	facts_structured: Optional[FactsStructured] = Field(default=None, description="結構化事實子圖")


class ContextSettingsModel(BaseModel):
	recent_chapters_window: int
	total_context_budget_chars: int
	soft_budget_chars: int
	quota_recent: int
	quota_older_summary: int
	quota_facts: int


class UpdateContextSettingsRequest(BaseModel):
	recent_chapters_window: Optional[int] = None
	total_context_budget_chars: Optional[int] = None
	soft_budget_chars: Optional[int] = None
	quota_recent: Optional[int] = None
	quota_older_summary: Optional[int] = None
	quota_facts: Optional[int] = None
