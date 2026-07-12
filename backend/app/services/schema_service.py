"""Schema 服務層

負責 Schema 的組裝、引用解析、$defs 補全等業務邏輯。
"""

import re
from typing import Dict, Any, Set
from copy import deepcopy
from sqlmodel import Session
from app.db.models import CardType
from app.schemas.entity import DYNAMIC_INFO_TYPES
from app.schemas import entity as entity_schemas
from loguru import logger


# --- Schema 引用收集 ---

FIELD_TITLE_ZH_MAP: Dict[str, str] = {
    "content": "內容",
    "theme": "主題",
    "audience": "目標讀者",
    "narrative_person": "敘事人稱",
    "story_tags": "故事標籤",
    "affection": "情感關係",
    "name": "名稱",
    "description": "描述",
    "special_abilities_thinking": "金手指設計思考",
    "special_abilities": "金手指",
    "one_sentence_thinking": "一句話梗概思考",
    "one_sentence": "一句話梗概",
    "overview_thinking": "大綱擴展思考",
    "overview": "概述",
    "world_view_thinking": "世界觀設計思考",
    "world_view": "世界觀",
    "title": "標題",
    "entity_type": "實體類型",
    "life_span": "生命跨度",
    "role_type": "角色類型",
    "born_scene": "出生場景",
    "personality": "性格",
    "core_drive": "核心驅動力",
    "character_arc": "角色弧光",
    "influence": "影響力",
    "relationship": "關係",
    "dynamic_info": "動態信息",
    "last_appearance": "最後出場時間",
    "social_system": "社會體系",
    "civilization_level": "科技／文明發展水平",
    "power_systems": "核心體系列表",
    "system_type": "體系類型",
    "levels": "等級／階層劃分",
    "source": "能量／權力來源",
}

MODEL_TITLE_ZH_MAP: Dict[str, str] = {
    "WorldBuilding": "世界觀設定",
    "WorldviewTemplate": "世界觀",
    "SocialSystem": "社會體系",
    "CoreSystem": "核心體系",
    "SpecialAbility": "金手指",
    "CharacterCard": "角色",
    "SceneCard": "場景",
    "OrganizationCard": "組織／勢力",
    "SettingItem": "世界觀設定項目",
    "CharacterAction": "角色行動",
    "StoryLine": "故事線",
    "ChapterOutline": "章節大綱",
}

ARRAY_ITEM_TITLE_ZH_MAP: Dict[str, str] = {
    "special_abilities": "金手指",
    "currency_system": "貨幣",
    "major_power_camps": "組織／勢力",
    "power_systems": "核心體系",
    "character_cards": "角色",
    "scene_cards": "場景",
    "new_character_cards": "角色",
    "new_scene_cards": "場景",
    "branch_line": "輔線",
    "character_action_list": "角色行動",
    "entity_snapshot": "實體狀態",
    "chapter_outline_list": "章節大綱",
    "entity_list": "實體",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _derive_title_from_description(description: Any) -> str | None:
    if not isinstance(description, str):
        return None
    desc = description.strip()
    if not desc or not _contains_cjk(desc):
        return None

    candidate = re.split(r"[，。；;！？:：\n（(]", desc, maxsplit=1)[0].strip()
    if not candidate:
        return None
    if len(candidate) > 16:
        candidate = candidate[:16].strip()
    return candidate or None


def localize_schema_titles(schema: Any) -> Any:
    """將 schema 字段標題本地化爲中文（不修改字段 key）。"""
    if not isinstance(schema, (dict, list)):
        return schema

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            current_node_title = str(node.get("title") or "")
            if current_node_title in MODEL_TITLE_ZH_MAP:
                node["title"] = MODEL_TITLE_ZH_MAP[current_node_title]

            properties = node.get("properties")
            if isinstance(properties, dict):
                for field_name, field_schema in properties.items():
                    if isinstance(field_schema, dict):
                        current_title = str(field_schema.get("title") or "")
                        if not _contains_cjk(current_title):
                            localized = FIELD_TITLE_ZH_MAP.get(field_name) or _derive_title_from_description(
                                field_schema.get("description")
                            )
                            if localized:
                                field_schema["title"] = localized
                        item_title = ARRAY_ITEM_TITLE_ZH_MAP.get(field_name)
                        if item_title and "x-item-title" not in field_schema:
                            field_schema["x-item-title"] = item_title

            for defs_key in ("$defs", "definitions"):
                defs = node.get(defs_key)
                if isinstance(defs, dict):
                    for def_name, def_schema in defs.items():
                        if isinstance(def_schema, dict) and def_name in MODEL_TITLE_ZH_MAP:
                            def_schema["title"] = MODEL_TITLE_ZH_MAP[def_name]
                        visit(def_schema)

            items = node.get("items")
            if isinstance(items, dict):
                visit(items)

            prefix_items = node.get("prefixItems")
            if isinstance(prefix_items, list):
                for item in prefix_items:
                    visit(item)

            for union_key in ("anyOf", "oneOf", "allOf"):
                variants = node.get(union_key)
                if isinstance(variants, list):
                    for variant in variants:
                        visit(variant)

            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)

        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    return schema

