"""工作流工具函數

用於Schema解析、路徑訪問、模板渲染等。
"""

from typing import Any, Optional, List, Dict
import re
from sqlmodel import Session
from loguru import logger

from app.db.models import Card


def parse_schema_fields(schema: dict, path: str = "$.content", max_depth: int = 5) -> List[dict]:
    """解析JSON Schema字段結構，支持嵌套對象和引用
    
    Args:
        schema: JSON Schema對象
        path: 字段路徑前綴
        max_depth: 最大遞歸深度
        
    Returns:
        字段列表，每個字段包含: name, type, path, children(可選)
    """
    if max_depth <= 0:
        return []
    
    fields = []
    try:
        # 獲取$defs用於解析引用
        defs = schema.get("$defs", {})
        
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return fields
            
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                continue
            
            # 解析引用
            resolved_schema = resolve_schema_ref(field_schema, defs)
            
            field_type = resolved_schema.get("type", "unknown")
            field_title = resolved_schema.get("title", field_name)
            field_description = resolved_schema.get("description", "")
            field_path = f"{path}.{field_name}"
            
            field_info = {
                "name": field_name,
                "title": field_title,
                "type": field_type,
                "path": field_path,
                "description": field_description,
                "required": field_name in schema.get("required", []),
                "expanded": False
            }
            
            # 處理anyOf類型（可選類型）
            if "anyOf" in resolved_schema:
                non_null_schema = None
                for any_schema in resolved_schema["anyOf"]:
                    if isinstance(any_schema, dict) and any_schema.get("type") != "null":
                        non_null_schema = resolve_schema_ref(any_schema, defs)
                        break
                if non_null_schema:
                    resolved_schema = non_null_schema
                    field_type = resolved_schema.get("type", "unknown")
                    field_info["type"] = field_type
            
            # 處理嵌套對象
            if field_type == "object" and "properties" in resolved_schema:
                children = parse_schema_fields(resolved_schema, field_path, max_depth - 1)
                if children:
                    field_info["children"] = children
                    field_info["expandable"] = True
            
            # 處理數組類型
            elif field_type == "array" and "items" in resolved_schema:
                items_schema = resolved_schema["items"]
                items_resolved = resolve_schema_ref(items_schema, defs)
                
                if items_resolved.get("type") == "object" and "properties" in items_resolved:
                    children = parse_schema_fields(items_resolved, f"{field_path}[0]", max_depth - 1)
                    if children:
                        field_info["children"] = children
                        field_info["expandable"] = True
                        field_info["array_item_type"] = "object"
                else:
                    # 簡單數組類型
                    field_info["array_item_type"] = items_resolved.get("type", "unknown")
            
            fields.append(field_info)
            
    except Exception as e:
        logger.warning(f"解析Schema字段失敗: {e}")
    
    return fields


def resolve_schema_ref(schema: dict, defs: dict) -> dict:
    """解析Schema引用
    
    Args:
        schema: Schema對象
        defs: $defs定義
        
    Returns:
        解析後的Schema
    """
    if not isinstance(schema, dict):
        return schema
    
    # 處理$ref引用
    if "$ref" in schema:
        ref_path = schema["$ref"]
        if ref_path.startswith("#/$defs/"):
            ref_name = ref_path.replace("#/$defs/", "")
            if ref_name in defs:
                resolved = defs[ref_name]
                # 保留原schema的title和description
                if "title" in schema:
                    resolved = {**resolved, "title": schema["title"]}
                if "description" in schema:
                    resolved = {**resolved, "description": schema["description"]}
                return resolved
    
    return schema


def get_card_by_id(session: Session, card_id: int) -> Optional[Card]:
    """根據ID獲取卡片
    
    Args:
        session: 數據庫會話
        card_id: 卡片ID
        
    Returns:
        卡片對象或None
    """
    try:
        return session.get(Card, int(card_id))
    except Exception:
        return None


def get_by_path(obj: Any, path: str) -> Any:
    """按JSONPath獲取值
    
    支持 $.content.a.b.c 與 $.a.b 格式
    
    Args:
        obj: 目標對象
        path: JSONPath路徑
        
    Returns:
        獲取的值或None
    """
    if not path or not isinstance(path, str):
        return None
    if not path.startswith("$."):
        return None
    parts = path[2:].split(".")
    # 處理根 '$'：若 obj 爲 {"$": base} 則先取出 base
    if isinstance(obj, dict) and "$" in obj:
        cur: Any = obj.get("$")
    else:
        cur = obj
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            try:
                cur = getattr(cur, p)
            except Exception:
                return None
    return cur


