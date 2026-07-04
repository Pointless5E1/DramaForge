"""指令校驗工具

負責校驗指令的格式、路徑、類型和約束。
"""

import re
from typing import Dict, Any, Optional
from pydantic import ValidationError
from loguru import logger


_ARRAY_INDEX_PATTERN = re.compile(r"\[(\d+)\]")


def normalize_instruction_path(path: Any) -> str:
    """把常見路徑寫法統一轉換爲 JSON Pointer。"""
    if not isinstance(path, str):
        return ""

    normalized = path.strip()
    if not normalized:
        return ""

    if normalized == "$":
        return "/"
    if normalized.startswith("$."):
        normalized = normalized[2:]

    # items[0] -> items/0
    normalized = _ARRAY_INDEX_PATTERN.sub(r"/\1", normalized)
    # config.theme -> config/theme
    normalized = normalized.replace(".", "/")

    if not normalized.startswith("/"):
        normalized = "/" + normalized.lstrip("/")

    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    return normalized



def resolve_schema(schema: Dict[str, Any], root_schema: Dict[str, Any]) -> Dict[str, Any]:
    """解析 Schema 引用 ($ref) 和組合類型 (allOf)
    
    Args:
        schema: 當前 Schema 節點
        root_schema: 根 Schema (包含 $defs/definitions)
        
    Returns:
        解析後的 Schema
    """
    if not isinstance(schema, dict):
        return schema
        
    resolved = schema
    
    # 1. 處理 $ref
    if '$ref' in resolved:
        ref_path = resolved['$ref']
        # 支持 #/$defs/Name 和 #/definitions/Name
        if ref_path.startswith('#/'):
            parts = ref_path.split('/')
            # parts[0] is '#', parts[1] is '$defs' or 'definitions', parts[2] is model name
            if len(parts) >= 3:
                def_section = parts[1]
                model_name = parts[2]
                if def_section in root_schema and model_name in root_schema[def_section]:
                    # 遞歸解析（處理 Ref -> Ref 的情況）
                    return resolve_schema(root_schema[def_section][model_name], root_schema)
    
    # 2. 處理 allOf (合併屬性)
    if 'allOf' in resolved:
        merged = {}
        for sub_schema in resolved['allOf']:
            sub_resolved = resolve_schema(sub_schema, root_schema)
            if isinstance(sub_resolved, dict):
                # 簡單合併 properties
                if 'properties' in sub_resolved:
                    if 'properties' not in merged:
                        merged['properties'] = {}
                    merged['properties'].update(sub_resolved['properties'])
                # 合併 required
                if 'required' in sub_resolved:
                    if 'required' not in merged:
                        merged['required'] = []
                    merged['required'].extend(sub_resolved['required'])
                # 合併 type
                if 'type' in sub_resolved and 'type' not in merged:
                    merged['type'] = sub_resolved['type']
        
        # 將當前 schema 的其他屬性也合並進去
        for k, v in resolved.items():
            if k != 'allOf':
                if k == 'properties':
                    if 'properties' not in merged:
                        merged['properties'] = {}
                    merged['properties'].update(v)
                elif k == 'required':
                    if 'required' not in merged:
                        merged['required'] = []
                    new_reqs = [r for r in v if r not in merged['required']]
                    merged['required'].extend(new_reqs)
                else:
                    merged[k] = v
        return merged

    return resolved


