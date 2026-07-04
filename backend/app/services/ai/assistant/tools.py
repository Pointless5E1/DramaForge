"""
靈感助手工具函數集合（LangChain 原生工具實現）。
"""
import json
import uuid
from typing import Dict, Any, List, Optional
from contextvars import ContextVar

from loguru import logger
from langchain_core.tools import tool
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from app.services.card_service import CardService
from app.db.models import Card, CardType
from app.services.ai.generation.instruction_validator import InstructionExecutor
from app.services.ai.card_type_schema import get_card_type_schema_payload
from app.schemas.tool_result import (
    ToolResult,
    ToolResultStatus,
    ConfirmationRequest,
    CardOperationResult,
    to_dict
)
import copy

REVIEW_RESULT_CARD_TYPE_NAME = "內容審核卡片"


class AssistantDeps:
    """靈感助手的依賴（用於傳遞 session 和 project_id）。"""

    def __init__(self, session, project_id: int):
        self.session = session
        self.project_id = project_id


# 使用 ContextVar 在每個請求上下文中注入依賴，避免爲每個工具再包一層。
_assistant_deps_var: ContextVar[AssistantDeps | None] = ContextVar(
    "assistant_deps", default=None
)


def set_assistant_deps(deps: AssistantDeps) -> None:
    """爲當前請求上下文設置助手依賴，在調用工具前必須先設置。"""

    _assistant_deps_var.set(deps)


def _get_deps() -> AssistantDeps:
    """獲取當前請求上下文中的助手依賴。"""

    deps = _assistant_deps_var.get()
    if deps is None:
        raise RuntimeError(
            "AssistantDeps 未設置，請在調用助手工具前先調用 set_assistant_deps(...)。"
        )
    return deps


def _get_card_type_schema(session, card_type_name: str) -> Dict[str, Any]:
    """獲取卡片類型的 JSON Schema"""
    result = get_card_type_schema_payload(
        session,
        card_type_name,
        allow_model_name=False,
        require_schema=True,
    )
    if not result.get("success"):
        error = result.get("error")
        if error == "not_found":
            raise ValueError(f"卡片類型 '{card_type_name}' 不存在")
        if error == "schema_not_defined":
            raise ValueError(f"卡片類型 '{card_type_name}' 沒有定義 Schema")
        raise ValueError("獲取卡片類型 Schema 失敗")
    return result.get("schema") or {}


def _create_empty_card(session, card_type_name: str, title: str, parent_card_id: Optional[int], project_id: int) -> Card:
    """創建空卡片"""
    card_type = session.query(CardType).filter_by(name=card_type_name).first()
    if not card_type:
        raise ValueError(f"卡片類型 '{card_type_name}' 不存在")
    
    card = Card(
        card_type_id=card_type.id,
        project_id=project_id,
        title=title,
        parent_id=parent_card_id,
        content={}
    )
    session.add(card)
    session.flush()  # 獲取 card.id
    
    return card


def _get_card_by_id(session, card_id: int, project_id: int) -> Optional[Card]:
    """根據ID獲取卡片"""
    card = session.get(Card, card_id)
    if card and card.project_id == project_id:
        return card
    return None


