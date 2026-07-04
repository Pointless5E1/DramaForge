from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

DynamicInfoType = Literal[
    "系統/模擬器/金手指信息",
    "等級/修爲境界",
    "裝備/法寶",
    "知識/情報",
    "資產/領地",
    "功法/技能",
    "血脈/體質",
    "心理想法/目標快照",
]

DYNAMIC_INFO_TYPES: List[str] = [
    "系統/模擬器/金手指信息",
    "等級/修爲境界",
    "裝備/法寶",
    "知識/情報",
    "資產/領地",
    "功法/技能",
    "血脈/體質",
    "心理想法/目標快照",
]

EntityType = Literal["character", "scene", "organization", "item", "concept"]


class DynamicInfoItem(BaseModel):
    id: int = Field(-1, description="手動設置，無需生成；併入時若爲 -1 將自動分配順序號")
    info: str = Field(description="簡要描述具體動態信息")


class DynamicInfo(BaseModel):
    name: str = Field(description="角色名稱")
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(
        default_factory=dict,
        description="動態信息字典，鍵爲中文類別，值爲信息項列表",
    )

    @staticmethod
    def _normalize_dynamic_info_dict(v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        normalized: Dict[str, Any] = {}
        allowed = set(DYNAMIC_INFO_TYPES)
        for k, arr in v.items():
            key = k if isinstance(k, str) else str(k)
            if key in allowed:
                normalized[key] = arr
        return normalized

    @field_validator("dynamic_info", mode="before")
    @classmethod
    def _normalize_keys(cls, v: Any) -> Dict[str, Any]:
        return cls._normalize_dynamic_info_dict(v)


class DeletionInfo(BaseModel):
    name: str = Field(description="角色名稱")
    dynamic_type: DynamicInfoType = Field(description="動態信息類型")
    id: int = Field(gt=0, description="要刪除的動態信息 ID")


class UpdateDynamicInfo(BaseModel):
    info_list: List[DynamicInfo] = Field(description="需要更新的動態信息列表")
    delete_info_list: Optional[List[DeletionInfo]] = Field(default=None, description="可選的刪除列表")


class Entity(BaseModel):
    name: str = Field(..., min_length=1, description="實體名稱")
    entity_type: EntityType = Field(..., description="實體類型")
    life_span: Literal["長期", "短期"] = Field(description="實體在故事中的生命週期")


class CharacterCardCore(Entity):
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最後出現時間：[卷號, 章節號]")
    role_type: Literal["主角", "主角團配角", "普通NPC", "反派"] = Field("主角團配角", description="角色定位")
    born_scene: str = Field(description="出場/常駐場景")
    description: str = Field(description="一句話簡介與背景說明")


class CharacterCard(CharacterCardCore):
    entity_type: EntityType = Field("character", description="實體類型標記")
    personality: str = Field(description="性格關鍵詞")
    core_drive: str = Field(description="核心驅動力/目標")
    character_arc: str = Field(description="角色在全書中的弧光")
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(
        default_factory=dict,
        description="動態信息字典，留空，系統會自動維護",
    )

    @field_validator("dynamic_info", mode="before")
    @classmethod
    def _normalize_dynamic_info(cls, v: Any) -> Dict[str, Any]:
        return DynamicInfo._normalize_dynamic_info_dict(v)


class SceneCard(Entity):
    entity_type: EntityType = Field("scene", description="實體類型標記")
    description: str = Field(description="場景/地圖一句話簡介")
    function_in_story: str = Field(description="在劇情中的作用")
    dynamic_state: List[str] = Field(default_factory=list, description="當前狀態，由系統逐步補充維護")
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最後出現時間：[卷號, 章節號]")


class OrganizationCard(Entity):
    entity_type: EntityType = Field("organization", description="實體類型標記")
    description: str = Field(description="組織/勢力陣營描述")
    influence: Optional[str] = Field(default=None, description="該組織對世界的影響範圍/影響力")
    relationship: Optional[List[str]] = Field(default=None, description="與其他組織的關係")
    dynamic_state: List[str] = Field(default_factory=list, description="當前狀態，由系統逐步補充維護")
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最後出現時間：[卷號, 章節號]")


class SceneCardMemory(Entity):
    entity_type: EntityType = Field("scene", description="scene entity type")
    life_span: Optional[Literal["長期", "短期"]] = Field(default=None, description="scene lifespan")
    description: str = Field(default="", description="scene description")
    function_in_story: str = Field(default="", description="scene function in story")
    dynamic_state: List[str] = Field(default_factory=list, description="scene dynamic state summary")


class OrganizationCardMemory(Entity):
    entity_type: EntityType = Field("organization", description="organization entity type")
    life_span: Optional[Literal["長期", "短期"]] = Field(default=None, description="organization lifespan")
    description: str = Field(default="", description="organization description")
    influence: Optional[str] = Field(default=None, description="organization influence")
    relationship: List[str] = Field(default_factory=list, description="organization relationships")
    dynamic_state: List[str] = Field(default_factory=list, description="organization dynamic state summary")


class ItemCard(Entity):
    entity_type: EntityType = Field("item", description="實體類型")
    life_span: Literal["長期", "短期"] = Field("長期", description="物品在故事中的生命週期")
    category: str = Field(
        default="",
        description="物品類別",
        json_schema_extra={"x-knowledge-source": "物品類別"},
    )
    description: str = Field(default="", description="物品的一句話簡介或背景說明")
    owner_hint: Optional[str] = Field(default=None, description="當前或常見持有者")
    power_or_effect: Optional[str] = Field(default=None, description="物品能力、效果或用途")
    constraints: Optional[str] = Field(default=None, description="使用限制、代價或觸發條件")
    current_state: Optional[str] = Field(default=None, description="物品當前狀態")
    important_events: List[str] = Field(default_factory=list, description="與物品相關的重要事件摘要")

class ConceptCard(Entity):
    entity_type: EntityType = Field("concept", description="實體類型")
    life_span: Literal["長期", "短期"] = Field("長期", description="概念在故事中的生命週期")
    category: str = Field(
        default="",
        description="概念類別",
        json_schema_extra={"x-knowledge-source": "概念類別"},
    )
    description: str = Field(default="", description="概念簡介")
    rule_definition: str = Field(default="", description="規則定義、適用方式或核心機制")
    cost: Optional[str] = Field(default=None, description="使用或掌握該概念的代價")
    counter_relations: List[str] = Field(default_factory=list, description="對立、剋制或限制關係")
    mastery_hint: Optional[str] = Field(default=None, description="掌握門檻、領悟方式或常見使用者")
    known_by: List[str] = Field(default_factory=list, description="已知掌握、知曉或受影響的實體")
