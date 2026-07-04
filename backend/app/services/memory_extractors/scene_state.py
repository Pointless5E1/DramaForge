from __future__ import annotations

from typing import Any

from app.db.models import Card
from app.schemas.entity import SceneCard, SceneCardMemory
from app.schemas.memory import SceneStateExtraction
from app.services.memory_extractors.memory_base import (
    StructuredCardExtractorSpec,
    StructuredCardMemoryExtractor,
    merge_optional_text,
    unique_keep_order,
)


def _merge_scene_card(existing: SceneCard, incoming: SceneCardMemory) -> SceneCard:
    return SceneCard(
        name=incoming.name or existing.name,
        entity_type="scene",
        life_span=incoming.life_span or existing.life_span,
        description=merge_optional_text(existing.description, incoming.description) or "",
        function_in_story=merge_optional_text(existing.function_in_story, incoming.function_in_story) or "",
        dynamic_state=unique_keep_order([*(existing.dynamic_state or []), *(incoming.dynamic_state or [])])[-8:],
        last_appearance=existing.last_appearance,
    )


def _load_existing_scene_card(card: Card) -> SceneCard:
    payload = dict(card.content or {})
    payload.setdefault("name", card.title)
    payload.setdefault("entity_type", "scene")
    payload.setdefault("life_span", "長期")
    payload["description"] = payload.get("description") or ""
    payload["function_in_story"] = payload.get("function_in_story") or ""
    if not isinstance(payload.get("dynamic_state"), list):
        payload["dynamic_state"] = []
    return SceneCard.model_validate(payload)


_SPEC = StructuredCardExtractorSpec(
    code="scene_state",
    name="場景狀態提取",
    prompt_name="場景狀態提取",
    card_type_name="場景卡",
    output_model=SceneStateExtraction,
    list_field_name="scenes",
    target_participant_types=("scene",),
    related_participant_types=("organization", "character", "item", "concept"),
    target_participant_key="scene_names",
    related_participant_key="related_entities",
    reference_title="已有場景卡參考",
)


class SceneStateExtractor(StructuredCardMemoryExtractor):
    def __init__(self):
        super().__init__(_SPEC)

    def load_existing_card(self, card: Card) -> SceneCard:
        return _load_existing_scene_card(card)

    def merge_card(self, existing: SceneCard, incoming: SceneCardMemory) -> SceneCard:
        return _merge_scene_card(existing, incoming)

    def build_reference_lines(self, model: SceneCard) -> list[str]:
        return [
            f"- {model.name}",
            f"  簡介: {model.description or '未填寫'}",
            f"  劇情作用: {model.function_in_story or '未填寫'}",
            f"  當前狀態: {'；'.join(model.dynamic_state or []) or '暫無'}",
        ]