@tool
def search_cards(
    card_type: Optional[str] = None,
    title_keyword: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    搜索項目中的卡片
    
    Args:
        card_type: 卡片類型名稱（可選）
        title_keyword: 標題關鍵詞（可選）
        limit: 返回結果數量上限
    
    Returns:
        success: True 表示成功，False 表示失敗
        error: 錯誤信息
        cards: 卡片列表
        count: 卡片數量
    """

    deps = _get_deps()

    logger.info(f" [Assistant.search_cards] card_type={card_type}, keyword={title_keyword}")

    query = deps.session.query(Card).filter(Card.project_id == deps.project_id)
    
    if card_type:
        query = query.join(CardType).filter(CardType.name == card_type)
    
    if title_keyword:
        query = query.filter(Card.title.ilike(f'%{title_keyword}%'))
    
    cards = query.limit(limit).all()
    
    result = {
        "success": True,
        "cards": [
            {
                "id": c.id,
                "title": c.title,
                "type": c.card_type.name if c.card_type else "Unknown"
            }
            for c in cards
        ],
        "count": len(cards)
    }
    
    logger.info(f"✅ [Assistant.search_cards] 找到 {len(cards)} 個卡片")
    return result


@tool
def create_card(
    card_type: str,
    title: str,
    instructions: List[Dict[str, Any]],
    parent_card_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    創建**新**卡片並填充內容。
    
    ⚠️ **核心規則**：
    - ✅ **創建新卡片**：僅當用戶明確要求新建時使用。
    - ❌ **修改/完善**：若需修改現有卡片或補充內容，必須使用 `update_card`。
    - ✅ **顯式賦值**：即使字段有默認值，也必須顯式生成指令進行賦值，以確認 AI 的意圖。
    
    **策略建議（分步創建）**：
    - **複雜卡片**：推薦先僅填充核心字段（如 name）創建框架，獲取 ID 後再通過 `update_card` 分批補充剩餘內容。這能降低錯誤率並允許中途調整。
    - **簡單卡片**：可一次性創建。
    
    Args:
        card_type: 卡片類型（如：角色卡、世界觀設定）
        title: 標題
        instructions: 指令數組，如 `[{"op":"set", "path":"/name", "value":"張三"}]`
        parent_card_id: (可選) 父卡片ID
    
    Returns:
        包含 success, card_id, missing_fields 等信息。
        若 success=False (內容不完整)，請根據 missing_fields 生成補充指令並調用 update_card。
    """
    deps = _get_deps()
    
    logger.info(f"📝 [Assistant.create_card] type={card_type}, title={title}, instructions={len(instructions)}")
    
    try:
        # 1. 獲取Schema
        schema = _get_card_type_schema(deps.session, card_type)
        
        # 2. 創建空卡片
        card = _create_empty_card(
            session=deps.session,
            card_type_name=card_type,
            title=title,
            parent_card_id=parent_card_id,
            project_id=deps.project_id
        )
        
        logger.info(f"  創建空卡片成功, card_id={card.id}")
        
        # 3. 創建指令執行器
        executor = InstructionExecutor(schema=schema, initial_data={})
        
        # 4. 執行指令數組
        result = executor.execute_batch(instructions)
        
        # 5. 保存數據並標記爲 AI 修改
        card.content = result["data"]
        flag_modified(card, "content")
        card.ai_modified = True
        card.needs_confirmation = True
        card.last_modified_by = "ai"
        deps.session.commit()
        
        logger.info(f"  指令執行完成: applied={result['applied']}, failed={result['failed']}")
        logger.info(f"  已標記爲 AI 修改，需要用戶確認")
        
        # 6. 構建返回結果
        if result["success"]:
            logger.info(f"✅ [Assistant.create_card] 創建成功且內容完整")
            return {
                "success": True,
                "card_id": card.id,
                "card_title": title,
                "card_type": card_type,
                "message": f"✅ 卡片《{title}》創建成功，填充了 {result['applied']} 個字段。請在前端檢查內容後點擊保存以觸發工作流。",
                "applied": result['applied'],
                "needs_confirmation": True
            }
        else:
            # 數據不完整
            missing_fields_str = ", ".join(result["missing_fields"])
            logger.warning(f"⚠️ [Assistant.create_card] 卡片已創建但內容不完整: {missing_fields_str}")
            return {
                "success": False,
                "card_id": card.id,
                "card_title": title,
                "card_type": card_type,
                "message": f"⚠️ 卡片已創建但內容不完整，需要補充字段。補充完成後請在前端點擊保存以觸發工作流。",
                "error": f"缺失必填字段：{missing_fields_str}",
                "missing_fields": result["missing_fields"],
                "current_data": result["data"],
                "applied": result["applied"],
                "failed": result["failed"],
                "failed_instructions": result.get("errors", []),
                "needs_confirmation": True
            }
    
    except Exception as e:
        logger.error(f"❌ [Assistant.create_card] 失敗: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"創建失敗: {str(e)}"
        }


def _update_card_impl(
    card_id: int,
    instructions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    更新卡片的內部實現（核心邏輯）
    
    此函數包含實際的更新邏輯，可被多個工具函數複用。
    不要直接暴露給 LLM，而是通過 @tool 裝飾的函數調用。
    """
    deps = _get_deps()
    
    logger.info(f"📝 [_update_card_impl] card_id={card_id}, instructions={len(instructions)}")
    
    try:
        # 1. 獲取卡片
        card = _get_card_by_id(deps.session, card_id, deps.project_id)
        if not card:
            return {
                "success": False,
                "error": f"卡片 ID={card_id} 不存在或不屬於當前項目"
            }
        
        # 2. 獲取Schema
        schema = _get_card_type_schema(deps.session, card.card_type.name)
        
        # 3. 創建執行器（使用現有數據）
        initial_data = copy.deepcopy(card.content) if isinstance(card.content, dict) else {}
        executor = InstructionExecutor(
            schema=schema,
            initial_data=initial_data
        )
        
        # 4. 執行指令
        result = executor.execute_batch(instructions)
        
        # 5. 保存並標記爲 AI 修改
        card.content = result["data"]
        flag_modified(card, "content")
        card.ai_modified = True
        card.needs_confirmation = True
        card.last_modified_by = "ai"
        deps.session.commit()
        
        logger.info(f"  指令執行完成: applied={result['applied']}, failed={result['failed']}")
        logger.info(f"  已標記爲 AI 修改，需要用戶確認")
        
        # 6. 返回結果
        if result["success"]:
            logger.info(f"✅ [_update_card_impl] 更新成功且內容完整")
            return {
                "success": True,
                "card_id": card_id,
                "card_title": card.title,
                "message": f"✅ 卡片《{card.title}》更新成功，修改了 {result['applied']} 個字段。請在前端檢查內容後點擊保存以觸發工作流。",
                "current_data": result["data"],
                "applied": result["applied"],
                "needs_confirmation": True
            }
        else:
            missing_fields_str = ", ".join(result["missing_fields"])
            logger.warning(f"⚠️ [_update_card_impl] 卡片已更新但仍不完整: {missing_fields_str}")
            return {
                "success": True,
                "card_id": card_id,
                "card_title": card.title,
                "message": f"⚠️ 卡片已更新但仍不完整，需要繼續補充字段。補充完成後請在前端點擊保存以觸發工作流。",
                "is_complete": False,
                "completion_status": "incomplete",
                "warning": f"缺失必填字段：{missing_fields_str}",
                "missing_fields": result["missing_fields"],
                "current_data": result["data"],
                "applied": result["applied"],
                "failed": result["failed"],
                "needs_confirmation": True
            }
    
    except Exception as e:
        logger.error(f"❌ [_update_card_impl] 失敗: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"更新失敗: {str(e)}"
        }


@tool
def update_card(
    card_id: int,
    instructions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    更新**現有**卡片內容（執行指令數組）
    
    ⚠️ **重要：何時使用此工具？**
    
    - ✅ **修改現有卡片**：用戶選中/引用了某個卡片，要求修改或完善
    - ✅ **補充內容**：用戶說"完善這個卡片"、"補充內容"、"添加字段"等
    - ✅ **分步創建**：使用 create_card 創建基礎框架後，逐步補充內容
    - ❌ **創建新卡片**：如果是創建全新的卡片，應該使用 create_card
    
    **判斷依據：**
    1. 如果對話上下文中有卡片引用（如 @卡片名稱），使用此工具
    2. 如果用戶說"修改"、"完善"、"補充"、"更新"，使用此工具
    3. 如果是 create_card 返回不完整，繼續補充內容，使用此工具
    
    用於補充或修改已存在卡片的內容。支持批量修改多個字段。
    
    Args:
        card_id: 卡片ID
        instructions: 指令數組，每個指令包含：
            - op: 操作類型（"set" 設置字段，"append" 追加到數組）
            - path: 字段路徑（JSON Pointer 格式，如 "/name"）
            - value: 要設置的值
    
    Returns:
        Dict 包含:
        - success (bool): 是否成功
        - message (str): 結果消息
        - card_id (int): 卡片ID
        - card_title (str): 卡片標題
        - current_data (dict): 更新後的完整數據
        - applied (int): 成功執行的指令數
        - missing_fields (list, 可選): 仍缺失的必填字段路徑列表
        - failed (int, 可選): 失敗的指令數
    
    Examples:
        # 補充缺失字段
        update_card(
            card_id=123,
            instructions=[
                {"op":"set", "path":"/personality", "value":"正直勇敢"},
                {"op":"set", "path":"/background", "value":"武當弟子"},
                {"op":"append", "path":"/skills", "value":"降龍十八掌"}
            ]
        )
    """
    return _update_card_impl(card_id, instructions)


@tool
def modify_card_field(
    card_id: int,
    field_path: str,
    new_value: Any,
) -> Dict[str, Any]:
    """
    快速修改單個字段（便捷工具）
    
    這是 update_card 的簡化版本，用於快速修改單個字段。
    如需同時修改多個字段，請使用 update_card 工具。
    
    Args:
        card_id: 卡片ID
        field_path: 字段路徑，不需要前導斜槓（如 "name" 或 "personality"）
        new_value: 新值（字符串、數字、布爾值等）
    
    Returns:
        Dict 包含:
        - success (bool): 是否成功
        - message (str): 結果消息
        - card_id (int): 卡片ID
        - card_title (str): 卡片標題
    
    Examples:
        # 修改角色名稱
        modify_card_field(card_id=123, field_path="name", new_value="李四")
        
        # 修改角色性格
        modify_card_field(card_id=123, field_path="personality", new_value="正直勇敢")
    """
    # 轉換爲指令格式（添加前導斜槓）
    path = "/" + field_path if not field_path.startswith("/") else field_path
    instruction = {"op": "set", "path": path, "value": new_value}
    
    # 調用內部實現（不是調用 @tool 裝飾的函數）
    return _update_card_impl(card_id=card_id, instructions=[instruction])


@tool
def get_card_type_schema(
    card_type_name: str,
) -> Dict[str, Any]:
    """
    獲取指定卡片類型的 JSON Schema 定義
    
    使用場景：當需要創建卡片但不清楚其結構時調用
    
    Args:
        card_type_name: 卡片類型名稱
    
    Returns:
        success: True 表示成功，False 表示失敗
        error: 錯誤信息
        card_type: 卡片類型名稱
        schema: 卡片類型的 JSON Schema 定義
        description: 卡片類型的描述
    """

    deps = _get_deps()

    logger.info(f" [Assistant.get_card_type_schema] card_type={card_type_name}")

    result = get_card_type_schema_payload(
        deps.session,
        card_type_name,
        allow_model_name=False,
        require_schema=False,
    )

    if not result.get("success"):
        logger.warning(
            f"⚠️ [Assistant.get_card_type_schema] 卡片類型 '{card_type_name}' 不存在"
        )
        return {
            "success": False,
            "error": f"卡片類型 '{card_type_name}' 不存在"
        }

    output = {
        "success": True,
        "card_type": result.get("card_type") or card_type_name,
        "schema": result.get("schema") or {},
        "description": f"卡片類型 '{card_type_name}' 的完整結構定義"
    }

    logger.info(f"✅ [Assistant.get_card_type_schema] 已返回 Schema：{output}")
    return output


@tool
def get_card_content(
    card_id: int,
) -> Dict[str, Any]:
    """
    獲取指定卡片的詳細內容
    
    使用場景：需要查看卡片的完整數據時調用
    
    Args:
        card_id: 卡片ID
    
    Returns:
        success: True 表示成功，False 表示失敗
        error: 錯誤信息（失敗時）
        card_id: 卡片ID
        title: 卡片標題
        card_type: 卡片類型
        parent_id: 父卡片ID（None表示根級卡片）
        parent_title: 父卡片標題（如果有父卡片）
        parent_type: 父卡片類型（如果有父卡片）
        content: 卡片內容
        created_at: 卡片創建時間
    """

    deps = _get_deps()

    logger.info(f" [Assistant.get_card_content] card_id={card_id}")

    card = deps.session.query(Card).filter(Card.id == card_id).first()
    
    if not card:
        logger.warning(f"⚠️ [Assistant.get_card_content] 卡片 #{card_id} 不存在")
        return {
            "success": False,
            "error": f"卡片 #{card_id} 不存在"
        }
    
    result = {
        "success": True,
        "card_id": card.id,
        "title": card.title,
        "card_type": card.card_type.name if card.card_type else "Unknown",
        "parent_id": card.parent_id,  # 父卡片ID，用於瞭解層級關係
        "content": card.content or {},
        "created_at": str(card.created_at) if card.created_at else None
    }
    
    # 如果有父卡片，添加父卡片信息
    if card.parent_id and card.parent:
        result["parent_title"] = card.parent.title
        result["parent_type"] = card.parent.card_type.name if card.parent.card_type else "Unknown"
    
    logger.info(
        f"✅ [Assistant.get_card_content] 已返回卡片內容 (parent_id={card.parent_id})"
    )
    return result


# NF_ASSISTANT_BATCH_PATCH_BEGIN
def _nf_assistant_get_text_field_for_patch(card, field_path):
    raw = card.content or {}

    if isinstance(raw, str):
        if field_path in ("", "content", "/content"):
            return raw
        raise ValueError("card.content is a string, field_path must be content")

    if not isinstance(raw, dict):
        raise ValueError("card.content is not a readable text object")

    normalized = (field_path or "content").strip()
    candidates = []
    if normalized.startswith("/"):
        candidates.append([p for p in normalized.strip("/").split("/") if p])
    else:
        candidates.append([p for p in normalized.split(".") if p])

    if normalized == "content":
        candidates.append(["content", "content"])

    last_error = None
    for parts in candidates:
        cur = raw
        try:
            for part in parts:
                if not isinstance(cur, dict) or part not in cur:
                    raise KeyError(part)
                cur = cur[part]
            if isinstance(cur, str):
                return cur
            last_error = "field is not text: " + str(field_path)
        except Exception as exc:
            last_error = str(exc)

    raise ValueError(last_error or ("field path not found: " + str(field_path)))


def _nf_assistant_line_span(text, start_line, end_line):
    lines = text.split("\n")
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise ValueError("invalid line range: %s-%s, total lines: %s" % (start_line, end_line, len(lines)))
    return "\n".join(lines[start_line - 1:end_line])


def _nf_assistant_context(text, old_text, radius=120):
    idx = text.find(old_text)
    if idx < 0:
        return "", ""
    return text[max(0, idx - radius):idx], text[idx + len(old_text):idx + len(old_text) + radius]


@tool
def propose_card_text_patches(card_id: int, field_path: str, patches: list) -> dict:
    """
    批量提交正文修改建議，不直接寫入數據庫，由前端編輯器逐條預覽、接受或拒絕。

    使用場景：
    - 用戶要求對正文提出多條修改建議（潤色、糾錯、改寫等）時，使用本工具。

    Args:
        card_id: 目標卡片的ID
        field_path: 字段路徑（如 "content" 表示章節正文）
        patches: 修改建議列表（最多處理 30 條），每條爲 dict，包含：
            - old_text (必填): 當前正文中需要替換的原文片段，應儘量精確
            - new_text (必填): 建議替換爲的新文本
            - start_line/end_line (可選): 1-based 行號範圍，僅作爲輔助定位提示
            - context_before/context_after (可選): 原文前後的上下文片段，用於前端重新定位
            - instruction/reason (可選): 本條修改的理由或說明

    重要約束：
        - 每條 patch 必須同時包含 old_text 和 new_text。
        - old_text 應爲當前正文的精確片段，便於前端定位。

    Returns:
        success: True 表示建議已生成，False 表示失敗
        kind: "assistant_text_patch_batch"（前端識別標記）
        count: 有效建議條數
        patches: 歸一化後的建議列表
        failed_count: 校驗失敗的條數
        failed_patches: 失敗條目及原因
        preview_only: True（表示僅預覽，不寫數據庫）
        needs_user_accept: True（需要用戶逐條確認）
    """
    deps = _get_deps()
    logger.info("[Assistant.propose_card_text_patches] card_id=%s path=%s count=%s", card_id, field_path, len(patches or []))

    try:
        card = deps.session.get(Card, card_id)
        if not card or card.project_id != deps.project_id:
            return {"success": False, "error": "card not found or not in current project: %s" % card_id}

        if not patches:
            return {"success": False, "error": "patches is empty"}

        full_text = _nf_assistant_get_text_field_for_patch(card, field_path or "content")
        normalized = []
        failed = []

        for i, item in enumerate(patches[:30], start=1):
            item = item or {}
            new_text = str(item.get("new_text") or item.get("revised_text") or item.get("replacement_text") or "")
            if not new_text:
                failed.append({"index": i, "error": "missing new_text"})
                continue

            start_line = item.get("start_line")
            end_line = item.get("end_line")
            old_text = item.get("old_text") or item.get("original_text")

            if (not old_text) and start_line and end_line:
                try:
                    old_text = _nf_assistant_line_span(full_text, int(start_line), int(end_line))
                except Exception as exc:
                    failed.append({"index": i, "error": "invalid line range: %s" % exc})
                    continue

            if not old_text:
                failed.append({"index": i, "error": "missing old_text and start_line/end_line"})
                continue

            old_text = str(old_text)
            context_before = str(item.get("context_before") or "")
            context_after = str(item.get("context_after") or "")
            if not context_before and not context_after:
                context_before, context_after = _nf_assistant_context(full_text, old_text)

            normalized.append({
                "id": int(item.get("id") or i),
                "index": i,
                "card_id": card.id,
                "field_path": field_path or "content",
                "start_line": int(start_line) if start_line else None,
                "end_line": int(end_line) if end_line else None,
                "old_text": old_text,
                "original_text": old_text,
                "new_text": new_text,
                "context_before": context_before,
                "context_after": context_after,
                "instruction": item.get("instruction") or item.get("reason") or "",
                "status": "pending",
            })

        if not normalized:
            return {
                "success": False,
                "kind": "assistant_text_patch_batch",
                "status": "text_patch_batch_failed",
                "error": "no valid patch proposals",
                "failed_count": len(failed),
                "failed_patches": failed,
            }

        return {
            "success": True,
            "kind": "assistant_text_patch_batch",
            "status": "text_patch_batch_partial" if failed else "text_patch_batch_proposed",
            "message": "Created %s text patch proposals. Review them in the chapter editor." % len(normalized),
            "card_id": card.id,
            "card_title": card.title,
            "field_path": field_path or "content",
            "count": len(normalized),
            "patches": normalized,
            "failed_count": len(failed),
            "failed_patches": failed,
            "preview_only": True,
            "needs_user_accept": True,
        }

    except Exception as e:
        logger.error("[Assistant.propose_card_text_patches] failed: %s", e, exc_info=True)
        return {"success": False, "error": "failed to create patch proposals: " + str(e)}
# NF_ASSISTANT_BATCH_PATCH_END


@tool
def replace_field_text(
    card_id: int,
    field_path: str,
    old_value: str,
    new_value: str,
) -> Dict[str, Any]:
    """
    替換卡片字段中的指定文本片段（舊兼容工具，優先級低於按行替換）。

    使用場景：
    - 只有在拿不到穩定行號、沒有 `chapter_excerpt` 引用、也沒有 `snapshot_hash` 時，才把它當作兜底方案。
    - 如果上下文已經明確給出“第 X-Y 行”、`chapter_excerpt` 引用或 `snapshot_hash`，不要調用本工具，應改用 `replace_card_text_by_lines`。
    - 適用於大綱描述、短段落或非正文長文本中的模糊片段替換。
    
    Examples:
        1. 精確匹配（短文本，且沒有可用行號）：
        replace_field_text(card_id=42, field_path="content", 
                            old_value="林風猶豫了片刻",
                            new_value="林風毫不猶豫地")
        
        2. 模糊匹配（長文本兜底）：
        replace_field_text(card_id=42, field_path="content",
                            old_value="少年面色蒼白，額頭青筋暴起...現在卻成了個廢人。",
                            new_value="新的完整段落內容...")
    
    Args:
        card_id: 目標卡片的ID
        field_path: 字段路徑（如 "content" 表示章節正文，"overview" 表示概述）
        old_value: 要被替換的原文片段，支持兩種模式：
            1. 精確匹配：提供完整的原文（適用於短文本，50字以內）
            2. 模糊匹配：提供開頭10字 + "..." + 結尾10字（適用於長文本，50字以上）
        new_value: 新的文本內容

    重要約束：
        - 如果已知行號範圍，請不要使用本工具。
        - 如果引用來源是正文選區，請優先使用 `replace_card_text_by_lines`。

    Returns:
        success: True 表示成功，False 表示失敗
        error: 錯誤信息
        card_title: 卡片標題
        replaced_count: 替換的次數
        message: 用戶友好的消息
    """

    deps = _get_deps()

    logger.info(f" [Assistant.replace_field_text] card_id={card_id}, path={field_path}")
    logger.info(f"  要替換的文本長度: {len(old_value)} 字符")
    logger.info(f"  新文本長度: {len(new_value)} 字符")

    try:
        # Use CardService logic directly
        service = CardService(deps.session)
        result = service.replace_field_text(
            card_id=card_id,
            field_path=field_path,
            old_text=old_value,
            new_text=new_value,
            fuzzy_match=True
        )

        # 如果Service執行失敗
        if not result.get("success"):
            raw_error = str(result.get("error") or "替換失敗")
            raw_hint = str(result.get("hint") or "").strip()

            suggestion = ""
            if raw_error in ("未找到指定的原文片段", "未找到開頭文本", "未找到結尾文本", "模糊匹配格式錯誤"):
                suggestion = "建議先調用 get_card_content 獲取最新內容，再複製準確片段重試；長文本請使用“開頭...結尾”格式。"
            elif "不是文本類型" in raw_error:
                suggestion = "目標字段不是字符串文本，建議改用 modify_card_field 按結構化方式更新。"
            elif "字段路徑" in raw_error:
                suggestion = "字段路徑可能不正確，建議先查看卡片結構並確認 field_path。"

            if suggestion:
                result["message"] = f"⚠️ 文本替換失敗：{raw_error}。{suggestion}"
            else:
                result["message"] = f"⚠️ 文本替換失敗：{raw_error}。"

            if raw_hint:
                result["message"] = f"{result['message']}（定位提示：{raw_hint}）"

            logger.warning(
                f"⚠️ [Assistant.replace_field_text] 替換失敗: {result.get('error')}"
            )
            return result
        
        # Service already commits, but tool flow often expects us to handle it or just be sure.
        # CardService.replace_field_text does commit.
        
        logger.info(f"✅ [Assistant.replace_field_text] 替換成功")

        # 添加用戶友好的消息
        result["message"] = (
            f"✅ 已在「{result.get('card_title')}」的 {field_path} 中替換 "
            f"{result.get('replaced_count')} 處內容"
        )

        return result

    except Exception as e:
        logger.error(f"❌ [Assistant.replace_field_text] 替換失敗: {e}")
        return {"success": False, "error": f"替換失敗: {str(e)}"}


@tool
def replace_card_text_by_lines(
    card_id: int,
    field_path: str,
    start_line: int,
    end_line: int,
    new_text: str,
    snapshot_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """
    按行號替換卡片文本片段（位置型替換，正文片段編輯時應優先使用本工具）。

    這是“章節正文 / Markdown 長文本片段修訂”的首選工具，適合以下場景：
    - 用戶明確指定“第 93-102 行”
    - 上下文裏已經有 `chapter_excerpt` 引用
    - 已拿到 `snapshot_hash`
    - 想避免 `replace_field_text` 的模糊匹配誤傷

    調用建議：
    - `field_path` 對章節正文通常傳 `content`
    - 如果有片段引用，優先傳 `snapshot_hash`；通常不需要再額外傳舊片段文本
    - 當你能定位具體行號時，不要退回 `replace_field_text`

    Examples:
        1. 根據正文片段引用直接替換：
           replace_card_text_by_lines(
               card_id=666,
               field_path="content",
               start_line=93,
               end_line=102,
               new_text="新的正文片段……",
               snapshot_hash="abc123"
           )

        2. 已知要修改的行段，但沒有快照時：
           replace_card_text_by_lines(
               card_id=666,
               field_path="content",
               start_line=40,
               end_line=44,
               new_text="修訂後的內容"
           )
    """
    deps = _get_deps()
    logger.info(
        f"🧩 [Assistant.replace_card_text_by_lines] card_id={card_id}, "
        f"path={field_path}, lines={start_line}-{end_line}"
    )

    try:
        service = CardService(deps.session)
        result = service.replace_field_text_by_lines(
            card_id=card_id,
            field_path=field_path,
            start_line=start_line,
            end_line=end_line,
            new_text=new_text,
            snapshot_hash=snapshot_hash,
        )
        if not result.get("success"):
            raw_error = str(result.get("error") or "按行替換失敗")
            if "快照校驗失敗" in raw_error or "原片段校驗失敗" in raw_error:
                result["message"] = (
                    f"⚠️ {raw_error}。建議先重新引用最新正文片段，再按行替換。"
                )
            else:
                result["message"] = f"⚠️ 按行替換失敗：{raw_error}"
            return result

        result["message"] = (
            f"✅ 已按行替換 {start_line}-{end_line} 行，"
            f"將 {result.get('replaced_line_count')} 行替換爲 {result.get('new_line_count')} 行，"
            f"目標字段：{field_path}"
        )
        return result
    except Exception as e:
        logger.error(f"❌ [Assistant.replace_card_text_by_lines] 失敗: {e}")
        return {"success": False, "error": f"按行替換失敗: {str(e)}"}


@tool
def list_reviews_for_target(
    target_id: int,
    review_type: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    獲取指定目標卡片綁定的審核結果卡片列表（用於注入 review_result 引用）。
    """
    deps = _get_deps()
    logger.info(
        f"📚 [Assistant.list_reviews_for_target] target_id={target_id}, review_type={review_type}, limit={limit}"
    )
    try:
        review_card_type = deps.session.query(CardType).filter(CardType.name == REVIEW_RESULT_CARD_TYPE_NAME).first()
        if not review_card_type:
            return {"success": False, "error": f"缺少卡片類型: {REVIEW_RESULT_CARD_TYPE_NAME}"}

        rows = (
            deps.session.query(Card)
            .filter(Card.project_id == deps.project_id, Card.card_type_id == review_card_type.id)
            .order_by(Card.created_at.desc())
            .all()
        )
        filtered = []
        for row in rows:
            content = dict(row.content or {})
            if int(content.get("review_target_card_id") or -1) != target_id:
                continue
            if review_type and review_type != "all" and str(content.get("review_type") or "") != review_type:
                continue
            filtered.append(row)
        filtered = filtered[: max(1, min(limit, 100))]
        return {
            "success": True,
            "count": len(filtered),
            "reviews": [
                {
                    "review_card_id": row.id,
                    "project_id": row.project_id,
                    "target_id": int((row.content or {}).get("review_target_card_id") or 0),
                    "target_title": (row.content or {}).get("review_target_title"),
                    "review_type": (row.content or {}).get("review_type"),
                    "review_profile": (row.content or {}).get("review_profile"),
                    "target_field": (row.content or {}).get("review_target_field"),
                    "quality_gate": (row.content or {}).get("quality_gate"),
                    "prompt_name": (row.content or {}).get("prompt_name"),
                    "created_at": (row.content or {}).get("reviewed_at") or str(row.created_at),
                    "title": row.title,
                }
                for row in filtered
            ],
        }
    except Exception as e:
        logger.error(f"❌ [Assistant.list_reviews_for_target] 失敗: {e}")
        return {"success": False, "error": f"獲取審核記錄失敗: {str(e)}"}


@tool
def get_review_record(review_id: int) -> Dict[str, Any]:
    """
    獲取單張審核結果卡片詳情（包含完整審核 Markdown）。
    """
    deps = _get_deps()
    logger.info(f"📄 [Assistant.get_review_record] review_card_id={review_id}")
    try:
        row = deps.session.get(Card, review_id)
        review_card_type = deps.session.query(CardType).filter(CardType.name == REVIEW_RESULT_CARD_TYPE_NAME).first()
        if not row or row.project_id != deps.project_id or not review_card_type or row.card_type_id != review_card_type.id:
            return {"success": False, "error": f"審核結果卡片 #{review_id} 不存在"}
        content = dict(row.content or {})
        return {
            "success": True,
            "review": {
                "review_card_id": row.id,
                "project_id": row.project_id,
                "target_id": int(content.get("review_target_card_id") or 0),
                "target_title": content.get("review_target_title"),
                "review_type": content.get("review_type"),
                "review_profile": content.get("review_profile"),
                "target_field": content.get("review_target_field"),
                "quality_gate": content.get("quality_gate"),
                "prompt_name": content.get("prompt_name"),
                "result_text": content.get("review_markdown"),
                "content_snapshot": content.get("target_snapshot"),
                "meta": content.get("meta"),
                "created_at": content.get("reviewed_at") or str(row.created_at),
                "title": row.title,
            },
        }
    except Exception as e:
        logger.error(f"❌ [Assistant.get_review_record] 失敗: {e}")
        return {"success": False, "error": f"讀取審核記錄失敗: {str(e)}"}


@tool
def delete_card(
    card_id: int,
    skip_confirmation: bool = False
) -> Dict[str, Any]:
    """
    刪除卡片（危險操作）
    
    ⚠️ **確認規則：**
    - **用戶明確指令**（如"刪除角色卡張三"）：可以直接執行，設置 skip_confirmation=True
    - **模糊指令或你自主判斷**：必須先獲取用戶確認，設置 skip_confirmation=False
    
    **判斷標準：**
    - 用戶消息中明確指定了要刪除的卡片（通過標題、ID等唯一標識） → 可直接執行
    - 用戶說"刪除那個卡片"、"刪掉測試的"等模糊表述 → 需要確認
    - 你自己判斷某個卡片需要刪除（用戶沒有明說） → 需要確認
    
    **確認流程：**
    1. 首先以 skip_confirmation=False 調用，獲取確認請求
    2. 工具返回 status="confirmation_required" 和卡片信息
    3. 向用戶說明要刪除的卡片詳情，詢問"是否確認刪除？"
    4. 用戶明確回覆"確認"、"確認刪除"後，以 skip_confirmation=True 再次調用
    
    Args:
        card_id: 要刪除的卡片ID
        skip_confirmation: 是否跳過確認（默認 False，需要確認）
    
    Returns:
        Dict 包含:
        - 如果需要確認：{"status": "confirmation_required", "message": "...", "data": {...}}
        - 如果已確認：{"success": true, "message": "卡片已刪除", ...}
    
    Examples:
        # 示例1：用戶明確指令 "刪除角色卡張三"
        delete_card(card_id=123, skip_confirmation=True)  # 直接執行
        
        # 示例2：用戶模糊指令 "刪除測試卡片" 或你自主判斷需要刪除
        # 第一步：獲取確認
        result = delete_card(card_id=123, skip_confirmation=False)
        # 你："我需要刪除卡片《測試》，此操作不可撤銷。是否確認？"
        # 用戶："確認刪除"
        # 第二步：執行刪除
        result = delete_card(card_id=123, skip_confirmation=True)
    """
    deps = _get_deps()
    
    logger.info(f"🗑️ [Assistant.delete_card] card_id={card_id}, skip_confirmation={skip_confirmation}")
    
    try:
        # 獲取卡片信息
        card = _get_card_by_id(deps.session, card_id, deps.project_id)
        if not card:
            result = CardOperationResult(
                success=False,
                status=ToolResultStatus.FAILED,
                message=f"卡片 ID={card_id} 不存在或不屬於當前項目",
                error=f"卡片 ID={card_id} 不存在"
            )
            return to_dict(result)
        
        # 檢查是否有子卡片
        child_count = deps.session.query(Card).filter(
            Card.parent_id == card_id
        ).count()
        
        # 如果需要確認，返回確認請求
        if not skip_confirmation:
            warning = None
            if child_count > 0:
                warning = f"此卡片有 {child_count} 個子卡片，刪除後子卡片也會被刪除"
            
            result = ConfirmationRequest(
                confirmation_id=str(uuid.uuid4()),
                action="delete_card",
                action_params={"card_id": card_id},
                message=f"❓ 確認要刪除卡片《{card.title}》嗎？請用戶明確說\"確認刪除\"或\"取消\"",
                warning=warning,
                data={
                    "card_id": card_id,
                    "card_title": card.title,
                    "card_type": card.card_type.name,
                    "child_count": child_count
                }
            )
            logger.info(f"⚠️ [Assistant.delete_card] 等待用戶確認")
            return to_dict(result)
        
        # 用戶已確認，執行刪除
        logger.info(f"✅ [Assistant.delete_card] 用戶已確認，開始刪除")
        
        # 刪除子卡片（如果有）
        if child_count > 0:
            deps.session.query(Card).filter(Card.parent_id == card_id).delete()
            logger.info(f"  已刪除 {child_count} 個子卡片")
        
        # 刪除卡片本身
        card_title = card.title
        deps.session.delete(card)
        deps.session.commit()
        
        result = CardOperationResult(
            success=True,
            status=ToolResultStatus.SUCCESS,
            message=f"✅ 卡片《{card_title}》已成功刪除" + (f"（包括 {child_count} 個子卡片）" if child_count > 0 else ""),
            card_id=card_id,
            card_title=card_title,
            data={"deleted_children": child_count}
        )
        logger.info(f"✅ [Assistant.delete_card] 刪除成功")
        return to_dict(result)
    
    except Exception as e:
        logger.error(f"❌ [Assistant.delete_card] 失敗: {e}", exc_info=True)
        result = CardOperationResult(
            success=False,
            status=ToolResultStatus.FAILED,
            message=f"刪除失敗: {str(e)}",
            error=str(e)
        )
        return to_dict(result)


@tool
def move_card(
    card_id: int,
    new_parent_id: Optional[int] = None,
    skip_confirmation: bool = False
) -> Dict[str, Any]:
    """
    移動卡片到新的父卡片下（危險操作）
    
    ⚠️ **確認規則：**
    - **用戶明確指令**（如"把角色卡清風移動到核心藍圖下面"）：可以直接執行，設置 skip_confirmation=True
    - **模糊指令或你自主判斷**：必須先獲取用戶確認，設置 skip_confirmation=False
    
    **判斷標準：**
    - 用戶明確說了要移動哪個卡片到哪裏 → 可直接執行
    - 用戶說"移動那個卡片"、"把它放到別處"等模糊表述 → 需要確認
    - 你自己判斷某個卡片需要移動（用戶沒有明說） → 需要確認
    
    **確認流程：**
    1. 首先以 skip_confirmation=False 調用，獲取確認請求
    2. 工具返回 status="confirmation_required" 和移動詳情
    3. 向用戶說明移動操作："將卡片《X》從 Y 移動到 Z，是否確認？"
    4. 用戶明確回覆"確認"、"確認移動"後，以 skip_confirmation=True 再次調用
    
    Args:
        card_id: 要移動的卡片ID
        new_parent_id: 新的父卡片ID（None 表示移動到根級別）
        skip_confirmation: 是否跳過確認（默認 False，需要確認）
    
    Returns:
        Dict 包含:
        - 如果需要確認：{"status": "confirmation_required", "message": "...", "data": {...}}
        - 如果已確認：{"success": true, "message": "卡片已移動", ...}
    
    Examples:
        # 示例1：用戶明確指令 "把清風移動到核心藍圖下面"
        move_card(card_id=123, new_parent_id=456, skip_confirmation=True)  # 直接執行
        
        # 示例2：用戶模糊指令或你自主判斷
        # 第一步：獲取確認
        result = move_card(card_id=123, new_parent_id=456, skip_confirmation=False)
        # 你："將卡片《清風》從根級別移動到《核心藍圖》下，是否確認？"
        # 用戶："確認移動"
        # 第二步：執行移動
        result = move_card(card_id=123, new_parent_id=456, skip_confirmation=True)
    """
    deps = _get_deps()
    
    logger.info(f"📦 [Assistant.move_card] card_id={card_id}, new_parent={new_parent_id}, skip_confirmation={skip_confirmation}")
    
    try:
        # 1. 獲取要移動的卡片
        card = _get_card_by_id(deps.session, card_id, deps.project_id)
        if not card:
            result = CardOperationResult(
                success=False,
                status=ToolResultStatus.FAILED,
                message=f"卡片 ID={card_id} 不存在或不屬於當前項目",
                error=f"卡片 ID={card_id} 不存在"
            )
            return to_dict(result)
        
        # 2. 驗證新父卡片
        new_parent = None
        if new_parent_id is not None:
            new_parent = _get_card_by_id(deps.session, new_parent_id, deps.project_id)
            if not new_parent:
                result = CardOperationResult(
                    success=False,
                    status=ToolResultStatus.FAILED,
                    message=f"目標父卡片 ID={new_parent_id} 不存在或不屬於當前項目",
                    error=f"目標父卡片不存在"
                )
                return to_dict(result)
            
            # 防止循環引用：不能將卡片移動到自己或自己的子卡片下
            if new_parent_id == card_id:
                result = CardOperationResult(
                    success=False,
                    status=ToolResultStatus.FAILED,
                    message="不能將卡片移動到自己下面",
                    error="循環引用錯誤"
                )
                return to_dict(result)
            
            # TODO: 檢查是否是子孫卡片（需要遞歸檢查）
        
        # 3. 獲取當前父卡片信息
        old_parent = None
        old_parent_title = "根級別"
        if card.parent_id:
            old_parent = deps.session.get(Card, card.parent_id)
            if old_parent:
                old_parent_title = f"《{old_parent.title}》"
        
        new_parent_title = "根級別" if not new_parent else f"《{new_parent.title}》"
        
        # 4. 如果需要確認，返回確認請求
        if not skip_confirmation:
            result = ConfirmationRequest(
                confirmation_id=str(uuid.uuid4()),
                action="move_card",
                action_params={
                    "card_id": card_id,
                    "new_parent_id": new_parent_id
                },
                message=f"❓ 確認要將卡片《{card.title}》從 {old_parent_title} 移動到 {new_parent_title} 嗎？請用戶明確說\"確認移動\"或\"取消\"",
                data={
                    "card_id": card_id,
                    "card_title": card.title,
                    "from_parent": old_parent_title,
                    "to_parent": new_parent_title
                }
            )
            logger.info(f"⚠️ [Assistant.move_card] 等待用戶確認")
            return to_dict(result)
        
        # 5. 用戶已確認，執行移動
        logger.info(f"✅ [Assistant.move_card] 用戶已確認，開始移動")
        
        card.parent_id = new_parent_id
        deps.session.commit()
        
        result = CardOperationResult(
            success=True,
            status=ToolResultStatus.SUCCESS,
            message=f"✅ 卡片《{card.title}》已從 {old_parent_title} 移動到 {new_parent_title}",
            card_id=card_id,
            card_title=card.title,
            data={
                "from_parent": old_parent_title,
                "to_parent": new_parent_title
            }
        )
        logger.info(f"✅ [Assistant.move_card] 移動成功")
        return to_dict(result)
    
    except Exception as e:
        logger.error(f"❌ [Assistant.move_card] 失敗: {e}", exc_info=True)
        result = CardOperationResult(
            success=False,
            status=ToolResultStatus.FAILED,
            message=f"移動失敗: {str(e)}",
            error=str(e)
        )
        return to_dict(result)


# 導出所有 LangChain 工具（已通過 @tool 裝飾）
ASSISTANT_TOOLS = [
    search_cards,
    create_card,
    update_card,
    modify_card_field,
    delete_card,
    move_card,
    replace_card_text_by_lines, propose_card_text_patches,
    replace_field_text,
    list_reviews_for_target,
    get_review_record,
    get_card_type_schema,
    get_card_content,
]

ASSISTANT_TOOL_REGISTRY = {tool.name: tool for tool in ASSISTANT_TOOLS}

ASSISTANT_TOOL_DESCRIPTIONS = {
    tool.name: {
        "description": tool.description,
        "args": tool.args,
    }
    for tool in ASSISTANT_TOOLS
}
