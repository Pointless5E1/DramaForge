from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Card, CardType, Project
from app.schemas.card import CardCreate, CardUpdate, CardTypeCreate, CardTypeUpdate
from app.exceptions import BusinessException
import logging
import hashlib
# 引入動態信息模型
from app.schemas.entity import UpdateDynamicInfo, CharacterCard, DynamicInfoItem
from sqlalchemy import update as sa_update

logger = logging.getLogger(__name__)


def _compute_legacy_snapshot_hash(input_text: str) -> str:
    hash_value = 5381
    for char in input_text or "":
        hash_value = ((hash_value << 5) + hash_value) ^ ord(char)
    return f"h{(hash_value & 0xFFFFFFFF):x}"


def _resolve_context_template_slots(source: object, fallback: object | None = None, is_free_project: bool = False) -> dict[str, Optional[str]]:
    if is_free_project:
        return {
            "ai_context_template": None,
            "ai_context_template_review": None,
        }

    generation_template = getattr(source, "ai_context_template", None)
    review_template = getattr(source, "ai_context_template_review", None)

    if fallback is not None:
        if not generation_template:
            generation_template = getattr(fallback, "default_ai_context_template", None)
        if not review_template:
            review_template = getattr(fallback, "default_ai_context_template_review", None)

    return {
        "ai_context_template": generation_template,
        "ai_context_template_review": review_template,
    }

# 每類動態信息的建議上限（超過則保留更重要/較新者）。可按需調整。
MAX_ITEMS_BY_TYPE: dict[str, int] = {
    "心理想法/目標快照": 3,
    "等級/修爲境界": 4,
    "功法/技能": 6,
    "裝備/法寶": 4,
    "知識/情報": 4,
    "資產/領地": 4,
    "血脈/體質": 4,
    # DynamicInfoType.CONNECTION: 5,
}

# 全局權重閾值（默認 0.45）
WEIGHT_THRESHOLD =0.45

# ---- ：子樹工具 ----

def _fetch_children(db: Session, parent_ids: List[int]) -> List[Card]:
    if not parent_ids:
        return []
    stmt = select(Card).where(Card.parent_id.in_(parent_ids))
    return db.exec(stmt).all()


def _collect_subtree(db: Session, root: Card) -> List[Card]:
    """按廣度優先收集包含 root 在內的整棵子樹（返回順序：父在前、子在後）。"""
    result: List[Card] = []
    queue: List[Card] = [root]
    while queue:
        node = queue.pop(0)
        result.append(node)
        children = _fetch_children(db, [node.id])
        queue.extend(children)
    return result


def _next_display_order(db: Session, project_id: int, parent_id: Optional[int]) -> int:
    stmt = select(Card).where(Card.project_id == project_id, Card.parent_id == parent_id)
    siblings = db.exec(stmt).all()
    return len(siblings)


def _shallow_clone(src: Card, project_id: int, parent_id: Optional[int], display_order: int) -> Card:
    return Card(
        title=src.title,
        model_name=src.model_name,
        content=dict(src.content or {}),
        parent_id=parent_id,
        card_type_id=src.card_type_id,
        json_schema=dict(src.json_schema or {}) if src.json_schema is not None else None,
        ai_params=dict(src.ai_params or {}) if src.ai_params is not None else None,
        project_id=project_id,
        display_order=display_order,
        ai_context_template=src.ai_context_template,
        ai_context_template_review=src.ai_context_template_review,
    )

# ---- 標題後綴生成 ----

def _generate_non_conflicting_title(db: Session, project_id: int, base_title: str, card_type_id: Optional[int] = None) -> str:
    """生成不衝突的標題
    
    Args:
        db: 數據庫會話
        project_id: 項目ID
        base_title: 基礎標題
        card_type_id: 卡片類型ID（如果提供，只檢查同類型卡片的標題衝突）
    """
    title = (base_title or '').strip() or '新卡片'
    
    # 構建查詢：同項目內的標題
    stmt = select(Card.title).where(Card.project_id == project_id)
    
    # 如果指定了卡片類型，只檢查同類型的標題衝突
    if card_type_id is not None:
        stmt = stmt.where(Card.card_type_id == card_type_id)
    
    titles = db.exec(stmt).all() or []
    existing_titles = set(titles)
    
    if title not in existing_titles:
        return title
    
    # 找最大後綴
    import re
    pattern = re.compile(rf"^{re.escape(title)}\((\d+)\)$")
    max_n = 0
    for t in existing_titles:
        m = pattern.match(str(t))
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except Exception:
                continue
    return f"{title}({max_n + 1})"


