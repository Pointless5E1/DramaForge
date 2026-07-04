"""卡片類型初始化

初始化默認卡片類型及其Schema定義。
"""

import re
from typing import Any, Dict

from sqlmodel import Session, select
from loguru import logger

from app.core.config import settings
from app.db.models import Card, CardType, LLMConfig
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from .registry import initializer


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
    "power_structure": "權力結構",
    "currency_system": "貨幣體系",
    "background": "背景",
    "major_power_camps": "主要勢力陣營",
    "world_view_thinking": "世界觀設計思考",
    "world_view": "世界觀",
    "volume_count": "總卷數",
    "character_thinking": "角色設計思考",
    "character_cards": "角色卡",
    "scene_thinking": "場景設計思考",
    "scene_cards": "場景卡",
    "organization_thinking": "組織設計思考",
    "organization_cards": "組織卡",
    "volume_number": "卷號",
    "title": "標題",
    "main_target": "主線目標",
    "branch_line": "輔線",
    "new_character_cards": "新增角色卡",
    "new_scene_cards": "新增場景卡",
    "stage_count": "階段數量",
    "character_action_list": "角色行動列表",
    "entity_snapshot": "實體狀態快照",
    "stage_number": "階段號",
    "chapter_number": "章節號",
    "entity_list": "實體列表",
    "stage_name": "階段名稱",
    "reference_chapter": "參考章節範圍",
    "analysis": "分析",
    "chapter_outline_list": "章節大綱列表",
    "entity_type": "實體類型",
    "life_span": "生命週期",
    "role_type": "角色類型",
    "born_scene": "出生場景",
    "personality": "性格",
    "core_drive": "核心驅動力",
    "character_arc": "角色弧光",
    "influence": "影響力",
    "relationship": "關係",
    "dynamic_info": "動態信息",
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

    candidate = re.split(r"[，。；;：:（(\n]", desc, maxsplit=1)[0].strip()
    if not candidate:
        return None
    if len(candidate) > 16:
        candidate = candidate[:16].strip()
    return candidate or None


