"""動態模型構建服務

負責從 JSON Schema 動態構建 Pydantic 模型。
"""

from typing import Dict, Any, List, Type
from pydantic import create_model, Field as PydanticField, BaseModel
from typing import Any as _Any, Dict as _Dict, List as _List


def json_schema_to_py_type(sch: Dict[str, Any], schema_root: Dict[str, Any] = None) -> Any:
    """將 JSON Schema 類型轉換爲 Python 類型註解
    
    Args:
        sch: JSON Schema 定義
        schema_root: 根 Schema (用於解析 $ref)
        
    Returns:
        Python 類型註解或 Pydantic 模型類
    """
    if not isinstance(sch, dict):
        return _Any
    
    # 處理 $ref
    if '$ref' in sch:
        ref_path = sch['$ref']
        # 簡單的 $ref 解析: #/$defs/ModelName
        if ref_path.startswith('#/$defs/') and schema_root and '$defs' in schema_root:
            def_name = ref_path.split('/')[-1]
            ref_schema = schema_root['$defs'].get(def_name)
            if ref_schema:
                # 遞歸構建引用的模型
                # 使用引用名作爲模型名，避免哈希命名
                return build_model_from_json_schema(def_name, ref_schema, schema_root)
        
        # 解析失敗或無 definitions，回退到 Dict
        return _Dict[str, _Any]
    
    t = sch.get('type')
    
    if t == 'string':
        return str
    if t == 'integer':
        return int
    if t == 'number':
        return float
    if t == 'boolean':
        return bool
    if t == 'array':
        item_sch = sch.get('items') or {}
        return _List[json_schema_to_py_type(item_sch, schema_root)]  # type: ignore[index]
    if t == 'object':
        # **關鍵修復**: 如果有 properties,遞歸構建嵌套 Pydantic 模型
        if 'properties' in sch:
            # 生成唯一的嵌套模型名
            import hashlib
            schema_str = str(sorted(sch.get('properties', {}).keys()))
            model_hash = hashlib.md5(schema_str.encode()).hexdigest()[:8]
            nested_model_name = f'NestedModel_{model_hash}'
            return build_model_from_json_schema(nested_model_name, sch, schema_root)
        else:
            # 沒有 properties 的對象,按 Dict 處理
            return _Dict[str, _Any]
    
    # 未聲明 type 或無法識別
    return _Any


def build_model_from_json_schema(model_name: str, schema: Dict[str, Any], root_schema: Dict[str, Any] = None) -> Type[BaseModel]:
    """從 JSON Schema 動態構建 Pydantic 模型
    
    Args:
        model_name: 模型名稱
        schema: JSON Schema 定義
        root_schema: 根 Schema (用於解析 $ref)，默認爲 schema 自己
        
    Returns:
        動態創建的 Pydantic 模型類
    """
    if root_schema is None:
        root_schema = schema

    # 1. 如果當前 schema 本身就是一個 $ref，直接解析並返回引用模型
    if '$ref' in schema:
         return json_schema_to_py_type(schema, root_schema)

    props: Dict[str, Any] = (schema or {}).get('properties') or {}
    required: List[str] = list((schema or {}).get('required') or [])
    field_defs: Dict[str, tuple] = {}
    
    for fname, fsch in props.items():
        # 獲取類型註解 (可能是嵌套模型)
        # 傳入 root_schema 以便在深層嵌套中仍能找到 definitions
        anno = json_schema_to_py_type(fsch if isinstance(fsch, dict) else {}, root_schema)
        
        # 獲取描述
        desc = fsch.get('description') if isinstance(fsch, dict) else None
        
        # 判斷是否必填
        is_required = fname in required
        
        # 構建字段定義：必填用 ...，非必填用 None
        if desc is not None:
            default_val = PydanticField(... if is_required else None, description=desc)
        else:
            default_val = ... if is_required else None
        
        field_defs[fname] = (anno, default_val)
    
    return create_model(model_name, **field_defs)