class CardService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_for_project(self, project_id: int) -> List[Card]:
        # 獲取該項目所有卡片，樹形結構將在客戶端構建。
        statement = (
            select(Card)
            .where(Card.project_id == project_id)
            .order_by(Card.display_order)
        )
        cards = self.db.exec(statement).all()
        return cards

    def search(self, project_id: int, query: str) -> List[Card]:
        """Search cards in a project by title or content."""
        import sqlalchemy as sa
        statement = select(Card).where(
            Card.project_id == project_id,
            sa.or_(
                Card.title.contains(query),
                sa.cast(Card.content, sa.String).contains(query)
            )
        )
        return self.db.exec(statement).all()

    def get_by_id(self, card_id: int) -> Optional[Card]:
        return self.db.get(Card, card_id)

    def create(self, card_create: CardCreate, project_id: int) -> Card:

        card_type = self.db.get(CardType, card_create.card_type_id)
        if not card_type:
             raise BusinessException(f"CardType with id {card_create.card_type_id} not found", status_code=404)

        # 單例限制：在保留項目(__free__)中放行
        proj = self.db.get(Project, project_id)
        is_free_project = getattr(proj, 'name', None) == "__free__"
        if card_type.is_singleton and not is_free_project:
            statement = select(Card).where(Card.project_id == project_id, Card.card_type_id == card_create.card_type_id)
            existing_card = self.db.exec(statement).first()
            if existing_card:
                raise BusinessException(
                    f"A card of type '{card_type.name}' already exists in this project, and it is a singleton.",
                    status_code=409
                )

        # 決定顯示順序
        statement = select(Card).where(Card.project_id == project_id, Card.parent_id == card_create.parent_id)
        sibling_cards = self.db.exec(statement).all()
        display_order = len(sibling_cards)

        context_template_slots = _resolve_context_template_slots(card_create, card_type, is_free_project=is_free_project)

        # 自動處理標題衝突：相同類型的卡片標題追加 (n)
        final_title = _generate_non_conflicting_title(
            self.db, 
            project_id, 
            getattr(card_create, 'title', '') or card_type.name,
            card_type_id=card_create.card_type_id  # 只檢查同類型卡片
        )

        # 合併參數：context_template_slots 會覆蓋 card_create 中的同名字段
        card_params = {
            **card_create.model_dump(),
            'title': final_title,
            'project_id': project_id,
            'display_order': display_order,
            **context_template_slots,
        }
        
        card = Card(**card_params)
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    @staticmethod
    def create_initial_cards_for_project(db: Session, project_id: int, template_items: Optional[List[dict]] = None):
        """
        # 爲新項目創建初始卡片集合。
        # 如果提供了 template_items，則使用它們；否則回退到內置的默認列表（兼容舊版）。
        # template_items: List[ { card_type_id: int, display_order: int, title_override?: str } ]
        """
        if template_items is None:
            initial_cards_setup = {
                "作品標籤": {"order": 0},
                "金手指": {"order": 1},
                "一句話梗概": {"order": 2},
                "故事大綱": {"order": 3},
                "世界觀設定": {"order": 4},
                "核心藍圖": {"order": 5},
            }

            for card_type_name, setup in initial_cards_setup.items():
                try:
                    statement = select(CardType).where(CardType.name == card_type_name)
                    card_type = db.exec(statement).first()
                    if card_type:
                        # 創建卡片
                        new_card = Card(
                            title=card_type_name,
                            content={},
                            project_id=project_id,
                        card_type_id=card_type.id,
                            display_order=setup["order"],
                            ai_context_template=card_type.default_ai_context_template,
                            ai_context_template_review=card_type.default_ai_context_template_review,
                        )
                    db.add(new_card)
                    db.commit()
                except Exception as e:
                    logger.error(f"Failed creating initial card for type {card_type_name}: {e}")
            return

        # 使用模板條目創建
        for item in sorted(template_items, key=lambda x: x.get('display_order', 0)):
            try:
                ct = db.get(CardType, item['card_type_id'])
                if not ct:
                    continue
                title = item.get('title_override') or ct.name
                new_card = Card(
                    title=title,
                    content={},
                    project_id=project_id,
                    card_type_id=ct.id,
                    display_order=item.get('display_order', 0),
                    ai_context_template=ct.default_ai_context_template,
                    ai_context_template_review=ct.default_ai_context_template_review,
                )
                db.add(new_card)
                db.commit()
            except Exception as e:
                logger.error(f"Failed creating initial card by template item {item}: {e}")
        return

    def update(self, card_id: int, card_update: CardUpdate) -> Optional[Card]:
        card = self.get_by_id(card_id)
        if not card:
            return None
            
        update_data = card_update.model_dump(exclude_unset=True)

        # 如果parent_id改變了，我們需要更新display_order
        if 'parent_id' in update_data and card.parent_id != update_data['parent_id']:
            # 這個邏輯可能很複雜。現在只是將新的列表追加到末尾。
            statement = select(Card).where(Card.project_id == card.project_id, Card.parent_id == update_data['parent_id'])
            sibling_cards = self.db.exec(statement).all()
            update_data['display_order'] = len(sibling_cards)


        for key, value in update_data.items():
            setattr(card, key, value)
            
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    def delete(self, card_id: int) -> bool:
        # 遞歸刪除由關係中的級聯選項處理
        card = self.get_by_id(card_id)
        if not card:
            return False
        self.db.delete(card)
        self.db.commit()
        return True 

    def replace_field_text(self, card_id: int, field_path: str, old_text: str, new_text: str, fuzzy_match: bool = True) -> Dict[str, Any]:
        """
        替換卡片字段中的指定文本片段
        
        Args:
            card_id: 目標卡片ID
            field_path: 字段路徑（如 "content", "overview" 等）
            old_text: 要被替換的原文片段
            new_text: 新的文本內容
            fuzzy_match: 是否啓用模糊匹配（支持 "開頭...結尾" 格式）
            
        Returns:
            result dict including success, replaced_count, etc.
        """
        import copy
        
        # 1. 獲取卡片
        card = self.get_by_id(card_id)
        if not card:
            return {"success": False, "error": f"卡片 {card_id} 不存在"}
            
        # 2. 標準化路徑 (自動處理 content. 前綴)
        normalized_path = field_path
        if not normalized_path.startswith("content."):
            normalized_path = f"content.{normalized_path}"
            
        # 3. 獲取當前值
        try:
            current_value = card.content or {}
            # 逐層訪問
            parts = normalized_path.split(".")[1:] # 跳過 content
            for part in parts:
                if isinstance(current_value, dict):
                    current_value = current_value.get(part, "")
                else:
                    return {"success": False, "error": f"字段路徑 {normalized_path} 無效: 無法遍歷到 {part}"}
        except Exception as e:
            return {"success": False, "error": f"獲取字段值失敗: {str(e)}"}
            
        if not isinstance(current_value, str):
            return {"success": False, "error": f"字段 {field_path} 不是文本類型"}
            
        # 4. 匹配邏輯
        actual_old_text = old_text
        if fuzzy_match and ("..." in old_text or "……" in old_text):
            separator = "..." if "..." in old_text else "……"
            split_parts = old_text.split(separator, 1)
            if len(split_parts) == 2:
                start_text = split_parts[0].strip()
                end_text = split_parts[1].strip()
                
                # 查找範圍
                start_idx = current_value.find(start_text)
                if start_idx == -1:
                    return {"success": False, "error": "未找到開頭文本", "hint": f"開頭: {start_text[:20]}..."}
                
                end_search_start = start_idx + len(start_text)
                end_idx = current_value.find(end_text, end_search_start)
                if end_idx == -1:
                    return {"success": False, "error": "未找到結尾文本", "hint": f"結尾: ...{end_text[-20:]}"}
                
                actual_old_text = current_value[start_idx:end_idx + len(end_text)]
            else:
                 return {"success": False, "error": "模糊匹配格式錯誤"}
        
        if actual_old_text not in current_value:
             return {"success": False, "error": "未找到指定的原文片段"}
             
        # 5. 執行替換
        replaced_count = current_value.count(actual_old_text)
        updated_value = current_value.replace(actual_old_text, new_text)
        
        # 6. 更新並保存
        new_content = copy.deepcopy(card.content or {})
        target = new_content
        # 導航到父級
        parts = normalized_path.split(".")[1:]
        for part in parts[:-1]:
            if part not in target:
                 target[part] = {}
            target = target[part]
        
        target[parts[-1]] = updated_value
        
        card.content = new_content
        flag_modified(card, "content")
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        
        return {
            "success": True,
            "card_id": card.id,
            "card_title": card.title,
            "replaced_count": replaced_count,
            "old_length": len(current_value),
            "new_length": len(updated_value)
        }

    # ---- 移動與複製 ----
    def replace_field_text_by_lines(
        self,
        card_id: int,
        field_path: str,
        start_line: int,
        end_line: int,
        new_text: str,
        expected_excerpt: Optional[str] = None,
        snapshot_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        按行號替換文本字段片段（位置型替換）。
        """
        import copy

        card = self.get_by_id(card_id)
        if not card:
            return {"success": False, "error": f"卡片 {card_id} 不存在"}

        normalized_path = field_path
        if not normalized_path.startswith("content."):
            normalized_path = f"content.{normalized_path}"

        try:
            current_value = card.content or {}
            parts = normalized_path.split(".")[1:]
            for part in parts:
                if isinstance(current_value, dict):
                    current_value = current_value.get(part, "")
                else:
                    return {"success": False, "error": f"字段路徑 {normalized_path} 無效: 無法遍歷到 {part}"}
        except Exception as e:
            return {"success": False, "error": f"獲取字段值失敗: {str(e)}"}

        if not isinstance(current_value, str):
            return {"success": False, "error": f"字段 {field_path} 不是文本類型"}

        if start_line < 1 or end_line < start_line:
            return {"success": False, "error": "行號範圍無效"}

        line_sep = "\r\n" if "\r\n" in current_value else "\n"
        lines = current_value.splitlines()
        if not lines:
            lines = [""]

        total_lines = len(lines)
        if end_line > total_lines:
            return {"success": False, "error": f"行號超出範圍: 當前共 {total_lines} 行"}

        start_index = start_line - 1
        end_index = end_line
        current_excerpt = line_sep.join(lines[start_index:end_index])
        excerpt_hash = hashlib.sha256(current_excerpt.encode("utf-8")).hexdigest()
        full_hash = hashlib.sha256(current_value.encode("utf-8")).hexdigest()
        legacy_excerpt_hash = _compute_legacy_snapshot_hash(current_excerpt)
        legacy_full_hash = _compute_legacy_snapshot_hash(current_value)
        if snapshot_hash and snapshot_hash not in {
            excerpt_hash,
            full_hash,
            legacy_excerpt_hash,
            legacy_full_hash,
        }:
            return {
                "success": False,
                "error": "快照校驗失敗，正文可能已變化",
                "expected_snapshot_hash": snapshot_hash,
                "actual_excerpt_hash": excerpt_hash,
                "actual_full_hash": full_hash,
                "actual_legacy_excerpt_hash": legacy_excerpt_hash,
                "actual_legacy_full_hash": legacy_full_hash,
            }

        if expected_excerpt is not None and expected_excerpt.strip() and expected_excerpt.strip() != current_excerpt.strip():
            return {
                "success": False,
                "error": "原片段校驗失敗，正文可能已變化",
                "expected_excerpt": expected_excerpt,
                "actual_excerpt": current_excerpt,
            }

        new_lines = new_text.splitlines()
        updated_lines = lines[:start_index] + new_lines + lines[end_index:]
        updated_value = line_sep.join(updated_lines)
        if current_value.endswith("\r\n"):
            updated_value = f"{updated_value}\r\n"
        elif current_value.endswith("\n"):
            updated_value = f"{updated_value}\n"

        new_content = copy.deepcopy(card.content or {})
        target = new_content
        path_parts = normalized_path.split(".")[1:]
        for part in path_parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[path_parts[-1]] = updated_value

        card.content = new_content
        flag_modified(card, "content")
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)

        return {
            "success": True,
            "card_id": card.id,
            "card_title": card.title,
            "field_path": field_path,
            "start_line": start_line,
            "end_line": end_line,
            "replaced_line_count": end_line - start_line + 1,
            "new_line_count": len(new_lines),
            "line_delta": len(new_lines) - (end_line - start_line + 1),
            "snapshot_hash": excerpt_hash,
        }

    def move_card(self, card_id: int, target_project_id: int, parent_id: Optional[int] = None) -> Optional[Card]:
        root = self.get_by_id(card_id)
        if not root:
            return None
        # 收集子樹
        subtree = _collect_subtree(self.db, root)
        id_set = {c.id for c in subtree}
        # 校驗：若指定 parent_id，不能把父節點設爲子樹內部其它節點（避免環）
        if parent_id and parent_id in id_set and parent_id != root.id:
            raise BusinessException("Cannot set parent to a descendant of itself", status_code=400)
        # 目標父節點項目校驗
        if parent_id is not None:
            parent_card = self.get_by_id(parent_id)
            if not parent_card:
                raise BusinessException("Target parent card not found", status_code=404)
            if parent_card.project_id != target_project_id:
                raise BusinessException("Target parent card not in target project", status_code=400)
        # 非保留項目的單例限制（跨項目移動時校驗）
        if target_project_id != root.project_id:
            target_proj = self.db.get(Project, target_project_id)
            is_target_free = getattr(target_proj, 'name', None) == "__free__"
            if root.card_type and getattr(root.card_type, 'is_singleton', False) and not is_target_free:
                exists_stmt = select(Card).where(Card.project_id == target_project_id, Card.card_type_id == root.card_type_id)
                exists = self.db.exec(exists_stmt).first()
                if exists:
                    raise BusinessException(f"A card of type '{root.card_type.name}' already exists in target project (singleton)", status_code=409)
        # 更新項目ID（整棵子樹）
        for node in subtree:
            node.project_id = target_project_id
        # 調整根的父與顯示順序
        root.parent_id = parent_id
        # 單例限制：在保留項目(__free__)內的同類型允許多個，因此 display_order 也允許直接追加
        root.display_order = _next_display_order(self.db, target_project_id, parent_id)
        # 提交
        for node in subtree:
            self.db.add(node)
        self.db.commit()
        self.db.refresh(root)
        return root

    def copy_card(self, card_id: int, target_project_id: int, parent_id: Optional[int] = None) -> Optional[Card]:
        src_root = self.get_by_id(card_id)
        if not src_root:
            return None
        # 非保留項目的單例限制（複製到目標時校驗根類型）
        target_proj = self.db.get(Project, target_project_id)
        is_target_free = getattr(target_proj, 'name', None) == "__free__"
        if src_root.card_type and getattr(src_root.card_type, 'is_singleton', False) and not is_target_free:
            exists_stmt = select(Card).where(Card.project_id == target_project_id, Card.card_type_id == src_root.card_type_id)
            exists = self.db.exec(exists_stmt).first()
            if exists:
                raise BusinessException(f"A card of type '{src_root.card_type.name}' already exists in target project (singleton)", status_code=409)
        # 收集子樹，按父在前的順序複製
        subtree = _collect_subtree(self.db, src_root)
        old_to_new_id: dict[int, int] = {}
        new_nodes_by_old_id: dict[int, Card] = {}
        for node in subtree:
            # 計算新父ID
            if node.id == src_root.id:
                new_parent_id = parent_id
                new_order = _next_display_order(self.db, target_project_id, new_parent_id)
            else:
                old_parent_id = node.parent_id
                new_parent_id = old_to_new_id.get(old_parent_id) if old_parent_id is not None else None
                new_order = _next_display_order(self.db, target_project_id, new_parent_id)
            clone = _shallow_clone(node, target_project_id, new_parent_id, new_order)
            # 複製時也避免標題衝突
            clone.title = _generate_non_conflicting_title(self.db, target_project_id, clone.title)
            self.db.add(clone)
            self.db.commit()
            self.db.refresh(clone)
            old_to_new_id[node.id] = clone.id
            new_nodes_by_old_id[node.id] = clone
        return new_nodes_by_old_id.get(src_root.id)


class CardTypeService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[CardType]:
        return self.db.exec(select(CardType)).all()

    def get_by_id(self, card_type_id: int) -> Optional[CardType]:
        return self.db.get(CardType, card_type_id)
        
    def create(self, card_type_create: CardTypeCreate) -> CardType:
        card_type = CardType.model_validate(card_type_create)
        self.db.add(card_type)
        self.db.commit()
        self.db.refresh(card_type)
        return card_type

    def update(self, card_type_id: int, card_type_update: CardTypeUpdate) -> Optional[CardType]:
        card_type = self.get_by_id(card_type_id)
        if not card_type:
            return None
        for key, value in card_type_update.model_dump(exclude_unset=True).items():
            setattr(card_type, key, value)
        self.db.add(card_type)
        self.db.commit()
        self.db.refresh(card_type)
        return card_type

    def delete(self, card_type_id: int) -> bool:
        card_type = self.get_by_id(card_type_id)
        if not card_type:
            return False
        # Consider cascading deletes or checks for associated cards
        self.db.delete(card_type)
        self.db.commit()
        return True 