def set_by_path(obj: Dict[str, Any], path: str, value: Any) -> bool:
    """按JSONPath設置值
    
    Args:
        obj: 目標對象
        path: JSONPath路徑（必須以$.開頭）
        value: 要設置的值
    
    Returns:
        是否設置成功
    """
    if not isinstance(obj, dict) or not isinstance(path, str) or not path.startswith("$."):
        return False
    
    parts = path[2:].split(".")
    cur: Dict[str, Any] = obj
    
    # 遍歷到倒數第二層，確保路徑存在
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]  # type: ignore[assignment]
    
    # 設置最後一層的值
    cur[parts[-1]] = value
    return True


# 模板渲染相關
_TPL_PATTERN = re.compile(r"\{([^{}]+)\}")


def resolve_expr(expr: str, state: dict) -> Any:
    """解析表達式
    
    支持: index, item.xxx, current.xxx, scope.xxx, $.content.xxx
    
    Args:
        expr: 表達式字符串
        state: 狀態字典
        
    Returns:
        解析結果
    """
    expr = expr.strip()
    # index（循環序號，從 1 開始）
    if expr == "index":
        return (state.get("item") or {}).get("index")
    # item.xxx
    if expr.startswith("item."):
        item = state.get("item") or {}
        return get_by_path({"item": item}, "$." + expr)
    # current.xxx / current.card.xxx
    if expr.startswith("current."):
        cur = state.get("current") or {}
        return get_by_path({"current": cur}, "$." + expr)
    # scope.xxx
    if expr.startswith("scope."):
        scope = state.get("scope") or {}
        return get_by_path({"scope": scope}, "$." + expr)
    # $.content.xxx 針對當前 card
    if expr.startswith("$."):
        card = (state.get("current") or {}).get("card") or state.get("card")
        base = {"content": getattr(card, "content", {})} if card else {}
        return get_by_path({"$": base}, expr)
    return None


def to_name(x: Any) -> str:
    """將對象轉換爲名稱字符串
    
    Args:
        x: 任意對象
        
    Returns:
        名稱字符串
    """
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, dict):
        for key in ("name", "title", "label", "content"):
            v = x.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, dict):
                nn = v.get("name") or v.get("title")
                if isinstance(nn, str) and nn.strip():
                    return nn.strip()
    return str(x).strip()


def to_name_list(seq: Any) -> List[str]:
    """將序列轉換爲名稱列表（去重）
    
    Args:
        seq: 序列
        
    Returns:
        名稱列表
    """
    if not isinstance(seq, list):
        return []
    out: List[str] = []
    for it in seq:
        name = to_name(it)
        if name:
            out.append(name)
    # 去重保持順序
    seen = set()
    unique: List[str] = []
    for n in out:
        if n not in seen:
            unique.append(n)
            seen.add(n)
    return unique


def render_value(val: Any, state: dict) -> Any:
    """模板渲染
    
    - 字符串：{item.xxx} / {current.card.content.xxx} / {scope.xxx} / {index} / {$.content.xxx}
    - 對象：支持 {"$toNameList": "item.entity_list"} 快捷轉換
    - 列表/對象：遞歸渲染
    
    Args:
        val: 待渲染的值
        state: 狀態字典
        
    Returns:
        渲染後的值
    """
    if isinstance(val, dict):
        if "$toNameList" in val and isinstance(val.get("$toNameList"), str):
            seq = resolve_expr(val["$toNameList"], state)
            return to_name_list(seq)
        return {k: render_value(v, state) for k, v in val.items()}
    if isinstance(val, list):
        return [render_value(v, state) for v in val]
    if isinstance(val, str):
        # 單一表達式直接返回原類型
        m = _TPL_PATTERN.fullmatch(val.strip())
        if m:
            resolved = resolve_expr(m.group(1), state)
            return resolved
        # 內嵌模板，最終還是字符串
        def repl(match: re.Match) -> str:
            expr = match.group(1)
            res = resolve_expr(expr, state)
            if isinstance(res, (dict, list)):
                return str(res)
            return "" if res is None else str(res)
        return _TPL_PATTERN.sub(repl, val)
    return val


def get_from_state(path_expr: Any, state: dict) -> Any:
    """從狀態中獲取值
    
    兼容 path 字符串（$. / $item. / $current. / $scope. / item. / scope. / current.）或直接值
    
    Args:
        path_expr: 路徑表達式或直接值
        state: 狀態字典
        
    Returns:
        獲取的值
    """
    if isinstance(path_expr, str):
        p = path_expr.strip()
        if p in ("item", "$item"):
            return state.get("item")
        if p in ("current", "$current"):
            return state.get("current")
        if p in ("scope", "$scope"):
            return state.get("scope")
        # 統一映射到 resolve_expr 可識別形式
        if p.startswith("$item."):
            return resolve_expr("item." + p[len("$item."):], state)
        if p.startswith("$current."):
            return resolve_expr("current." + p[len("$current."):], state)
        if p.startswith("$scope."):
            return resolve_expr("scope." + p[len("$scope."):], state)
        if p.startswith(("item.", "current.", "scope.", "$.")):
            return resolve_expr(p, state)
    return path_expr