def get_field_schema_by_path(schema: Dict[str, Any], path: str) -> Optional[Dict[str, Any]]:
    """根據 JSON Pointer 路徑獲取字段的 Schema
    
    Args:
        schema: 完整的 JSON Schema
        path: JSON Pointer 格式的路徑，如 /name 或 /config/theme
        
    Returns:
        字段的 Schema，如果路徑不存在則返回 None
    """
    path = normalize_instruction_path(path)
    if not path or not path.startswith('/'):
        return None
    
    # 移除開頭的 /
    path = path[1:]
    if not path:
        return schema
    
    # 分割路徑
    parts = path.split('/')
    current_schema = schema
    
    for part in parts:
        # 每一層都嘗試解析引用
        current_schema = resolve_schema(current_schema, schema)
        
        # 處理數組索引（如 hobbies/0）
        if part.isdigit():
            # 數組元素，獲取 items schema
            if 'items' in current_schema:
                current_schema = current_schema['items']
            elif 'prefixItems' in current_schema:
                 # 處理 tuple (prefixItems)
                 idx = int(part)
                 if idx < len(current_schema['prefixItems']):
                     current_schema = current_schema['prefixItems'][idx]
                 else:
                     return None
            else:
                # 嘗試處理 anyOf/oneOf 中的數組情況
                found_array = False
                for key in ['anyOf', 'oneOf']:
                    if key in current_schema:
                        for option in current_schema[key]:
                            resolved_option = resolve_schema(option, schema)
                            if resolved_option.get('type') == 'array' and 'items' in resolved_option:
                                current_schema = resolved_option['items']
                                found_array = True
                                break
                        if found_array:
                            break
                if not found_array:
                    return None
        else:
            # 對象屬性
            # 嘗試處理 properties
            if 'properties' in current_schema and part in current_schema['properties']:
                current_schema = current_schema['properties'][part]
            else:
                # 嘗試處理 anyOf/oneOf 中的對象情況 (如 Union[A, B])
                # 這是一個簡化的處理：只要在任意一個分支中找到該屬性，就認爲路徑從Schema角度是合法的
                # 並返回找到的那個屬性的 Schema。
                # 注意：這在校驗時可能不夠嚴格（因爲不知道運行時是 A 還是 B），
                # 但對於"路徑是否存在"的檢查，這是合理的寬容策略。
                found_prop = False
                for key in ['anyOf', 'oneOf']:
                    if key in current_schema:
                        for option in current_schema[key]:
                            resolved_option = resolve_schema(option, schema)
                            if 'properties' in resolved_option and part in resolved_option['properties']:
                                current_schema = resolved_option['properties'][part]
                                found_prop = True
                                break
                        if found_prop:
                            break
                
                if not found_prop:
                    return None
    
    # 返回前最後解析一次
    return resolve_schema(current_schema, schema)


def validate_type(value: Any, expected_type: Optional[str]) -> bool:
    """校驗值的類型是否匹配
    
    Args:
        value: 要校驗的值
        expected_type: 期望的類型（JSON Schema 類型）
        
    Returns:
        是否匹配
    """
    if expected_type is None:
        return True
    
    type_mapping = {
        'string': str,
        'integer': int,
        'number': (int, float),
        'boolean': bool,
        'array': list,
        'object': dict,
        'null': type(None)
    }
    
    expected_python_type = type_mapping.get(expected_type)
    if expected_python_type is None:
        # 未知類型，寬容處理
        return True
    
    return isinstance(value, expected_python_type)


def _resolve_schema_variant_by_type(
    schema_node: Dict[str, Any],
    root_schema: Dict[str, Any],
    target_type: str,
) -> Optional[Dict[str, Any]]:
    """在 nullable/union schema 中選出目標類型分支。"""
    resolved = resolve_schema(schema_node, root_schema)
    if resolved.get('type') == target_type:
        return resolved

    for union_key in ('anyOf', 'oneOf'):
        options = resolved.get(union_key)
        if not isinstance(options, list):
            continue
        for option in options:
            resolved_option = resolve_schema(option, root_schema)
            if resolved_option.get('type') == target_type:
                return resolved_option
    return None


def _validate_constraints(value: Any, schema_node: Dict[str, Any], path: str) -> None:
    """校驗 enum、長度、數值範圍等約束。"""
    expected_type = schema_node.get('type')

    if 'enum' in schema_node and value not in schema_node['enum']:
        raise ValueError(f"字段 {path} 的值不在枚舉範圍內：{schema_node['enum']}")

    if expected_type in ['integer', 'number']:
        if 'minimum' in schema_node and value < schema_node['minimum']:
            raise ValueError(f"字段 {path} 的值 {value} 小於最小值 {schema_node['minimum']}")
        if 'maximum' in schema_node and value > schema_node['maximum']:
            raise ValueError(f"字段 {path} 的值 {value} 大於最大值 {schema_node['maximum']}")

    if expected_type == 'string':
        if 'minLength' in schema_node and len(value) < schema_node['minLength']:
            raise ValueError(f"字段 {path} 的長度 {len(value)} 小於最小長度 {schema_node['minLength']}")
        if 'maxLength' in schema_node and len(value) > schema_node['maxLength']:
            raise ValueError(f"字段 {path} 的長度 {len(value)} 大於最大長度 {schema_node['maxLength']}")

    if expected_type == 'array' and isinstance(value, list):
        if 'minItems' in schema_node and len(value) < schema_node['minItems']:
            raise ValueError(f"數組 {path} 的長度 {len(value)} 小於最小長度 {schema_node['minItems']}")
        if 'maxItems' in schema_node and len(value) > schema_node['maxItems']:
            raise ValueError(f"數組 {path} 的長度 {len(value)} 大於最大長度 {schema_node['maxItems']}")