def collect_ref_names(node: Any) -> Set[str]:
    """遞歸收集 Schema 中的所有 $ref 引用名稱
    
    Args:
        node: Schema 節點（dict/list/其他）
        
    Returns:
        引用名稱集合
    """
    names: Set[str] = set()
    if isinstance(node, dict):
        if '$ref' in node and isinstance(node['$ref'], str) and node['$ref'].startswith('#/$defs/'):
            names.add(node['$ref'].split('/')[-1])
        for v in node.values():
            names |= collect_ref_names(v)
    elif isinstance(node, list):
        for it in node:
            names |= collect_ref_names(it)
    return names


# --- 內置模型 $defs 緩存 ---

_BUILTIN_DEFS_CACHE: Dict[str, Any] | None = None

def get_builtin_defs() -> Dict[str, Any]:
    """獲取所有內置 Pydantic 模型的 $defs（帶緩存）
    
    Returns:
        合併後的 $defs 字典
    """
    global _BUILTIN_DEFS_CACHE
    if _BUILTIN_DEFS_CACHE is not None:
        return _BUILTIN_DEFS_CACHE
    
    # 導入響應模型映射
    from app.schemas.response_registry import RESPONSE_MODEL_MAP
    
    merged: Dict[str, Any] = {}
    for _, model_class in RESPONSE_MODEL_MAP.items():
        sch = model_class.model_json_schema(ref_template="#/$defs/{model}")
        sch = localize_schema_titles(sch)
        defs = sch.get('$defs') or {}
        merged.update(defs)
    
    _BUILTIN_DEFS_CACHE = merged
    return merged


def augment_schema_with_builtin_defs(schema: Dict[str, Any]) -> Dict[str, Any]:
    """將內置模型的 $defs 注入到自定義 Schema 中
    
    Args:
        schema: 原始 Schema
        
    Returns:
        增強後的 Schema（深拷貝）
    """
    sch = deepcopy(schema) if schema is not None else {}
    if not isinstance(sch, dict):
        return sch
    
    # 收集所有引用
    ref_names = collect_ref_names(sch)
    if not ref_names:
        return localize_schema_titles(sch)
    
    # 獲取內置 defs
    builtin_defs = get_builtin_defs()
    
    # 確保有 $defs
    if '$defs' not in sch:
        sch['$defs'] = {}
    
    # 注入被引用的內置定義
    for name in ref_names:
        if name in builtin_defs and name not in sch['$defs']:
            sch['$defs'][name] = builtin_defs[name]

    return localize_schema_titles(sch)


# --- CardType Schema 組裝 ---

def compose_schema_with_card_types(session: Session, schema: Dict[str, Any]) -> Dict[str, Any]:
    """將 CardType 的 Schema 注入到 $defs 中
    
    Args:
        session: 數據庫會話
        schema: 原始 Schema
        
    Returns:
        增強後的 Schema（深拷貝）
    """
    sch = deepcopy(schema) if isinstance(schema, dict) else {}
    if not isinstance(sch, dict):
        return sch
    
    # 確保有 $defs
    if '$defs' not in sch:
        sch['$defs'] = {}
    
    # 收集所有引用
    ref_names = collect_ref_names(sch)
    if not ref_names:
        return localize_schema_titles(sch)
    
    # 查詢所有 CardType，建立映射
    all_types = session.query(CardType).all()
    by_model: Dict[str, Any] = {}
    
    for ct in all_types:
        if ct and ct.json_schema:
            localized_schema = localize_schema_titles(deepcopy(ct.json_schema))
            if ct.model_name:
                by_model[ct.model_name] = localized_schema
            by_model[ct.name] = localized_schema
    
    # 注入被引用的 CardType Schema
    for name in ref_names:
        if name in by_model:
            sch['$defs'][name] = by_model[name]

    return localize_schema_titles(sch)


def compose_full_schema(session: Session, schema: Dict[str, Any]) -> Dict[str, Any]:
    """完整的 Schema 組裝：內置 defs + CardType defs
    
    Args:
        session: 數據庫會話
        schema: 原始 Schema
        
    Returns:
        完全增強後的 Schema
    """
    # 先注入內置 defs
    sch = augment_schema_with_builtin_defs(schema)
    # 再注入 CardType defs
    sch = compose_schema_with_card_types(session, sch)
    return localize_schema_titles(sch)