def _localize_schema_titles(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for field_name, field_schema in properties.items():
                    if not isinstance(field_schema, dict):
                        continue
                    current_title = str(field_schema.get("title") or "")
                    if not _contains_cjk(current_title):
                        localized = FIELD_TITLE_ZH_MAP.get(field_name) or _derive_title_from_description(
                            field_schema.get("description")
                        )
                        if localized:
                            field_schema["title"] = localized
                    visit(field_schema)

            defs = node.get("$defs")
            if isinstance(defs, dict):
                for def_schema in defs.values():
                    visit(def_schema)

            items = node.get("items")
            if isinstance(items, dict):
                visit(items)

            for union_key in ("anyOf", "oneOf", "allOf"):
                variants = node.get(union_key)
                if isinstance(variants, list):
                    for variant in variants:
                        visit(variant)

        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    return schema

@initializer(name="卡片類型", order=20)
def create_default_card_types(session: Session) -> None:
    """初始化默認卡片類型
    
    創建所有內置卡片類型及其Schema、AI參數預設等。
    
    Args:
        session: 數據庫會話
    """
    stage_review_context_template = (
        "世界觀設定: @世界觀設定.content.world_view\n"
        "組織/勢力設定:@type:組織卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
        "分卷主線:@parent.content.main_target\n"
        "分卷輔線:@parent.content.branch_line\n"
        "角色卡信息:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.born_scene,content.description,content.personality,content.core_drive,content.character_arc}\n"
        "地圖/場景卡信息:@type:場景卡[previous].{content.name,content.description}\n"
        "之前的階段故事大綱:@type:階段大綱[previous:global:1].{content.stage_name,content.reference_chapter,content.analysis,content.overview,content.entity_snapshot}\n"
        "上一章節大綱概述:@type:章節大綱[previous:global:1].{content.title,content.overview,content.entity_list}\n"
        "本卷的StageCount總數爲：@parent.content.stage_count\n"
        "卷末實體狀態快照:@parent.content.entity_snapshot\n"
    )

    chapter_review_context_template = (
        "世界觀設定: @世界觀設定.content\n"
        "組織/勢力設定:@type:組織卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.influence,content.relationship,content.dynamic_state}\n"
        "場景卡:@type:場景卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.dynamic_state}\n"
        "當前故事階段大綱: @parent.content.overview\n"
        "角色卡:@type:角色卡[index=filter:content.name in $self.content.entity_list].{content.name,content.role_type,content.born_scene,content.description,content.personality,content.core_drive,content.character_arc,content.dynamic_info}\n"
        "物品卡:@type:物品卡[index=filter:content.name in $self.content.entity_list].{content.name,content.category,content.description,content.current_state,content.power_or_effect}\n"
        "概念卡:@type:概念卡[index=filter:content.name in $self.content.entity_list].{content.name,content.category,content.description,content.rule_definition,content.mastery_hint}\n"
        "最近的章節原文:@type:章節正文[previous:1].{content.title,content.chapter_number,content.content}\n"
        "參與者實體列表:@self.content.entity_list\n"
        "當前章節大綱:@type:章節大綱[index=filter:content.volume_number = $self.content.volume_number&&content.stage_number= $self.content.stage_number&&content.chapter_number= $self.content.chapter_number].{content.title,content.overview,content.entity_list}\n"
        "下一章節大綱:@type:章節大綱[index=filter:content.volume_number = $self.content.volume_number && content.chapter_number = $self.content.chapter_number+1].{content.title,content.overview,content.entity_list}\n"
    )

    default_types = {
        "通用文本": {"editor_component": "MarkdownTextEditor", "is_singleton": False, "is_ai_enabled": False, "default_ai_context_template": None},
        "作品標籤": {"editor_component": "TagsEditor", "is_singleton": True, "is_ai_enabled": False, "default_ai_context_template": None},
        "金手指": {"is_singleton": True, "default_ai_context_template": "作品標籤: @作品標籤.content"},
        "一句話梗概": {"is_singleton": True, "default_ai_context_template": "作品標籤: @作品標籤.content\n金手指/特殊能力: @金手指.content.special_abilities"},
        "故事大綱": {"is_singleton": True, "default_ai_context_template": "作品標籤: @作品標籤.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事梗概: @一句話梗概.content.one_sentence"},
        "世界觀設定": {"is_singleton": True, "default_ai_context_template": "作品標籤: @作品標籤.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大綱: @故事大綱.content.overview"},
        "核心藍圖": {"is_singleton": True, "default_ai_context_template": "作品標籤: @作品標籤.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大綱: @故事大綱.content.overview\n世界觀設定: @世界觀設定.content\n組織/勢力設定:@type:組織卡[previous:global].{content.name,content.description,content.influence,content.relationship}"},
        "分卷大綱": {"default_ai_context_template": (
            "總卷數:@核心藍圖.content.volume_count\n"
            "故事大綱:@故事大綱.content.overview\n"
            "作品標籤:@作品標籤.content\n"
            "世界觀設定: @世界觀設定.content.world_view\n"
            "組織/勢力設定:@type:組織卡[previous:global].{content.name,content.description,content.influence,content.relationship}\n"
            "character_card:@type:角色卡[previous]\n"
            "scene_card:@type:場景卡[previous]\n"
            "上一卷信息: @type:分卷大綱[index=$current.volumeNumber-1].content\n"
            "接下來請你創作第 @self.content.volume_number 卷的細綱\n"
        )},
        "寫作指南": {
            "is_singleton": False,
            "default_ai_context_template": (
                "世界觀設定: @世界觀設定.content.world_view\n"
                "組織/勢力設定:@type:組織卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
                "當前分卷主線:@parent.content.main_target\n"
                "當前分卷輔線:@parent.content.branch_line\n"
                "該卷的階段數量及卷末實體狀態快照:@parent.{content.stage_count,content.entity_snapshot}\n"
                "角色卡信息:@type:角色卡[previous]\n"
                "地圖/場景卡信息:@type:場景卡[previous]\n"
                "請爲第 @self.content.volume_number 卷生成一份寫作指南。"
            )
        },
        "階段大綱": {"default_ai_context_template": (
            "世界觀設定: @世界觀設定.content.world_view\n"
            "組織/勢力設定:@type:組織卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
            "分卷主線:@parent.content.main_target\n"
            "分卷輔線:@parent.content.branch_line\n"
            "角色卡信息:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.born_scene,content.description,content.personality,content.core_drive,content.character_arc}\n"
            "地圖/場景卡信息:@type:場景卡[previous]\n"
            "該卷的角色行動簡述:@parent.content.character_action_list\n"
            "之前的階段故事大綱，確保章節範圍、劇情能夠銜接:@type:階段大綱[previous:global:1].{content.stage_name,content.reference_chapter,content.analysis,content.overview,content.entity_snapshot}\n"
            "上一章節大綱概述，確保能夠銜接劇情:@type:章節大綱[previous:global:1].{content.overview}\n"
            "本卷的StageCount總數爲：@parent.content.stage_count\n"
            "注意，請務必在@parent.content.stage_count 個階段內將故事按分卷主線收束，並達到卷末實體快照狀態:@parent.content.entity_snapshot\n"
            "該卷的寫作注意事項:@type:寫作指南[sibling].content.content \n"
            "接下來請你創作第 @self.content.stage_number 階段的故事細綱。"
        ), "default_ai_context_template_review": stage_review_context_template},
        "章節大綱": {"default_ai_context_template": (
            "word_view: @世界觀設定.content\n"
            "volume_number: @self.content.volume_number\n"
            "volume_main_target: @type:分卷大綱[index=$current.volumeNumber].content.main_target\n"
            "volume_branch_line: @type:分卷大綱[index=$current.volumeNumber].content.branch_line\n"
            "本卷的實體action列表: @parent.content.entity_action_list\n"
            "當前階段故事概述: @stage:current.overview\n"
            "當前階段覆蓋章節範圍: @stage:current.reference_chapter\n"
            "之前的章節大綱: @type:章節大綱[sibling].{content.chapter_number,content.overview}\n"
            "請開始創作第 @self.content.chapter_number 章的大綱，保證連貫性"
        )},
        "章節正文": {"editor_component": "CodeMirrorEditor", "is_ai_enabled": False, "default_ai_context_template": (
            "世界觀設定: @世界觀設定.content\n"
            "組織/勢力設定:@type:組織卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.influence,content.relationship,content.dynamic_state}\n"
            "場景卡:@type:場景卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.dynamic_state}\n"
            "當前故事階段大綱: @parent.content.overview\n"
            "角色卡:@type:角色卡[index=filter:content.name in $self.content.entity_list].{content.name,content.role_type,content.born_scene,content.description,content.personality,content.core_drive,content.character_arc,content.dynamic_info}\n"
            "物品卡:@type:物品卡[index=filter:content.name in $self.content.entity_list].{content.name,content.category,content.description,content.current_state,content.power_or_effect}\n"
            "概念卡:@type:概念卡[index=filter:content.name in $self.content.entity_list].{content.name,content.category,content.description,content.rule_definition,content.mastery_hint}\n"
            "最近的章節原文，確保能夠銜接劇情:@type:章節正文[previous:1].{content.title,content.chapter_number,content.content}\n"
            "參與者實體列表，確保生成內容只會出場這些實體:@self.content.entity_list\n"
            "請根據 @self.content.chapter_number： @self.content.title 的大綱@type:章節大綱[index=filter:content.volume_number = $self.content.volume_number&&content.stage_number= $self.content.stage_number&&content.chapter_number= $self.content.chapter_number].{content.overview} 來創作章節正文內容，可以適當發散、設計與大綱內容不衝突的劇情來進行擴充。你無需在正文中重複標題：@self.content.title \n"
            "注意，寫作時必須保證結尾劇情與下一章的劇情大綱不會衝突，且不會提前涉及下一章劇情(如果存在的話):@type:章節大綱[index=filter:content.volume_number = $self.content.volume_number && content.chapter_number = $self.content.chapter_number+1].{content.title,content.overview}\n"
            "寫作時請結合寫作指南要求:@type:寫作指南[index=filter:content.volume_number = $self.content.volume_number].{content.content}\n"
            ), "default_ai_context_template_review": chapter_review_context_template},
        "內容審核卡片": {
            "editor_component": "ReviewResultCardEditor",
            "is_ai_enabled": False,
            "default_ai_context_template": None,
            "default_ai_context_template_review": None,
        },
        "角色卡": {"default_ai_context_template": None},
        "場景卡": {"default_ai_context_template": None},
        "組織卡": {"default_ai_context_template": None},
        "物品卡": {"default_ai_context_template": None, "is_ai_enabled": False},
        "概念卡": {"default_ai_context_template": None, "is_ai_enabled": False},
        "文件夾": {"is_singleton": False, "is_ai_enabled": False, "default_ai_context_template": None},
    }

    # 類型默認 AI 參數預設（不包含 llm_config_id）
    DEFAULT_AI_PARAMS = {
        "金手指": {"prompt_name": "金手指生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "一句話梗概": {"prompt_name": "一句話梗概", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "故事大綱": {"prompt_name": "一段話大綱", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "世界觀設定": {"prompt_name": "世界觀設定", "temperature": 0.7, "max_tokens": 4096, "timeout": 150},
        "核心藍圖": {"prompt_name": "核心藍圖", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "分卷大綱": {"prompt_name": "分卷大綱", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "寫作指南": {"prompt_name": "寫作指南", "temperature": 0.6, "max_tokens": 8192, "timeout": 120},
        "階段大綱": {"prompt_name": "階段大綱", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "章節大綱": {"prompt_name": "章節大綱", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "章節正文": {"prompt_name": "內容生成", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "內容審核卡片": None,
        "角色卡": {"prompt_name": "角色動態信息提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "場景卡": {"prompt_name": "內容生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "組織卡": {"prompt_name": "關係提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "物品卡": None,
        "概念卡": None,
    }

    # 類型名稱到內置響應模型的映射（直接用於生成 json_schema）
    TYPE_TO_MODEL_KEY = {
        "通用文本" : "Text",
        "作品標籤": "Tags",
        "金手指": "SpecialAbilityResponse",
        "一句話梗概": "OneSentence",
        "故事大綱": "ParagraphOverview",
        "世界觀設定": "WorldBuilding",
        "核心藍圖": "Blueprint",
        "分卷大綱": "VolumeOutline",
        "寫作指南": "WritingGuide",
        "階段大綱": "StageLine",
        "章節大綱": "ChapterOutline",
        "章節正文": "Chapter",
        "內容審核卡片": "ReviewResultCardContent",
        "角色卡": "CharacterCard",
        "場景卡": "SceneCard",
        "組織卡": "OrganizationCard",
        "物品卡": "ItemCard",
        "概念卡": "ConceptCard",
        "文件夾": "Text",
    }

    overwrite_card_schemas = settings.bootstrap.should_overwrite_card_schemas

    existing_types = session.exec(select(CardType)).all()
    existing_type_names = {ct.name for ct in existing_types}
    existing_type_by_name = {ct.name: ct for ct in existing_types}

    # 默認 llm_config_id：取第一個可用 LLM 配置（若存在）
    default_llm = session.exec(select(LLMConfig)).first()

    for name, details in default_types.items():
        if name not in existing_type_names:
            # 直接在卡片類型上存儲結構（json_schema）
            schema = None
            try:
                model_class = RESPONSE_MODEL_MAP.get(TYPE_TO_MODEL_KEY.get(name))
                if model_class:
                    schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
                    schema = _localize_schema_titles(schema)
            except Exception:
                schema = None
            # AI 參數預設（llm_config_id 由前端選擇，不在此指定）
            ai_params = DEFAULT_AI_PARAMS.get(name)
            if ai_params is not None:
                # 若存在可用的默認 LLM，則寫入其 ID；避免寫 0 導致前端無法識別
                ai_params = {**ai_params, "llm_config_id": (default_llm.id if default_llm else None)}
            card_type = CardType(
                name=name,
                model_name=TYPE_TO_MODEL_KEY.get(name, name),
                description=details.get("description", f"{name}的默認卡片類型"),
                json_schema=schema,
                ai_params=ai_params,
                editor_component=details.get("editor_component"),
                is_ai_enabled=details.get("is_ai_enabled", True),
                is_singleton=details.get("is_singleton", False),
                default_ai_context_template=details.get("default_ai_context_template"),
                default_ai_context_template_review=details.get("default_ai_context_template_review"),
                built_in=True,
            )
            session.add(card_type)
            logger.info(f"Created default card type: {name}")
        else:
            # 增量更新：刷新類型結構與元信息
            ct = existing_type_by_name[name]
            try:
                model_class = RESPONSE_MODEL_MAP.get(TYPE_TO_MODEL_KEY.get(name))
                if model_class:
                    schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
                    schema = _localize_schema_titles(schema)
                    if ct.json_schema is None or overwrite_card_schemas:
                        ct.json_schema = schema
            except Exception:
                pass
            # 若缺失 ai_params 則按預設填充（不覆蓋用戶已設置的）
            if getattr(ct, 'ai_params', None) is None:
                preset = DEFAULT_AI_PARAMS.get(name)
                if preset is not None:
                    ct.ai_params = {**preset, "llm_config_id": (default_llm.id if default_llm else None)}
            # 若缺失 model_name 則按映射補齊
            if not getattr(ct, 'model_name', None):
                ct.model_name = TYPE_TO_MODEL_KEY.get(name, name)
            ct.editor_component = details.get("editor_component")
            ct.is_ai_enabled = details.get("is_ai_enabled", True)
            ct.is_singleton = details.get("is_singleton", False)
            ct.description = details.get("description", f"{name}的默認卡片類型")
            ct.default_ai_context_template = details.get("default_ai_context_template")
            ct.default_ai_context_template_review = details.get("default_ai_context_template_review")
            ct.built_in = True

    session.flush()

    all_cards = session.exec(select(Card)).all()
    for card in all_cards:
        card_type = existing_type_by_name.get(getattr(card.card_type, "name", ""))
        if not card_type and getattr(card, "card_type_id", None):
            card_type = session.get(CardType, card.card_type_id)
        if not card_type:
            continue
        if getattr(card, "ai_context_template", None) is None:
            card.ai_context_template = getattr(card_type, "default_ai_context_template", None)
        if getattr(card, "ai_context_template_review", None) is None:
            card.ai_context_template_review = getattr(card_type, "default_ai_context_template_review", None)

    # 自動同步：將未映射到默認卡片類型的內置響應模型寫入 CardType
    # 目的：避免新增響應模型後，前端“設置-卡片類型”看不到對應模型定義。
    # mapped_model_keys = set(TYPE_TO_MODEL_KEY.values())
    # for model_key, model_class in RESPONSE_MODEL_MAP.items():
    #     # 已由 default_types 顯式管理的模型，不重複創建
    #     if model_key in mapped_model_keys:
    #         continue

    #     existing = next(
    #         (
    #             ct for ct in existing_types
    #             if ct.name == model_key or ct.model_name == model_key
    #         ),
    #         None
    #     )

    #     schema = None
    #     try:
    #         schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
    #     except Exception:
    #         schema = None

    #     if existing:
    #         # 僅對內置類型做增量修復，避免覆蓋用戶自定義類型
    #         if getattr(existing, "built_in", False):
    #             existing.model_name = model_key
    #             if schema is not None:
    #                 existing.json_schema = schema
    #             if not (existing.description or "").strip():
    #                 existing.description = f"{model_key}（內置響應模型）"
    #         continue

    #     auto_type = CardType(
    #         name=model_key,
    #         model_name=model_key,
    #         description=f"{model_key}（內置響應模型）",
    #         json_schema=schema,
    #         ai_params=None,
    #         editor_component=None,
    #         is_ai_enabled=False,
    #         is_singleton=False,
    #         default_ai_context_template=None,
    #         built_in=True,
    #     )
    #     session.add(auto_type)
    #     existing_types.append(auto_type)
    #     existing_type_names.add(model_key)
    #     existing_type_by_name[model_key] = auto_type
    #     logger.info(f"Created builtin response model card type: {model_key}")

    session.commit()
    logger.info(f"Default card types committed. overwrite_card_schemas={overwrite_card_schemas}")
