from typing import Any, Dict, List, Optional, AsyncIterator, Union, TYPE_CHECKING
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlalchemy.orm.attributes import flag_modified

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from app.db.models import Card
from app.services.card_service import CardService
from app.schemas.card import CardCreate
from ...registry import register_node
from ..base import BaseNode, get_card_type_by_name


class CardBatchUpsertInput(BaseModel):
    """批量更新卡片輸入"""
    project_id: int = Field(..., description="項目ID（必須顯式傳遞）")
    items: List[Any] = Field(..., description="數據列表（必須是list類型）")
    card_type: str = Field(
        ..., 
        description="卡片類型名稱",
        json_schema_extra={"x-component": "CardTypeSelect"}
    )
    title_template: str = Field(..., description="標題模板，支持 {item.field} 語法")
    content_template: Optional[Any] = Field(default_factory=dict, description="內容模板（可選，支持 dict 或 str）")
    match_by: str = Field("title", description="匹配現有卡片的方式（默認按標題）")
    parent_id: Optional[Any] = Field(None, description="父卡片ID（支持ID數字或模板語法 {item.pid}）")


class CardBatchUpsertOutput(BaseModel):
    """批量更新卡片輸出"""
    cards: List[Dict[str, Any]] = Field(..., description="處理後的卡片列表")
    output: List[int] = Field(..., description="卡片ID列表（兼容）")