def validate_value_against_schema(
    value: Any,
    schema_node: Dict[str, Any],
    root_schema: Dict[str, Any],
    path: str,
) -> None:
    """按單個 schema 節點遞歸校驗一個值。"""
    resolved = resolve_schema(schema_node, root_schema)

    for union_key in ('anyOf', 'oneOf'):
        options = resolved.get(union_key)
        if not isinstance(options, list):
            continue

        matched = False
        last_error: Optional[ValueError] = None
        for option in options:
            resolved_option = resolve_schema(option, root_schema)
            opt_type = resolved_option.get('type')
            if not validate_type(value, opt_type):
                continue
            try:
                validate_value_against_schema(value, resolved_option, root_schema, path)
                matched = True
                break
            except ValueError as exc:
                last_error = exc

        if not matched:
            if last_error:
                raise last_error
            allowed_types = [resolve_schema(opt, root_schema).get('type') for opt in options]
            raise ValueError(
                f"字段類型或結構錯誤：路徑 {path}，期望 {allowed_types} 之一。實際: {type(value).__name__}"
            )
        return

    expected_type = resolved.get('type')
    if expected_type and not validate_type(value, expected_type):
        raise ValueError(f"字段類型錯誤：路徑 {path}，期望 {expected_type}，實際 {type(value).__name__}")

    _validate_constraints(value, resolved, path)

    if expected_type == 'object':
        validate_schema_structure(value, resolved, root_schema, path)
        return

    if expected_type == 'array' and isinstance(value, list):
        if isinstance(resolved.get('prefixItems'), list):
            for idx, item_schema in enumerate(resolved['prefixItems']):
                if idx >= len(value):
                    break
                validate_value_against_schema(value[idx], item_schema, root_schema, f"{path}/{idx}")
            return

        item_schema = resolved.get('items')
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                validate_value_against_schema(item, item_schema, root_schema, f"{path}/{idx}")


