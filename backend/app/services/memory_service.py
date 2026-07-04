from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from sqlmodel import Session
from sqlalchemy.orm.attributes import flag_modified

from loguru import logger

from app.schemas.relation_extract import RelationExtraction, CN_TO_EN_KIND
from app.schemas.entity import Entity
from app.services.ai.core import llm_service
from pydantic import BaseModel
# 引入動態信息模型
from app.schemas.entity import UpdateDynamicInfo, DynamicInfoType, DynamicInfoItem, DeletionInfo
from app.db.models import Card, CardType
from sqlmodel import select

# 引入帶類型的參與者模型
from app.schemas.memory import ParticipantTyped

# 從數據庫加載提示詞
from app.services import prompt_service
from app.services.memory_extractors.memory_base import log_extract_prompt
from app.services.memory_extractors.registry_factory import get_memory_extractor_registry

# 使用可切換的知識圖譜 Provider
from app.services.kg_provider import get_provider, KnowledgeGraphUnavailableError

# 主賓類型約束（建議表）
_ALLOWED_PAIRS: Dict[str, List[Tuple[str, str]]] = {
    '同盟': [('character','character')],
    '隊友': [('character','character')],
    '同門': [('character','character')],
    '敵對': [('character','character')],
    '親屬': [('character','character')],
    '師徒': [('character','character')],
    '對手': [('character','character')],
    '夥伴': [('character','character')],
    '上級': [('character','character')],
    '下屬': [('character','character')],

    '隸屬': [('character','organization')],
    '成員': [('character','organization')],
    '領導': [('character','organization'), ('organization','organization')],
    '創立': [('character','organization') , ('organization','organization')],

    '擁有': [('character','item'), ('organization','item')],
    '使用': [('character','item'), ('organization','item')],
    '修煉': [('character','concept')],
    '領悟': [('character','concept')],
    '承載': [('item','concept')],
    '映射': [('concept','item')],

    '控制': [('organization','scene')],
    '位於': [('scene','organization')],

    
    '關於': [('character','character'), ('organization','organization'), ('character','organization'), ('organization','character'),
        #    ('item','item'), ('concept','concept'), ('character','concept'), ('character','item')
           ],
    '其他': [('character','character'), ('organization','organization'), ('character','organization'), ('organization','character'), ('item','item'), ('concept','concept'), ('character','concept'), ('character','item')],
    # '影響': [('character','character'), ('organization','organization'), ('character','organization'), ('organization','character'), ('item','item'), ('concept','concept'), ('character','concept'), ('character','item'), ('scene','organization'), ('organization','scene')],
    # '剋制': [('item','item'), ('concept','concept'), ('character','character')],
}

# # 簡化：從卡片類型名稱推斷實體類型
# _CARDTYPE_TO_ENTITYTYPE: Dict[str, str] = {
#     '角色卡': 'character',
#     '場景卡': 'scene',
#     '組織卡': 'organization',
#     # '物品卡': 'item',
#     # '概念卡': 'concept',
# }

def _guess_entity_type(session: Session, project_id: int, name: str) -> Optional[str]:
    try:
        # 在該項目下查找 title == name 的卡片，並讀取其類型名稱
        st = select(Card).where(Card.project_id == project_id, Card.title == name)
        card = session.exec(st).first()
        if not card:
            return None
        ct = card.card_type
        if not ct:
            return None
        
        # 修正：card.content 已經是 dict，應使用 model_validate 而不是 model_validate_json
        entity=Entity.model_validate(card.content)
        return str(entity.entity_type)
        # return _CARDTYPE_TO_ENTITYTYPE.get(ct.name or '', None)
    except Exception as e:
        logger.error(f"Error guessing entity type: {e}")
        return None


# 動態信息每類別數量上限（可根據需要調整）
DYNAMIC_INFO_LIMITS: Dict[str, int] = {
    "系統/模擬器/金手指信息": 3,
    "等級/修爲境界": 3,
    "裝備/法寶": 3,
    "知識/情報": 3,
    "資產/領地": 3,
    "功法/技能": 3,
    "血脈/體質": 3,
    "心理想法/目標快照": 3,
}