@register_node
class CardBatchUpsertNode(BaseNode[CardBatchUpsertInput, CardBatchUpsertOutput]):
    """批量創建/更新卡片節點。

    嚴格約束（給工作流編寫 Agent）：
    1) `content_template` 必須是字面量 dict，且字段與目標卡片 schema 對齊。
    2) 允許在字段值中使用 `{item.xxx}` 佔位符；禁止將整個 `content_template` 設爲表達式結果。
    3) 不能臆造字段，必須先確認該卡片類型可寫字段。

    推薦：先查詢卡片類型 schema，再編寫 `title_template/content_template`。
    """
    node_type = "Card.BatchUpsert"
    category = "card"
    label = "批量更新卡片"
    description = "根據列表數據批量創建或更新卡片"
    
    input_model = CardBatchUpsertInput
    output_model = CardBatchUpsertOutput

    async def execute(self, inputs: CardBatchUpsertInput) -> AsyncIterator[Union['ProgressEvent', CardBatchUpsertOutput]]:
        """批量更新卡片（支持斷點續傳）"""
        from ...engine.async_executor import ProgressEvent
        
        items = inputs.items
        
        # 強制要求輸入是列表
        if not isinstance(items, list):
            raise ValueError(f"items 輸入必須是列表類型，當前類型: {type(items).__name__}。請使用 Data.ExtractPath 節點提取列表。")
        
        # === 1. 讀取檢查點 ===
        checkpoint = getattr(self.context, 'checkpoint', None)
        start_index = checkpoint.get('processed_count', 0) if checkpoint else 0
        
        if start_index > 0:
            logger.info(f"[BatchUpsert] 從檢查點恢復: 已處理 {start_index}/{len(items)}")
        
        # 獲取基礎 parent_id 配置
        base_parent_id = inputs.parent_id
        
        # 兼容性處理：如果 parent_id 是字典（來自 Card.Read 輸出），提取 id
        if isinstance(base_parent_id, dict):
            base_parent_id = base_parent_id.get("id")
        
        # 獲取卡片類型
        card_type = get_card_type_by_name(self.context.session, inputs.card_type)
        if not card_type:
            raise ValueError(f"卡片類型不存在: {inputs.card_type}")

        # 使用顯式傳遞的 project_id（不再從全局變量查找）
        project_id = inputs.project_id
        
        logger.info(
            f"[BatchUpsert] 使用顯式傳遞的項目ID: project_id={project_id}"
        )

        results = []
        service = CardService(self.context.session)
        total = len(items)
        
        # === 2. 從檢查點繼續處理 ===
        for index in range(start_index, total):
            item = items[index]
            
            # 準備模版上下文
            ctx = {"item": item, "index": index + 1}
            
            # 渲染標題
            try:
                title = self._render_template(inputs.title_template, ctx)
            except Exception as e:
                logger.warning(f"[BatchUpsert] 標題渲染失敗: {e}")
                continue
                
            if not title:
                continue

            # 計算當前項的 parent_id
            current_parent_id = None
            if base_parent_id is not None:
                if isinstance(base_parent_id, int):
                    current_parent_id = base_parent_id
                elif isinstance(base_parent_id, str):
                    if '{' in base_parent_id and '}' in base_parent_id:
                        # 模板渲染
                        rendered = self._render_template(base_parent_id, ctx)
                        # 嘗試轉 int
                        if rendered and rendered.isdigit():
                            current_parent_id = int(rendered)
                        else:
                            # 渲染結果爲空或非數字，視爲無父級或無效
                            current_parent_id = None 
                    elif base_parent_id.isdigit():
                         current_parent_id = int(base_parent_id)
            
            # 查找現有卡片
            stmt = select(Card).where(
                Card.project_id == project_id,
                Card.card_type_id == card_type.id,
                Card.title == title
            )
            if current_parent_id:
                stmt = stmt.where(Card.parent_id == current_parent_id)
            
            existing_card = self.context.session.exec(stmt).first()
            
            # 渲染內容
            content = {}
            if inputs.content_template:
                rendered_content = self._render_content(inputs.content_template, ctx)
                # 確保 content 是字典類型
                if isinstance(rendered_content, dict):
                    content = rendered_content
                elif rendered_content:  # 非空但不是字典，包裝成字典
                    content = {"value": rendered_content}
                # 如果是空字符串或 None，保持 content 爲空字典
            elif isinstance(item, dict):
                 # 如果沒有模板且 item 是 dict，默認使用 item 作爲內容
                 content = item
            
            if existing_card:
                # 更新
                updated = False
                if content:
                    # 簡單合併
                    if not isinstance(existing_card.content, dict):
                        existing_card.content = {}
                    existing_card.content.update(content)
                    flag_modified(existing_card, "content")
                    updated = True
                
                # 如果父ID變化（移動）
                if current_parent_id and existing_card.parent_id != current_parent_id:
                    existing_card.parent_id = current_parent_id
                    updated = True
                    
                if updated:
                    self.context.session.add(existing_card)
                    # 手動提交更新
                    self.context.session.commit()
                    self.context.session.refresh(existing_card)
                    results.append(existing_card)
                else:
                    results.append(existing_card)
            else:
                # 創建
                try:
                    card_create = CardCreate(
                        title=title,
                        content=content,
                        card_type_id=card_type.id,
                        parent_id=current_parent_id,
                        project_id=project_id
                    )
                    
                    new_card = service.create(card_create, project_id)
                    results.append(new_card)
                except Exception as e:
                    logger.error(f"[BatchUpsert] 創建卡片失敗: {e}")
                    continue
            
            # === 3. 報告進度（自動保存檢查點）===
            percent = ((index + 1) / total) * 100
            yield ProgressEvent(
                percent=percent,
                message=f"已處理 {index + 1}/{total} 張卡片",
                data={
                    'processed_count': index + 1,  # ✅ 輕量級：計數器
                    'last_title': title            # ✅ 輕量級：標識符
                }
            )
        
        self.context.session.commit()
        
        # 刷新以獲取ID
        touched = self.context.variables.setdefault("touched_card_ids", [])
        for card in results:
            self.context.session.refresh(card)
            if card.id not in touched:
                touched.append(card.id)

        logger.info(f"[BatchUpsert] 批量處理完成: {len(results)} 個卡片 ({inputs.card_type})")
        
        # === 4. 返回最終結果 ===
        yield CardBatchUpsertOutput(
            cards=[
                {
                    "id": c.id,
                    "title": c.title,
                    "content": c.content,
                    "parent_id": c.parent_id
                } for c in results
            ],
            output=[c.id for c in results]  # 兼容性輸出
        )

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """簡單的字符串模版渲染 {a.b}"""
        # 簡單實現，支持 {item.field}
        # 更復雜的可以使用 jinja2，這裏先手寫一個簡單的
        import re
        
        def replace(match):
            path = match.group(1).strip()
            # 解析路徑 item.name
            parts = path.split('.')
            value = context
            try:
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    elif hasattr(value, part):
                        value = getattr(value, part)
                    else:
                        value = None
                        break
                return str(value) if value is not None else ""
            except Exception:
                return ""

        return re.sub(r'\{([^}]+)\}', replace, template)

    def _render_content(self, template: Any, context: Dict[str, Any]) -> Any:
        "遞歸渲染內容"
        if isinstance(template, str):
            # 只有包含 {} 才嘗試渲染
            if '{' in template and '}' in template:
                # 特殊處理：如果是單一路徑引用（如 {item.ai_result}），返回原始對象
                import re
                single_path_match = re.fullmatch(r'\{([^}]+)\}', template)
                if single_path_match:
                    path = single_path_match.group(1).strip()
                    parts = path.split('.')
                    value = context
                    try:
                        for part in parts:
                            if isinstance(value, dict):
                                value = value.get(part)
                            elif hasattr(value, part):
                                value = getattr(value, part)
                            else:
                                value = None
                                break
                        # 如果解析成功，返回原始對象
                        if value is not None:
                            return value
                    except Exception:
                        pass
                
                # Fallback：正常字符串渲染
                return self._render_template(template, context)
            return template
        elif isinstance(template, dict):
            return {k: self._render_content(v, context) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._render_content(v, context) for v in template]
        else:
            return template