def validate_instruction(instruction: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """校驗單條指令的合法性
    
    Args:
        instruction: 指令對象
        schema: 完整的 JSON Schema
        
    Raises:
        ValueError: 校驗失敗時拋出異常
    """
    op = instruction.get('op')
    
    if op not in ['set', 'append', 'done']:
        raise ValueError(f"未知的指令操作類型: {op}")
    
    if op == 'done':
        # done 指令無需校驗
        return
    
    path = instruction.get('path')
    value = instruction.get('value')
    
    if not path:
        raise ValueError("指令缺少 path 字段")

    # 兼容模型偶爾輸出的裸路徑、點路徑，統一轉成 JSON Pointer 再校驗。
    path = normalize_instruction_path(path)
    instruction['path'] = path
    
    if value is None and op != 'set':
        raise ValueError(f"指令 {op} 缺少 value 字段")
    
    # 1. 路徑校驗
    field_schema = get_field_schema_by_path(schema, path)
    if not field_schema:
        raise ValueError(f"路徑 {path} 不存在於 Schema 中")
    
    # 對於 append 操作，需要檢查數組的 items 類型
    if op == 'append':
        actual_schema = _resolve_schema_variant_by_type(field_schema, schema, 'array')
        if not actual_schema:
            raise ValueError(f"路徑 {path} 不是數組類型，無法使用 append 操作")
        items_schema = actual_schema.get('items')
        if not isinstance(items_schema, dict):
            raise ValueError(f"路徑 {path} 的數組未定義 items 結構，無法使用 append 操作")
        validate_value_against_schema(value, items_schema, schema, f"{path}/-")

    else:
        validate_value_against_schema(value, field_schema, schema, path)

def validate_schema_structure(
    data: Any,
    schema_node: Dict[str, Any],
    root_schema: Dict[str, Any],
    path: str = "",
) -> None:
    """遞歸校驗數據的結構是否符合 Schema 定義 (包含 required 和 properties)
    
    Args:
        data: 要校驗的數據
        schema_node: 當前數據的 Schema 節點
        root_schema: 根 Schema (用於解析 $ref)
    
    Raises:
        ValueError: 校驗失敗
    """
    if not isinstance(data, dict):
        return
        
    resolved = resolve_schema(schema_node, root_schema)
    
    # 1. 遍歷 Schema 屬性，處理 校驗必填 + 注入默認值 + 遞歸校驗
    if 'properties' in resolved:
        properties = resolved['properties']
        required_fields = set(resolved.get('required', []))
        
        # 爲了支持注入默認值，我們需要遍歷 Schema 的 properties 而不僅僅是 data 的 keys
        # 但要注意：如果 Schema 很大但 Data 很小，這可能有效率問題。
        # 鑑於這是生成過程，通常數據結構不會太大，且爲了完整性，遍歷 Schema 是合理的。
        
        for field_name, field_schema_ref in properties.items():
            field_schema = resolve_schema(field_schema_ref, root_schema)
            
            # A. 處理缺失字段
            if field_name not in data:
                # 如果有默認值，注入默認值
                if 'default' in field_schema:
                    data[field_name] = field_schema['default']
                # 如果沒默認值 且 是必填項，報錯
                elif field_name in required_fields:
                    raise ValueError(f"缺少必填字段: {field_name}")
                # 既沒默認值也不是必填，跳過
                continue
            
            field_path = f"{path}/{field_name}" if path else f"/{field_name}"

            # B. 處理已存在字段
            field_value = data[field_name]

            validate_value_against_schema(field_value, field_schema, root_schema, field_path)
    
    # 2. (可選) 檢查 data 中有多餘的字段? (additionalProperties)
    # 目前暫不嚴格限制，允許 AI 生成額外字段作爲"思考備註"或未定義屬性


def apply_instruction(data: Dict[str, Any], instruction: Dict[str, Any]) -> None:
    """將指令應用到數據對象
    
    Args:
        data: 數據對象（會被修改）
        instruction: 指令對象
    """
    op = instruction.get('op')
    
    if op == 'done':
        return
    
    path = normalize_instruction_path(instruction.get('path', ''))
    value = instruction.get('value')
    
    # 移除開頭的 /
    if path.startswith('/'):
        path = path[1:]
    
    if not path:
        return
    
    # 分割路徑
    parts = path.split('/')
    current = data
    
    # 遍歷路徑，創建中間對象
    for i, part in enumerate(parts[:-1]):
        if part.isdigit():
            # 數組索引
            idx = int(part)
            if not isinstance(current, list):
                logger.warning(f"路徑 {path} 中的 {part} 應該是數組索引，但當前對象不是數組")
                return
            
            # 確保數組足夠長
            while len(current) <= idx:
                current.append({})
            
            current = current[idx]
        else:
            # 對象屬性
            if part not in current:
                # 判斷下一個部分是否是數組索引
                next_part = parts[i + 1] if i + 1 < len(parts) else None
                if next_part and next_part.isdigit():
                    current[part] = []
                else:
                    current[part] = {}
            
            current = current[part]
    
    # 設置最後一個字段
    last_part = parts[-1]
    
    if op == 'set':
        if last_part.isdigit():
            idx = int(last_part)
            if isinstance(current, list):
                while len(current) <= idx:
                    current.append(None)
                current[idx] = value
        else:
            current[last_part] = value
    
    elif op == 'append':
        if last_part.isdigit():
            logger.warning(f"append 操作不應該使用數組索引路徑: {path}")
            return
        
        # 初始化數組（如果不存在或爲 None）
        if last_part not in current or current[last_part] is None:
            current[last_part] = []
        
        if not isinstance(current[last_part], list):
            logger.warning(f"路徑 {path} 不是數組，無法執行 append 操作")
            return
        
        current[last_part].append(value)


def format_validation_errors(errors: list) -> str:
    """格式化 Pydantic 驗證錯誤
    
    Args:
        errors: Pydantic 驗證錯誤列表
        
    Returns:
        格式化的錯誤信息
    """
    lines = []
    for error in errors:
        loc = ' -> '.join(str(l) for l in error.get('loc', []))
        msg = error.get('msg', '未知錯誤')
        lines.append(f"- {loc}: {msg}")
    
    return '\n'.join(lines)


def extract_error_fields(validation_error: ValidationError) -> list[str]:
    """從 Pydantic 驗證錯誤中提取錯誤字段列表
    
    Args:
        validation_error: Pydantic 驗證錯誤
        
    Returns:
        錯誤字段路徑列表
    """
    fields = []
    for error in validation_error.errors():
        loc = error.get('loc', ())
        if loc:
            # 轉換爲 JSON Pointer 格式
            path = '/' + '/'.join(str(l) for l in loc)
            fields.append(path)
    
    return fields


class InstructionExecutor:
    """指令執行器
    
    封裝指令的批量執行、驗證和數據管理邏輯。
    用於統一 AI 卡片生成和靈感助手工具的指令執行。
    """
    
    def __init__(self, schema: Dict[str, Any], initial_data: Optional[Dict[str, Any]] = None):
        """
        初始化執行器
        
        Args:
            schema: JSON Schema
            initial_data: 初始數據（可選）
        """
        self.schema = schema
        self.data = initial_data.copy() if initial_data else {}
        self.stats = {
            "executed": 0,
            "success": 0,
            "failed": 0
        }
    
    def execute(self, instruction: Dict[str, Any]) -> None:
        """
        執行單條指令
        
        Args:
            instruction: 指令對象
            
        Raises:
            ValueError: 指令校驗或執行失敗
        """
        self.stats["executed"] += 1
        
        try:
            # 校驗指令
            validate_instruction(instruction, self.schema)
            
            # 應用指令
            apply_instruction(self.data, instruction)
            
            self.stats["success"] += 1
            
        except Exception as e:
            self.stats["failed"] += 1
            raise
    
    def execute_batch(self, instructions: list[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量執行指令
        
        Args:
            instructions: 指令數組
            
        Returns:
            執行結果：
            {
                "success": bool - 是否完整成功（所有指令執行且數據完整）
                "data": dict - 當前數據
                "applied": int - 成功執行的指令數
                "failed": int - 失敗的指令數
                "errors": list - 失敗的指令詳情
                "is_complete": bool - 數據是否完整
                "missing_fields": list - 缺失的必填字段
            }
        """
        failed_instructions = []
        
        for idx, inst in enumerate(instructions):
            try:
                self.execute(inst)
            except Exception as e:
                failed_instructions.append({
                    "index": idx,
                    "instruction": inst,
                    "error": str(e)
                })
                logger.warning(f"[InstructionExecutor] 指令執行失敗: {e}")
        
        # 驗證數據完整性
        is_complete, missing_fields = self.validate_completeness()
        
        return {
            "success": is_complete and len(failed_instructions) == 0,
            "data": self.data,
            "applied": self.stats["success"],
            "failed": self.stats["failed"],
            "errors": failed_instructions,
            "is_complete": is_complete,
            "missing_fields": missing_fields
        }
    
    def validate_completeness(self) -> tuple[bool, list[str]]:
        """
        驗證數據完整性
        
        Returns:
            (is_complete, missing_fields):
            - is_complete: 是否完整
            - missing_fields: 缺失的必填字段路徑列表
        """
        from app.services.ai.core.model_builder import build_model_from_json_schema
        
        try:
            # 使用 Pydantic 動態模型驗證
            DynamicModel = build_model_from_json_schema('ValidationModel', self.schema)
            DynamicModel(**self.data)
            return True, []
        except ValidationError as e:
            # 提取缺失字段
            missing_fields = []
            for error in e.errors():
                if error.get('type') == 'missing':
                    loc = error.get('loc', ())
                    if loc:
                        path = '/' + '/'.join(str(l) for l in loc)
                        missing_fields.append(path)
            
            return False, missing_fields
    
    def get_data(self) -> Dict[str, Any]:
        """獲取當前數據"""
        return self.data
    
    def get_stats(self) -> Dict[str, int]:
        """獲取執行統計"""
        return self.stats.copy()