class MemoryService:
    def __init__(self, session: Session):
        self.session = session
        self.graph = get_provider()
        self.extractor_registry = get_memory_extractor_registry()

    def list_extractors(self) -> List[Dict[str, Any]]:
        return [
            {
                "code": extractor.code,
                "name": extractor.name,
                "target": extractor.target,
                "preview_supported": extractor.preview_supported,
            }
            for extractor in self.extractor_registry.list_all()
        ]

    async def extract_preview(
        self,
        *,
        extractor_code: str,
        project_id: int | None,
        text: str,
        participants: Optional[List[ParticipantTyped]] = None,
        llm_config_id: int = 1,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        extra_context: Optional[str] = None,
        volume_number: Optional[int] = None,
        chapter_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        extractor = self.extractor_registry.get(extractor_code)
        typed_participants = participants or []
        data = await extractor.extract(
            service=self,
            session=self.session,
            project_id=project_id,
            text=text,
            participants=typed_participants,
            llm_config_id=llm_config_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            extra_context=extra_context,
            context={
                "volume_number": volume_number,
                "chapter_number": chapter_number,
            },
        )
        return {
            "extractor_code": extractor.code,
            "preview_data": data.model_dump(mode="json"),
            "affected_targets": extractor.build_affected_targets(data),
        }

    def apply_preview(
        self,
        *,
        extractor_code: str,
        project_id: int,
        data: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
        volume_number: Optional[int] = None,
        chapter_number: Optional[int] = None,
        participants: Optional[List[ParticipantTyped]] = None,
    ) -> Dict[str, Any]:
        extractor = self.extractor_registry.get(extractor_code)
        preview_data = extractor.output_model.model_validate(data)
        result = extractor.persist(
            service=self,
            session=self.session,
            project_id=project_id,
            data=preview_data,
            options=options,
            context={
                "volume_number": volume_number,
                "chapter_number": chapter_number,
                "participants": participants or [],
            },
        )
        return {
            "success": True,
            "written": int(result.get("written", 0)),
            "updated_card_count": int(result.get("updated_card_count", 0)),
            "updated_relation_count": int(
                result.get("updated_relation_count", result.get("written", 0) if extractor.target == "graph" else 0)
            ),
            "affected_targets": extractor.build_affected_targets(preview_data),
            "raw_result": result,
        }

    async def extract_relations_preview(
        self,
        *,
        text: str,
        participants: Optional[List[ParticipantTyped]] = None,
        llm_config_id: int = 1,
        timeout: Optional[float] = None,
        prompt_name: Optional[str] = "關係提取",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> RelationExtraction:
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        system_prompt = prompt.template

        schema_json = RelationExtraction.model_json_schema()
        system_prompt += f"\n\n請嚴格按以下 JSON Schema 格式輸出:\n{schema_json}"

        participant_names = [p.name for p in participants] if participants else []
        user_prompt = (
            f"參與者: {', '.join(participant_names)}\n\n"
            "請從以下正文中提取:\n"
            f"{text}"
        )
        log_extract_prompt("relation_preview", prompt_name, llm_config_id, system_prompt, user_prompt)
        res = await llm_service.generate_structured(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=RelationExtraction,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if not isinstance(res, RelationExtraction):
            raise ValueError("LLM 關係抽取失敗：輸出格式不符合 RelationExtraction")
        return res

    async def extract_dynamic_info_preview(
        self,
        *,
        text: str,
        participants: Optional[List[ParticipantTyped]] = None,
        llm_config_id: int = 1,
        timeout: Optional[float] = None,
        prompt_name: Optional[str] = "角色動態信息提取",
        project_id: Optional[int] = None,
        extra_context: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> UpdateDynamicInfo:
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示詞: {prompt_name}")
        system_prompt = prompt.template

        schema_json = UpdateDynamicInfo.model_json_schema()
        system_prompt += f"\n\n請嚴格按以下 JSON Schema 格式輸出:\n{schema_json}"

        ref_blocks: List[str] = []
        if extra_context:
            ref_blocks.append(f"【大綱參考信息，不允許從中提取信息】\n{extra_context}")

        character_participants = [p for p in (participants or []) if p.type == 'character']
        if project_id and character_participants:
            try:
                lines: List[str] = []
                for p in character_participants:
                    st = select(Card).where(Card.project_id == project_id, Card.title == p.name)
                    card = self.session.exec(st).first()
                    if not card or not card.card_type or card.card_type.name != '角色卡':
                        continue
                    try:
                        from app.schemas.entity import CharacterCard

                        model = CharacterCard.model_validate(card.content or {})
                        di = model.dynamic_info or {}
                        if not di:
                            continue
                        lines.append(f"- {p.name}:")
                        for cat_enum, items in di.items():
                            if len(items) == 0:
                                continue
                            preview = "; ".join([f"[{it.id}] {it.info}" for it in items[:5]])
                            limit = DYNAMIC_INFO_LIMITS.get(cat_enum, 3)
                            info_line = f"  - {cat_enum} ({len(items)}/{limit}): {preview}"
                            lines.append(info_line)
                    except Exception as e:
                        logger.error(f"Error preparing dynamic info context: {e}")
                        continue
                if lines:
                    ref_blocks.append("【現有角色動態信息（只讀參考）】\n" + "\n".join(lines))
            except Exception as e:
                logger.error(f"Error preparing dynamic info context: {e}")

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""
        participant_text = ""
        if character_participants:
            participant_text = (
                "本章當前參與角色（僅作優先參考，不是硬限制；如果正文裏明確出現了其他重要角色，也可以提取）：\n"
                f"{', '.join([p.name for p in character_participants])}\n\n"
            )
        user_prompt = (
            f"{ref_text}"
            f"章節正文:\n{text}\n\n"
            f"{participant_text}"
            "請從以上正文中提取本章值得寫回角色卡的動態信息。"
        )

        log_extract_prompt("character_dynamic_preview", prompt_name, llm_config_id, system_prompt, user_prompt)
        res = await llm_service.generate_structured(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=UpdateDynamicInfo,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        if not isinstance(res, UpdateDynamicInfo):
            raise ValueError("LLM 動態信息抽取失敗：輸出格式不符合 UpdateDynamicInfo")

        return res

    async def extract_relations_llm(self, text: str, participants: Optional[List[ParticipantTyped]] = None, llm_config_id: int = 1, timeout: Optional[float] = None, prompt_name: Optional[str] = "關係提取") -> RelationExtraction:
        # 優先使用默認提示詞，如果不存在則回退到硬編碼版本
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        system_prompt = prompt.template
        
        # 將輸出模型的 JSON Schema 附加到系統提示詞中
        schema_json = RelationExtraction.model_json_schema()
        system_prompt += f"\n\n請嚴格按照以下 JSON Schema 格式進行輸出:\n{schema_json}"

        participant_names = [p.name for p in participants] if participants else []
        user_prompt = (
            f"參與者: {', '.join(participant_names)}\n\n"
            "請從以下正文中抽取：\n"
            f"{text}"
        )
        log_extract_prompt("relation_extract", prompt_name, llm_config_id, system_prompt, user_prompt)
        res = await llm_service.generate_structured(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=RelationExtraction,
            system_prompt=system_prompt,
            timeout=timeout,
        )
        if not isinstance(res, RelationExtraction):
            raise ValueError("LLM 關係抽取失敗：輸出格式不符合 RelationExtraction")
        return res

    async def extract_dynamic_info_from_text(self, text: str, participants: Optional[List[ParticipantTyped]] = None, llm_config_id: int = 1, timeout: Optional[float] = None, prompt_name: Optional[str] = "角色動態信息提取", project_id: Optional[int] = None, extra_context: Optional[str] = None) -> UpdateDynamicInfo:
        """從文本中抽取角色動態信息。participants 僅作爲優先參考，不作爲硬限制。"""
        prompt = prompt_service.get_prompt_by_name(self.session, prompt_name)
        if not prompt:
            raise ValueError(f"未找到提示詞: {prompt_name}")
        system_prompt = prompt.template

        # 附加 JSON Schema 以強化輸出結構
        schema_json = UpdateDynamicInfo.model_json_schema()
        system_prompt += f"\n\n請嚴格按照以下 JSON Schema 格式進行輸出:\n{schema_json}"

        # 參考上下文（完全由前端決定）+ 現有角色動態信息
        ref_blocks: List[str] = []
        if extra_context:
            ref_blocks.append(f"【大綱參考信息，不允許從中提取信息】\n{extra_context}")

        # 使用帶類型的參與者，僅處理 character 類型
        character_participants = [p for p in (participants or []) if p.type == 'character']
        if project_id and character_participants:
            try:
                lines: List[str] = []
                for p in character_participants:
                    st = select(Card).where(Card.project_id == project_id, Card.title == p.name)
                    card = self.session.exec(st).first()
                    if not card or not card.card_type or card.card_type.name != '角色卡':
                        continue
                    try:
                        from app.schemas.entity import CharacterCard
                     
                        model = CharacterCard.model_validate(card.content or {})
    
                        di = model.dynamic_info or {}
                        if not di:
                            continue
                        lines.append(f"- {p.name}:")
                        for cat_enum, items in di.items():
                            if len(items)==0:
                                continue

                            # 增加數量/上限的上下文（去掉權重）
                            preview = "; ".join([f"[{it.id}] {it.info}" for it in items[:5]])
                            limit = DYNAMIC_INFO_LIMITS.get(cat_enum, 3)
                            info_line = f"  • {cat_enum} ({len(items)}/{limit}): {preview}"
                            lines.append(info_line)
                    except Exception as e:
                        logger.error(f"Error preparing dynamic info context: {e}")
                        continue
                if lines:
                    ref_blocks.append("【現有角色動態信息（只讀參考）】\n" + "\n".join(lines))
            except Exception as e:
                logger.error(f"Error preparing dynamic info context: {e}")

        ref_text = ("\n\n".join(ref_blocks) + "\n\n") if ref_blocks else ""
        participant_text = ""
        if character_participants:
            participant_text = (
                "本章當前參與角色（僅作優先參考，不是硬限制；如果正文裏明確出現了其他重要角色，也可以提取）：\n"
                f"{', '.join([p.name for p in character_participants])}\n\n"
            )

        user_prompt = (
            f"{ref_text}"
            f"章節正文：\n{text}\n\n"
            f"{participant_text}"
            "請從以上正文中提取本章值得寫回角色卡的動態信息。"
        )

        log_extract_prompt("character_dynamic_extract", prompt_name, llm_config_id, system_prompt, user_prompt)
        res = await llm_service.generate_structured(
            session=self.session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=UpdateDynamicInfo,
            system_prompt=system_prompt,
            timeout=timeout,
        )

        if not isinstance(res, UpdateDynamicInfo):
            raise ValueError("LLM 動態信息抽取失敗：輸出格式不符合 UpdateDynamicInfo")
        
        return res

    def query_subgraph(
        self,
        project_id: int,
        participants: Optional[List[str]] = None,
        radius: int = 2,
        edge_type_whitelist: Optional[List[str]] = None,
        top_k: int = 50,
        max_chapter_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.graph.query_subgraph(
            project_id=project_id,
            participants=participants,
            radius=radius,
            edge_type_whitelist=edge_type_whitelist,
            top_k=top_k,
            max_chapter_id=max_chapter_id,
        )

    def ingest_relations_from_llm(self, project_id: int, data: RelationExtraction, *, volume_number: Optional[int] = None, chapter_number: Optional[int] = None, participants_with_type: Optional[List[ParticipantTyped]] = None) -> Dict[str, Any]:
        # 寫入關係三元組；同時最小持久化稱呼/事件摘要/立場（作爲可檢索證據）
        # tuples: (主體, 關係, 客體, 屬性字典)
        triples_with_attrs: List[tuple[str, str, str, Dict[str, Any]]] = []

        DIALOGUES_QUEUE_SIZE = 2
        EVENTS_QUEUE_SIZE = 10

        # 創建參與者類型映射以便快速查找
        participant_type_map = {p.name: p.type for p in participants_with_type} if participants_with_type else {}

        def _merge_queue(existing: List[Any], incoming: List[Any], key_fn=lambda x: x, max_size: int = 3) -> List[Any]:
            seen = set()
            merged: List[Any] = []
            # 先舊後新，保持“新在隊尾”，之後裁剪保留隊尾（最近）
            for it in (existing or []) + (incoming or []):
                k = key_fn(it)
                if k in seen:
                    continue
                seen.add(k)
                merged.append(it)
            if len(merged) <= max_size:
                return merged
            return merged[-max_size:]

        # 按隊列策略合併對話/事件摘要（size=3），並序列化爲字典
        merged_evidence_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        # 預取：將本批所有 (a, b, kind_cn) 收集，做一次子圖查詢後在內存中過濾，避免多次往返
        pairs: List[Tuple[str, str, str]] = []  # (a, b, kind_en)
        for r in (data.relations or []):
            pred = CN_TO_EN_KIND.get(r.kind or '', '')
            if pred:
                pairs.append((r.a, r.b, pred))

        # 構建現存數據索引：key=(a,b,kind_en) -> {recent_dialogues, recent_event_summaries}
        existing_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        try:
            # 參與者全集（去重）
            all_parts = list({p for t in pairs for p in (t[0], t[1])})
            if all_parts:
                sub = self.graph.query_subgraph(project_id=project_id, participants=all_parts, top_k=200)
                from app.schemas.relation_extract import EN_TO_CN_KIND
                for item in (sub.get("relation_summaries") or []):
                    try:
                        a0 = item.get("a"); b0 = item.get("b"); kind_cn = item.get("kind")
                        kind_en = CN_TO_EN_KIND.get(kind_cn or '', '')
                        if not (a0 and b0 and kind_en):
                            continue
                        key = (a0, b0, kind_en)
                        existing_index[key] = {
                            "recent_dialogues": item.get("recent_dialogues") or [],
                            "recent_event_summaries": item.get("recent_event_summaries") or [],
                        }
                    except Exception:
                        continue
        except Exception:
            existing_index = {}

        def _coerce_kind_by_types(kind_cn: str, type_a: Optional[str], type_b: Optional[str]) -> str:
            if not type_a or not type_b:
                return kind_cn
            allowed = _ALLOWED_PAIRS.get(kind_cn)
            if not allowed:
                return kind_cn
            if (type_a, type_b) in allowed:
                return kind_cn
            # 不合法：降級爲“關於”
            return '關於'

        for r in (data.relations or []):
            pred = CN_TO_EN_KIND.get(r.kind or '', '')
            if not pred:
                continue
            
            # 使用傳入的類型信息，如果缺失則回退到猜測
            type_a = participant_type_map.get(r.a) or _guess_entity_type(self.session, project_id, r.a)
            type_b = participant_type_map.get(r.b) or _guess_entity_type(self.session, project_id, r.b)

            # 約束：依據實體類型矯正關係 kind（中文）
            kind_cn_fixed = _coerce_kind_by_types(r.kind, type_a, type_b)
            pred = CN_TO_EN_KIND.get(kind_cn_fixed, pred)
            
            # 準備屬性字典
            attributes = r.model_dump(exclude={"a", "b", "kind"}, exclude_none=True)

            # 後端強制過濾：如果 A 或 B 不是 character，則移除稱呼和對話
            if type_a != 'character' or type_b != 'character':
                attributes.pop('a_to_b_addressing', None)
                attributes.pop('b_to_a_addressing', None)
                attributes.pop('recent_dialogues', None)

            # 對話（過濾長度）
            new_dialogues = [d.strip() for d in (attributes.get("recent_dialogues") or []) if isinstance(d, str) and len(d.strip()) >= 20]
            if new_dialogues:
                attributes["recent_dialogues"] = new_dialogues
            elif "recent_dialogues" in attributes:
                attributes.pop("recent_dialogues")


            # 事件摘要（補全卷章）
            new_summaries: List[Dict[str, Any]] = []
            old_summaries_by_summary: Dict[str, Dict[str, Any]] = {}
            key = (r.a, r.b, pred)
            prev = existing_index.get(key, {})
            old_summaries: List[Dict[str, Any]] = list(prev.get("recent_event_summaries") or [])
            for old_item in old_summaries:
                summary_key = str(old_item.get("summary") or "").strip()
                if summary_key and summary_key not in old_summaries_by_summary:
                    old_summaries_by_summary[summary_key] = old_item

            for s in (r.recent_event_summaries or []):
                try:
                    item = s.model_dump()
                    summary_text = str(item.get("summary") or "").strip()
                    if not summary_text:
                        continue

                    matched_old = old_summaries_by_summary.get(summary_text)
                    if matched_old:
                        if item.get("volume_number") is None and matched_old.get("volume_number") is not None:
                            item["volume_number"] = matched_old.get("volume_number")
                        if item.get("chapter_number") is None and matched_old.get("chapter_number") is not None:
                            item["chapter_number"] = matched_old.get("chapter_number")

                    if volume_number is not None and item.get("volume_number") is None:
                        item["volume_number"] = int(volume_number)
                    if chapter_number is not None and item.get("chapter_number") is None:
                        item["chapter_number"] = int(chapter_number)

                    if summary_text:
                        new_summaries.append(item)
                except Exception:
                    continue

            # 讀取現存並合併爲隊列
            old_dialogues: List[str] = list(prev.get("recent_dialogues") or [])

            merged_dialogues = _merge_queue(old_dialogues, new_dialogues, key_fn=lambda x: x, max_size=DIALOGUES_QUEUE_SIZE)
            merged_summaries = _merge_queue(
                old_summaries,
                new_summaries,
                key_fn=lambda x: (
                    str((x or {}).get("summary") or "").strip(),
                    (x or {}).get("volume_number"),
                    (x or {}).get("chapter_number"),
                ),
                max_size=EVENTS_QUEUE_SIZE,
            )

            if merged_dialogues:
                attributes["recent_dialogues"] = merged_dialogues
            if merged_summaries:
                attributes["recent_event_summaries"] = merged_summaries

            # 清理空字段
            if not attributes.get("recent_dialogues") and "recent_dialogues" in attributes:
                attributes.pop("recent_dialogues", None)
            if not attributes.get("recent_event_summaries") and "recent_event_summaries" in attributes:
                attributes.pop("recent_event_summaries", None)
            
            triples_with_attrs.append((r.a, pred, r.b, attributes))
            
            # 返回值（僅摘要）
            merged_evidence_map[key] = {
                "recent_dialogues": attributes.get("recent_dialogues", []),
                "recent_event_summaries": [s.get('summary') for s in attributes.get("recent_event_summaries", [])]
            }

        if triples_with_attrs:
            try:
                self.graph.ingest_triples_with_attributes(project_id, triples_with_attrs)
            except Exception as e:
                raise ValueError(f"知識圖譜寫入失敗: {e}")
        
        return {"written": len(triples_with_attrs), "merged_evidence": merged_evidence_map} 

    def update_dynamic_character_info(self, project_id: int, data: UpdateDynamicInfo, queue_size: int = 3) -> Dict[str, Any]:
        """
        更新角色卡的動態信息，支持新增、刪除。
        每個類別的最大數量使用 DYNAMIC_INFO_LIMITS 中的配置；若未配置，則回退到 queue_size（默認3）。
        """
        from app.schemas.entity import CharacterCard

        # 1. 先處理刪除
        if data.delete_info_list:
            for del_item in data.delete_info_list:
                # 心理想法/目標快照：忽略來自 LLM 的刪除指令，交由系統按 FIFO 處理
                if str(del_item.dynamic_type) == '心理想法/目標快照':
                    continue
                st = select(Card).where(Card.project_id == project_id, Card.title == del_item.name)
                card = self.session.exec(st).first()
                if not card or card.card_type.name != '角色卡':
                    continue
                
                try:
                    model = CharacterCard.model_validate(card.content or {})
                    if model.dynamic_info and del_item.dynamic_type in model.dynamic_info:
                        model.dynamic_info[del_item.dynamic_type] = [
                            item for item in model.dynamic_info[del_item.dynamic_type] if item.id != del_item.id
                        ]
                        card.content = model.model_dump(exclude_unset=True)
                        flag_modified(card, "content")
                        self.session.add(card)
                except Exception as e:
                    logger.warning(f"Failed to process deletion for {del_item.name}: {e}")
            self.session.commit()

        # 2. 再處理新增與修改
        updated_cards: Dict[str, Card] = {}
        # 預加載所有相關的角色卡
        all_names = list(set([i.name for i in data.info_list]))
        if not all_names:
            return {"success": False, "updated_card_count": 0}

        stmt = select(Card).where(Card.project_id == project_id, Card.title.in_(all_names))
        cards = self.session.exec(stmt).all()
        card_map = {c.title: c for c in cards if c.card_type and c.card_type.name == '角色卡'}


        # 處理新增
        # (和之前類似，但要確保在已更新的 card 對象上操作)
        for info_group in data.info_list:
            card = updated_cards.get(info_group.name) or card_map.get(info_group.name)
            if not card:
                continue

            try:
                model = CharacterCard.model_validate(card.content or {})
                if not model.dynamic_info:
                    model.dynamic_info = {}

                for cat, items in info_group.dynamic_info.items():
                    if not items:
                        continue
                    
                    if cat not in model.dynamic_info:
                        model.dynamic_info[cat] = []
                    
                    existing_items = model.dynamic_info[cat]
                    
                    # 合併（新項追加在隊尾，便於 FIFO）
                    for new_item in items:
                        # 將佔位或缺失ID暫記爲 0，稍後統一分配正數ID
                        if not isinstance(new_item.id, int) or new_item.id <= 0:
                            new_item.id = 0
                        existing_items.append(new_item)
                    
                    # 統一ID規範化：爲所有 <=0 的條目分配連續正數ID（不改變已有正數ID）
                    existing_positive = [it.id for it in existing_items if isinstance(it.id, int) and it.id > 0]
                    next_id = (max(existing_positive) + 1) if existing_positive else 1
                    for it in existing_items:
                        if not isinstance(it.id, int) or it.id <= 0:
                            it.id = next_id
                            next_id += 1
                    
                    # 按配置上限裁剪
                    limit = DYNAMIC_INFO_LIMITS.get(cat, queue_size)
                    if str(cat) == '心理想法/目標快照':
                        # 保留最新 limit 條（先進先出，淘汰最舊）
                        model.dynamic_info[cat] = existing_items[-limit:]
                    else:
                        # 其他類別沿用當前策略（若需改爲保留最新，可改爲 existing_items[-limit:]）
                        model.dynamic_info[cat] = existing_items[:limit]

                card.content = model.model_dump(exclude_unset=True)
                flag_modified(card, "content")
                updated_cards[card.title] = card
            except Exception as e:
                logger.warning(f"Failed to process addition for {info_group.name}: {e}")

        # 統一提交
        for card in updated_cards.values():
            self.session.add(card)
        
        if updated_cards:
            self.session.commit()
            for card in updated_cards.values():
                self.session.refresh(card)

        return {"success": True, "updated_card_count": len(updated_cards)} 
