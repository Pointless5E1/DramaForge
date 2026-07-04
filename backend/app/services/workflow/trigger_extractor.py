"""觸發器提取器 - 從工作流代碼中自動提取觸發器配置

用於優化觸發器系統，避免單獨的 WorkflowTrigger 表查詢。
"""

from typing import List, Dict, Any
from loguru import logger


def extract_triggers_from_code(code: str) -> List[Dict[str, Any]]:
    """從工作流代碼中提取觸發器配置
    
    解析代碼中的觸發器節點，提取觸發器信息並緩存到 Workflow.triggers_cache 字段。
    
    支持的觸發器節點：
        - Trigger.ProjectCreated: 項目創建觸發器
          參數: template (可選)
          
        - Trigger.CardSaved: 卡片保存觸發器
          參數: card_type (可選), on_create (默認false), on_update (默認true)
    
    Args:
        code: 工作流代碼（註釋標記 DSL）
        
    Returns:
        觸發器配置列表，格式：
        [
            {
                "event": "project.created",
                "match": {"template": "snowflake"}  # 從節點參數構建
            },
            ...
        ]
    
    Example:
        >>> code = '''
        ... #@node()
        ... trigger = Trigger.ProjectCreated(template="snowflake")
        ... #</node>
        ... '''
        >>> extract_triggers_from_code(code)
        [{"event": "project.created", "match": {"template": "snowflake"}}]
    """
    from app.services.workflow.parser.marker_parser import WorkflowParser
    
    if not code or not code.strip():
        return []
    
    # 節點類型到事件名稱的映射
    NODE_TYPE_TO_EVENT = {
        "Trigger.ProjectCreated": "project.created",
        "Trigger.CardSaved": "card.saved",
    }
    
    try:
        # 解析工作流代碼
        parser = WorkflowParser()
        plan = parser.parse(code)
        
        triggers = []
        
        # 遍歷所有語句，查找觸發器節點
        for stmt in plan.statements:
            # 跳過禁用的節點
            if stmt.disabled:
                logger.debug(f"[TriggerExtractor] 跳過禁用的觸發器節點: {stmt.variable}")
                continue
            
            node_type = stmt.node_type
            config = stmt.config or {}
            
            # 檢查是否是觸發器節點
            event = NODE_TYPE_TO_EVENT.get(node_type)
            if not event:
                continue
            
            # 根據節點類型構建 match 條件
            match = {}
            
            if node_type == "Trigger.ProjectCreated":
                # 提取 template 參數
                if "template" in config and config["template"]:
                    match["template"] = config["template"]
                    
            elif node_type == "Trigger.CardSaved":
                # 提取 card_type 參數
                if "card_type" in config and config["card_type"]:
                    match["card_type"] = config["card_type"]
                # 提取 on_create 和 on_update 參數
                # 默認值需與 TriggerCardSavedInput 保持一致：on_create=False, on_update=True
                on_create = bool(config.get("on_create", False))
                on_update = bool(config.get("on_update", True))

                # 兩者都關閉：該觸發器不應觸發任何事件，直接跳過
                if not on_create and not on_update:
                    logger.debug("[TriggerExtractor] 跳過無效 Trigger.CardSaved：on_create 和 on_update 均爲 false")
                    continue

                # 僅創建 / 僅更新：收斂到 is_created 條件
                if on_create and not on_update:
                    match["is_created"] = True
                elif not on_create and on_update:
                    match["is_created"] = False
                # 兩者都爲 true：不添加 is_created 條件（創建/更新都觸發）
            
            trigger_config = {
                "event": event,
                "match": match if match else None
            }
            
            triggers.append(trigger_config)
        
        logger.debug(f"[TriggerExtractor] 從代碼中提取了 {len(triggers)} 個觸發器")
        return triggers
    
    except Exception as e:
        logger.error(f"[TriggerExtractor] 提取觸發器失敗: {e}")
        return []


def sync_triggers_cache(workflow, session) -> None:
    """同步工作流的觸發器緩存
    
    從 definition_code 中提取觸發器，更新 triggers_cache 字段。
    
    Args:
        workflow: Workflow 對象
        session: 數據庫會話
    """
    if not workflow.definition_code:
        workflow.triggers_cache = []
        return
    
    triggers = extract_triggers_from_code(workflow.definition_code)
    
    workflow.triggers_cache = triggers
    session.add(workflow)
    
    logger.info(f"[TriggerExtractor] 工作流 {workflow.id} ({workflow.name}) 的觸發器緩存已更新: {len(triggers)} 個觸發器")


def match_event(event_name: str, event_data: Dict[str, Any], trigger: Dict[str, Any]) -> bool:
    """判斷事件是否匹配觸發器
    
    Args:
        event_name: 事件名稱（如 project.created, card.saved）
        event_data: 事件數據（如 {"project_id": 1, "template": "snowflake"}）
        trigger: 觸發器配置（包含 event 和 match 字段）
        
    Returns:
        是否匹配
    """
    # 1. 事件名稱必須匹配
    if trigger.get("event") != event_name:
        return False
    
    # 2. 如果沒有 match 條件，直接匹配
    match_conditions = trigger.get("match")
    if not match_conditions:
        return True
    
    # 3. 檢查所有 match 條件
    for key, expected_value in match_conditions.items():
        actual_value = event_data.get(key)
        
        # 簡單相等匹配
        if actual_value != expected_value:
            return False
    
    return True


def get_active_triggers_by_event(session, event_name: str, event_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """獲取匹配指定事件的觸發器
    
    Args:
        session: 數據庫會話
        event_name: 事件名稱（如 project.created, card.saved）
        event_data: 事件數據（如 {"project_id": 1, "template": "snowflake"}）
        
    Returns:
        匹配的觸發器列表，格式：
        [
            {
                "workflow_id": 1,
                "event": "project.created",
                "match": {"template": "snowflake"}
            },
            ...
        ]
    """
    from sqlmodel import select
    from app.db.models import Workflow
    
    # 查詢所有激活的工作流
    stmt = select(Workflow).where(
        Workflow.is_active == True,
        Workflow.triggers_cache.isnot(None)
    )
    workflows = session.exec(stmt).all()
    
    matched_triggers = []
    
    for wf in workflows:
        if not wf.triggers_cache:
            continue
        
        for trigger in wf.triggers_cache:
            # 使用新的匹配邏輯
            if match_event(event_name, event_data, trigger):
                matched_triggers.append({
                    "workflow_id": wf.id,
                    **trigger
                })
    
    logger.debug(f"[TriggerExtractor] 找到 {len(matched_triggers)} 個匹配的觸發器: event={event_name}, data={event_data}")
    return matched_triggers
