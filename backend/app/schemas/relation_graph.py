from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.relation_extract import RelationKind, RelationStance


CsvJsonFormat = Literal["json", "csv"]


class RelationGraphEvent(BaseModel):
    summary: str = Field(description="事件摘要")
    volume_number: Optional[int] = Field(default=None, description="卷號")
    chapter_number: Optional[int] = Field(default=None, description="章節號")


class RelationGraphKey(BaseModel):
    source: str = Field(description="關係起點實體")
    target: str = Field(description="關係終點實體")
    kind_en: str = Field(description="關係英文鍵")


class RelationGraphInput(BaseModel):
    source: str = Field(description="關係起點實體")
    target: str = Field(description="關係終點實體")
    kind_en: Optional[str] = Field(default=None, description="關係英文鍵")
    kind_cn: Optional[RelationKind] = Field(default=None, description="關係中文類型")
    kind: Optional[RelationKind] = Field(default=None, description="關係中文類型（兼容字段）")
    fact: Optional[str] = Field(default=None, description="關係事實描述")
    description: Optional[str] = Field(default=None, description="關係描述")
    a_to_b_addressing: Optional[str] = Field(default=None, description="A 對 B 稱呼")
    b_to_a_addressing: Optional[str] = Field(default=None, description="B 對 A 稱呼")
    recent_dialogues: List[str] = Field(default_factory=list, description="近期對話證據")
    recent_event_summaries: List[RelationGraphEvent] = Field(default_factory=list, description="近期事件證據")
    stance: Optional[RelationStance] = Field(default=None, description="立場：友好/中立/敵意")


class RelationGraphRecord(BaseModel):
    source: str
    target: str
    kind_en: str
    kind_cn: RelationKind
    kind: RelationKind
    fact: str
    a_to_b_addressing: Optional[str] = None
    b_to_a_addressing: Optional[str] = None
    recent_dialogues: List[str] = Field(default_factory=list)
    recent_event_summaries: List[RelationGraphEvent] = Field(default_factory=list)
    stance: Optional[RelationStance] = None
    updated_at: Optional[str] = None


class RelationGraphListRequest(BaseModel):
    project_id: int
    keyword: Optional[str] = None
    kinds: List[RelationKind] = Field(default_factory=list)
    stances: List[RelationStance] = Field(default_factory=list)
    offset: int = 0
    limit: int = 50


class RelationGraphListResponse(BaseModel):
    items: List[RelationGraphRecord] = Field(default_factory=list)
    total: int = 0


class RelationGraphUpsertRequest(BaseModel):
    project_id: int
    relation: RelationGraphInput


class RelationGraphDeleteRequest(BaseModel):
    project_id: int
    key: RelationGraphKey


class RelationGraphBatchDeleteRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)


class RelationGraphBatchUpdateKindRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)
    new_kind_en: Optional[str] = Field(default=None, description="新的關係英文鍵")
    new_kind_cn: Optional[RelationKind] = Field(default=None, description="新的關係中文類型")


class RelationGraphBatchUpdateStanceRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)
    stance: Optional[RelationStance] = Field(default=None, description="新立場")


class RelationGraphBatchAppendEventsRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)
    events: List[RelationGraphEvent] = Field(default_factory=list)
    max_size: int = 20


class RelationGraphBatchCreateRequest(BaseModel):
    project_id: int
    relations: List[RelationGraphInput] = Field(default_factory=list)


class RelationGraphWriteResponse(BaseModel):
    affected: int = 0


class RelationGraphExportRequest(BaseModel):
    project_id: int
    format: CsvJsonFormat = "json"
    keys: List[RelationGraphKey] = Field(default_factory=list)


class RelationGraphExportResponse(BaseModel):
    filename: str
    mime_type: str
    content: str


class RelationGraphImportRequest(BaseModel):
    project_id: int
    format: CsvJsonFormat = "json"
    content: str


class RelationGraphImportResponse(BaseModel):
    created: int = 0
    updated: int = 0
    failed: int = 0
    errors: List[str] = Field(default_factory=list)


class RelationGraphKindOption(BaseModel):
    kind_cn: RelationKind
    kind_en: str


class RelationGraphMetaResponse(BaseModel):
    kinds: List[RelationGraphKindOption] = Field(default_factory=list)
    stances: List[RelationStance] = Field(default_factory=list)
