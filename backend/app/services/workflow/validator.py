"""工作流代碼校驗器

在工作流保存時進行靜態檢查，提前發現錯誤。
"""

import ast
import re
from typing import List, Dict, Any, Optional, Iterable, Tuple, Set
from dataclasses import dataclass
from loguru import logger
from sqlmodel import Session, select

try:
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover - optional dependency fallback
    Draft202012Validator = None

from .registry import NodeRegistry
from .expressions import validate_expression
from .expressions.evaluator import get_expression_dependencies


_IMPLICIT_REF_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+$")
_BRACED_REF_PATTERN = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\}(?!\})")
_EXPR_LITERAL_VAR_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+")
_EXPR_LITERAL_FUNC_PATTERN = re.compile(r"\b(str|int|float|len|sum|min|max|sorted|join)\s*\(")


@dataclass
class ValidationError:
    """校驗錯誤"""
    line: int
    variable: str
    error_type: str  # 'syntax', 'node_type', 'field_access', 'expression', 'type_mismatch'
    message: str
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """校驗結果"""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換爲字典"""
        return {
            'is_valid': self.is_valid,
            'errors': [
                {
                    'line': e.line,
                    'variable': e.variable,
                    'error_type': e.error_type,
                    'message': e.message,
                    'suggestion': e.suggestion
                }
                for e in self.errors
            ],
            'warnings': [
                {
                    'line': w.line,
                    'variable': w.variable,
                    'error_type': w.error_type,
                    'message': w.message,
                    'suggestion': w.suggestion
                }
                for w in self.warnings
            ]
        }


class WorkflowValidator:
    """工作流校驗器"""
    
    def __init__(self, session: Optional[Session] = None):
        self.registry = NodeRegistry()
        self.session = session
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        self._card_schema_by_name: Optional[Dict[str, Dict[str, Any]]] = None
        self._var_to_node_type: Dict[str, str] = {}
        self._var_to_output_schema: Dict[str, Dict[str, Any]] = {}
        self._var_to_output_contract: Dict[str, Dict[str, Any]] = {}
    
    def validate(self, code: str) -> ValidationResult:
        """校驗工作流代碼
        
        Args:
            code: 工作流 DSL 代碼（註釋標記 DSL）
            
        Returns:
            校驗結果
        """
        self.errors = []
        self.warnings = []
        
        try:
            # 解析代碼
            from .parser.marker_parser import WorkflowParser
            parser = WorkflowParser()
            
            # 1. 解析代碼（會檢查語法錯誤）
            plan = parser.parse(code)
            
            # 2. 檢查節點類型
            self._validate_node_types(plan.statements)
            
            # 3. 檢查字段訪問
            self._validate_field_access(plan.statements)
            
            # 4. 檢查表達式語法
            self._validate_expressions(plan.statements)
            
            # 5. 檢查類型匹配
            self._validate_type_matching(plan.statements)
            
            # 6. 檢查 Expression 節點特殊規則
            self._validate_expression_nodes(plan.statements)
            
            # 7. 檢查異步依賴
            self._validate_async_dependencies(plan.statements)
            
            # 8. 檢查參數值的有效性
            self._validate_parameter_values(plan.statements)
            
        except SyntaxError as e:
            self.errors.append(ValidationError(
                line=e.lineno or 0,
                variable='',
                error_type='syntax',
                message=f"語法錯誤: {str(e)}",
                suggestion="檢查代碼語法是否正確"
            ))
        except ValueError as e:
            # 解析器拋出的錯誤
            self.errors.append(ValidationError(
                line=0,
                variable='',
                error_type='syntax',
                message=str(e),
                suggestion="檢查代碼是否符合 DSL 規範"
            ))
        except Exception as e:
            logger.error(f"校驗失敗: {e}")
            self.errors.append(ValidationError(
                line=0,
                variable='',
                error_type='unknown',
                message=f"校驗失敗: {str(e)}",
                suggestion="請聯繫開發人員"
            ))
        
        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings
        )
    
    def _validate_node_types(self, statements):
        """檢查節點類型是否存在"""
        for stmt in statements:
            if stmt.node_type and not self.registry.has_node(stmt.node_type):
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='node_type',
                    message=f"未知的節點類型: {stmt.node_type}",
                    suggestion=f"可用的節點類型: {', '.join(self.registry.list_nodes())}"
                ))
    
    def _validate_field_access(self, statements):
        """檢查字段訪問是否合法"""
        # 構建變量 -> 節點類型 / 輸出 schema 映射
        var_to_node_type: Dict[str, str] = {}
        var_to_output_schema: Dict[str, Dict[str, Any]] = {}

        for stmt in statements:
            if not stmt.node_type:
                continue

            var_to_node_type[stmt.variable] = stmt.node_type

            node_class = self.registry.get(stmt.node_type)
            if node_class and hasattr(node_class, 'output_model'):
                try:
                    var_to_output_schema[stmt.variable] = node_class.output_model.model_json_schema()
                except Exception:
                    pass

        defined_vars = set(var_to_node_type.keys())

        for stmt in statements:
            for source, ref in self._extract_field_references(stmt.config, defined_vars):
                self._check_field_reference(
                    stmt=stmt,
                    ref=ref,
                    var_to_node_type=var_to_node_type,
                    var_to_output_schema=var_to_output_schema,
                    source=source,
                )

    def _extract_field_references(
        self,
        value: Any,
        defined_vars: set[str],
        path: str = "config",
    ) -> Iterable[Tuple[str, str]]:
        """遞歸提取配置中的變量字段引用。

        支持：
        - $var.field
        - var.field（僅當 var 爲已定義變量時，視作隱式引用）
        """
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return

            if text.startswith("${") and text.endswith("}"):
                return

            if text.startswith("$"):
                yield path, text[1:]
                return

            if _IMPLICIT_REF_PATTERN.match(text):
                root = text.split('.', 1)[0]
                if root in defined_vars:
                    yield path, text

            # 支持在字符串模板中提取內嵌字段引用（如 f"...{debate.summary}..."）
            # 僅提取 `{var.field}`，並跳過雙大括號 `{{...}}` 場景。
            for match in _BRACED_REF_PATTERN.finditer(text):
                ref = (match.group(1) or "").strip()
                if not ref:
                    continue
                root = ref.split('.', 1)[0]
                if root in defined_vars:
                    yield path, ref
            return

        if isinstance(value, list):
            for idx, item in enumerate(value):
                child_path = f"{path}[{idx}]"
                yield from self._extract_field_references(item, defined_vars, child_path)
            return

        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                yield from self._extract_field_references(item, defined_vars, child_path)

    def _check_field_reference(
        self,
        stmt,
        ref: str,
        var_to_node_type: Dict[str, str],
        var_to_output_schema: Dict[str, Dict[str, Any]],
        source: str,
    ):
        """檢查字段引用是否合法"""
        parts = ref.split('.')
        if len(parts) < 2:
            return  # 簡單變量引用，不檢查
        
        var_name = parts[0]
        field_name = parts[1]
        
        # 檢查變量是否存在
        if var_name not in var_to_node_type:
            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='field_access',
                message=f"字段引用來源 {source} 使用了未定義變量: {var_name}",
                suggestion=f"確保在使用前定義變量 {var_name}"
            ))
            return
        
        # 獲取節點類型與輸出 schema
        node_type = var_to_node_type[var_name]
        output_schema = var_to_output_schema.get(var_name)

        if not output_schema:
            return  # 無法檢查

        # 檢查字段路徑是否存在
        exists, available_fields = self._validate_schema_field_path(output_schema, parts[1:])
        if not exists:
            field_path = ".".join(parts[1:])
            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='field_access',
                message=f"節點 {var_name} ({node_type}) 沒有輸出字段路徑 '{field_path}'（來源: {source}）",
                suggestion=(
                    f"可用字段: {', '.join(available_fields)}"
                    if available_fields
                    else "請檢查字段路徑拼寫，或先用 wf_get_node_metadata 查看節點輸出 schema"
                )
            ))

    def _validate_schema_field_path(
        self,
        root_schema: Dict[str, Any],
        path_parts: List[str],
    ) -> Tuple[bool, List[str]]:
        """校驗輸出 schema 字段路徑是否存在。"""
        if not path_parts:
            return True, []

        current_candidates: List[Dict[str, Any]] = [root_schema]

        for part in path_parts:
            next_candidates: List[Dict[str, Any]] = []
            available_fields: set[str] = set()

            for candidate in current_candidates:
                normalized = self._resolve_schema_refs(candidate, root_schema)
                options = self._expand_schema_options(normalized)

                for option in options:
                    option = self._resolve_schema_refs(option, root_schema)
                    if self._schema_allows_dynamic_field_path(option, root_schema):
                        return True, []
                    properties = option.get('properties') if isinstance(option, dict) else None

                    if isinstance(properties, dict):
                        available_fields.update(properties.keys())
                        child = properties.get(part)
                        if isinstance(child, dict):
                            next_candidates.append(child)
                            continue

                    additional = option.get('additionalProperties') if isinstance(option, dict) else None
                    if isinstance(additional, dict):
                        next_candidates.append(additional)
                        continue
                    if additional is True:
                        return True, []

                    item_schema = option.get('items') if isinstance(option, dict) else None
                    if isinstance(item_schema, dict) and part.isdigit():
                        next_candidates.append(item_schema)

            if not next_candidates:
                return False, sorted(available_fields)

            current_candidates = next_candidates

        return True, []

    def _schema_allows_dynamic_field_path(
        self,
        schema: Dict[str, Any],
        root_schema: Dict[str, Any],
    ) -> bool:
        """判斷 schema 是否允許繼續向下訪問任意字段路徑。

        典型場景：
        - `Any`（Pydantic 會生成近似 `{}`）
        - `type=object` 且未約束 properties / additionalProperties
        - `additionalProperties=true`
        """
        if not isinstance(schema, dict):
            return False

        normalized = self._resolve_schema_refs(schema, root_schema)
        if not isinstance(normalized, dict):
            return False

        additional = normalized.get("additionalProperties")
        if additional is True:
            return True

        properties = normalized.get("properties")
        has_properties = isinstance(properties, dict) and bool(properties)
        has_items = (
            isinstance(normalized.get("items"), dict)
            or isinstance(normalized.get("prefixItems"), list)
        )
        schema_type = normalized.get("type")

        if schema_type == "object" and not has_properties and "additionalProperties" not in normalized:
            return True

        # `Any` / 無約束 schema
        structural_keys = (
            "type",
            "properties",
            "items",
            "prefixItems",
            "additionalProperties",
            "anyOf",
            "oneOf",
            "allOf",
            "$ref",
        )
        if not any(key in normalized for key in structural_keys):
            return True

        if schema_type == "array" and not has_items and "items" not in normalized and "prefixItems" not in normalized:
            return True

        return False

    def _resolve_schema_refs(self, schema: Dict[str, Any], root_schema: Dict[str, Any]) -> Dict[str, Any]:
        """解析 schema 中的本地 $ref（#/$defs/xxx）。"""
        if not isinstance(schema, dict):
            return {}

        ref = schema.get('$ref')
        if not isinstance(ref, str) or not ref.startswith('#/$defs/'):
            return schema

        ref_name = ref.split('/')[-1]
        defs = root_schema.get('$defs') if isinstance(root_schema, dict) else None
        if isinstance(defs, dict) and isinstance(defs.get(ref_name), dict):
            return defs[ref_name]
        return schema

    def _expand_schema_options(self, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """展開 anyOf/oneOf/allOf 便於路徑檢查。"""
        if not isinstance(schema, dict):
            return []

        options: List[Dict[str, Any]] = [schema]
        expanded = False
        for key in ('anyOf', 'oneOf', 'allOf'):
            variants = schema.get(key)
            if isinstance(variants, list) and variants:
                options = [item for item in variants if isinstance(item, dict)]
                expanded = True
                break

        if not expanded:
            return [schema]

        # 過濾掉 null 分支，優先保留對象/可展開分支
        filtered = [
            item for item in options
            if item.get('type') != 'null'
        ]
        return filtered or options
    
    def _validate_expressions(self, statements):
        """檢查表達式語法與變量依賴"""
        var_to_node_type: Dict[str, str] = {}
        var_to_output_schema: Dict[str, Dict[str, Any]] = {}

        for stmt in statements:
            if not stmt.node_type:
                continue
            var_to_node_type[stmt.variable] = stmt.node_type

            node_class = self.registry.get(stmt.node_type)
            if node_class and hasattr(node_class, 'output_model'):
                try:
                    var_to_output_schema[stmt.variable] = node_class.output_model.model_json_schema()
                except Exception:
                    pass

        defined_vars = set()

        for stmt in statements:
            # 1) Logic.Expression 節點 expression 參數
            if stmt.node_type == "Logic.Expression":
                expression = stmt.config.get('expression', '')
                if expression:
                    self._validate_single_expression(
                        stmt=stmt,
                        expression=expression,
                        source="expression",
                        defined_vars=defined_vars,
                        var_to_node_type=var_to_node_type,
                        var_to_output_schema=var_to_output_schema,
                    )

            # 2) 通用內聯表達式：${...}
            for source, inline_expr in self._extract_inline_expressions(stmt.config):
                self._validate_single_expression(
                    stmt=stmt,
                    expression=inline_expr,
                    source=source,
                    defined_vars=defined_vars,
                    var_to_node_type=var_to_node_type,
                    var_to_output_schema=var_to_output_schema,
                )

            # 當前節點定義的變量在本語句結束後可用
            defined_vars.add(stmt.variable)

    def _validate_single_expression(
        self,
        stmt,
        expression: str,
        source: str,
        defined_vars: set[str],
        var_to_node_type: Optional[Dict[str, str]] = None,
        var_to_output_schema: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """校驗單個表達式"""
        expression_errors = validate_expression(expression)
        if expression_errors:
            for expression_error in expression_errors:
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='expression',
                    message=f"表達式語法錯誤 ({source}): {expression_error}",
                    suggestion="檢查表達式語法是否正確"
                ))
            return

        dependencies = get_expression_dependencies(expression)
        undefined_vars = sorted(var for var in dependencies if var not in defined_vars)
        if undefined_vars:
            defined_preview = ", ".join(sorted(defined_vars)) if defined_vars else "（當前無可用變量）"
            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='expression',
                message=f"表達式引用了未定義變量 ({source}): {', '.join(undefined_vars)}",
                suggestion=f"請先定義這些變量，或檢查變量名拼寫。當前可用變量: {defined_preview}"
            ))

        if not var_to_node_type or not var_to_output_schema:
            return

        for ref in self._extract_expression_field_references(expression, defined_vars):
            self._check_field_reference(
                stmt=stmt,
                ref=ref,
                var_to_node_type=var_to_node_type,
                var_to_output_schema=var_to_output_schema,
                source=source,
            )

    def _extract_expression_field_references(self, expression: str, defined_vars: set[str]) -> List[str]:
        """提取表達式中的字段引用，如 debate.summary / project.project_id。"""
        if not expression:
            return []

        try:
            expr_node = ast.parse(expression, mode="eval")
        except Exception:
            return []

        refs: set[str] = set()
        for node in ast.walk(expr_node):
            if not isinstance(node, ast.Attribute):
                continue
            ref = self._attribute_to_ref(node)
            if not ref or "." not in ref:
                continue
            root = ref.split('.', 1)[0]
            if root in defined_vars:
                refs.add(ref)

        return sorted(refs)

    def _extract_inline_expressions(
        self,
        value: Any,
        path: str = ""
    ) -> Iterable[Tuple[str, str]]:
        """遞歸提取配置中的內聯表達式 ${...}"""
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                source = path if path else "config"
                yield source, value[2:-1]
            return

        if isinstance(value, list):
            for index, item in enumerate(value):
                child_path = f"{path}[{index}]" if path else f"[{index}]"
                yield from self._extract_inline_expressions(item, child_path)
            return

        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                yield from self._extract_inline_expressions(item, child_path)
    
    def _validate_type_matching(self, statements):
        """檢查類型匹配（支持表達式與變量引用的靜態推斷）"""
        var_to_output_schema: Dict[str, Dict[str, Any]] = {}
        defined_vars = {stmt.variable for stmt in statements}
        self._var_to_node_type = {
            stmt.variable: stmt.node_type
            for stmt in statements
            if stmt.node_type
        }

        for stmt in statements:
            if not stmt.node_type:
                continue

            node_class = self.registry.get(stmt.node_type)
            if not node_class:
                continue

            try:
                contract = node_class.get_output_schema_contract(
                    stmt.config,
                    session=self.session,
                )
                if isinstance(contract, dict) and contract:
                    self._var_to_output_contract[stmt.variable] = contract
            except Exception:
                pass

            if not hasattr(node_class, 'output_model'):
                continue

            try:
                var_to_output_schema[stmt.variable] = node_class.output_model.model_json_schema()
            except Exception:
                continue

        self._var_to_output_schema = var_to_output_schema

        for stmt in statements:
            if not stmt.node_type:
                continue

            node_class = self.registry.get(stmt.node_type)
            if not node_class or not hasattr(node_class, 'input_model'):
                continue

            input_schema = node_class.input_model.model_json_schema()

            required_fields = input_schema.get('required', [])
            for field in required_fields:
                if field not in stmt.config:
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='type_mismatch',
                        message=f"缺少必填參數: {field}",
                        suggestion=f"節點 {stmt.node_type} 需要參數 {field}"
                    ))

            properties = input_schema.get('properties', {})
            for key, value in stmt.config.items():
                if key not in properties:
                    continue

                if self._is_card_payload_param(stmt.node_type, key):
                    if stmt.node_type in ("Card.Create", "Card.BatchUpsert") and self._card_content_reference_matches_contract(stmt, key):
                        continue
                    continue

                prop_schema = properties[key]
                expected_types = self._extract_expected_types(prop_schema, input_schema)
                if not expected_types:
                    continue

                actual_types = self._infer_value_static_types(
                    value=value,
                    defined_vars=defined_vars,
                    var_to_output_schema=var_to_output_schema,
                )
                if not actual_types:
                    continue

                if self._types_compatible(expected_types, actual_types):
                    continue

                self.errors.append(
                    self._build_type_mismatch_error(
                        stmt=stmt,
                        key=key,
                        expected_types=expected_types,
                        actual_types=actual_types,
                    )
                )

    def _is_card_payload_param(self, node_type: str, key: str) -> bool:
        return (
            (node_type == "Card.Create" and key == "content")
            or (node_type == "Card.Update" and key == "content_merge")
            or (node_type == "Card.BatchUpsert" and key == "content_template")
        )

    def _format_type_names(self, types: Set[str]) -> str:
        mapping = {
            "object": "dict(object)",
            "array": "list(array)",
            "string": "string",
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
            "null": "null",
            "any": "any",
        }
        labels = [mapping.get(item, item) for item in sorted(types)]
        return " / ".join(labels)

    def _build_type_mismatch_error(
        self,
        stmt,
        key: str,
        expected_types: Set[str],
        actual_types: Set[str],
    ) -> ValidationError:
        expected_text = self._format_type_names(expected_types)
        actual_text = self._format_type_names(actual_types)

        if self._is_card_payload_param(stmt.node_type, key):
            node_param = f"{stmt.node_type}.{key}"
            card_type_hint = ""
            if stmt.node_type in ("Card.Create", "Card.BatchUpsert"):
                card_type_name = stmt.config.get("card_type")
                if isinstance(card_type_name, str) and card_type_name.strip():
                    schema_fields = self._get_card_schema_fields_preview(card_type_name.strip())
                    if schema_fields:
                        card_type_hint = f" 可用字段示例：{', '.join(schema_fields)}。"

            return ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='type_mismatch',
                message=(
                    f"{node_param} 類型不匹配：必須是 dict(object)，"
                    f"當前檢測爲 {actual_text}"
                ),
                suggestion=(
                    f"請把 {node_param} 改爲字面量字典，並嚴格按卡片 schema 填寫字段。"
                    f"禁止用 `${{表達式}}` 或 `Logic.Expression.result` 直接賦整個內容對象。"
                    f"{card_type_hint}"
                )
            )

        return ValidationError(
            line=stmt.line_number,
            variable=stmt.variable,
            error_type='type_mismatch',
            message=f"參數 {key} 類型不匹配：期望 {expected_text}，實際推斷爲 {actual_text}",
            suggestion=f"請將參數 {key} 改爲 {expected_text}。"
        )

    def _extract_reference(self, value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        if text.startswith("$"):
            return text[1:].strip() or None
        if _IMPLICIT_REF_PATTERN.match(text):
            return text
        return None

    def _resolve_contract_from_reference(self, ref: str) -> Optional[Dict[str, Any]]:
        if not ref:
            return None

        parts = ref.split(".")
        if not parts:
            return None
        var_name = parts[0]
        contract = self._var_to_output_contract.get(var_name)
        if not contract:
            return None

        data_path = contract.get("data_path")
        if not isinstance(data_path, str) or not data_path:
            return None

        ref_path = ".".join(parts[1:])
        if ref_path == data_path:
            return contract
        return None

    def _normalize_schema_id(self, schema_id: Any) -> Optional[str]:
        if not isinstance(schema_id, str):
            return None
        text = schema_id.strip()
        return text or None

    def _card_content_reference_matches_contract(
        self,
        stmt,
        field_name: str,
    ) -> bool:
        value = stmt.config.get(field_name)
        ref = self._extract_reference(value)
        if not ref:
            return False

        contract = self._resolve_contract_from_reference(ref)
        if not contract:
            return False

        contract_schema_id = self._normalize_schema_id(contract.get("schema_id"))
        if not contract_schema_id:
            return False

        target_card_type = stmt.config.get("card_type")
        if not isinstance(target_card_type, str) or not target_card_type.strip():
            return False

        target_card_type = target_card_type.strip()
        if contract_schema_id == target_card_type:
            return True

        schema = self._get_card_content_schema(target_card_type)
        if not schema:
            return False

        title = schema.get("title") if isinstance(schema, dict) else None
        if isinstance(title, str) and title.strip() and title.strip() == contract_schema_id:
            return True

        return False

    def _get_card_schema_fields_preview(self, card_type_name: str) -> List[str]:
        schema = self._get_card_content_schema(card_type_name)
        if not isinstance(schema, dict):
            return []
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return []
        return sorted(list(properties.keys()))[:8]

    def _extract_expected_types(
        self,
        schema: Dict[str, Any],
        root_schema: Optional[Dict[str, Any]] = None,
    ) -> Set[str]:
        if not isinstance(schema, dict):
            return set()

        root = root_schema or schema
        normalized = self._resolve_schema_refs(schema, root)
        result: Set[str] = set()

        schema_type = normalized.get("type")
        if isinstance(schema_type, str):
            result.add(schema_type)
        elif isinstance(schema_type, list):
            result.update(t for t in schema_type if isinstance(t, str))

        for variant_key in ("anyOf", "oneOf", "allOf"):
            variants = normalized.get(variant_key)
            if not isinstance(variants, list):
                continue
            for variant in variants:
                if isinstance(variant, dict):
                    result.update(self._extract_expected_types(variant, root))

        structural_keys = (
            "type",
            "properties",
            "items",
            "prefixItems",
            "additionalProperties",
            "anyOf",
            "oneOf",
            "allOf",
            "$ref",
            "enum",
            "const",
            "format",
            "pattern",
            "minimum",
            "maximum",
        )
        if not result and isinstance(normalized, dict) and not any(key in normalized for key in structural_keys):
            # 無約束 schema（例如 Any -> {}）
            return {"any"}

        return result

    def _infer_value_static_types(
        self,
        value: Any,
        defined_vars: Set[str],
        var_to_output_schema: Dict[str, Dict[str, Any]],
    ) -> Set[str]:
        if value is None:
            return {"null"}
        if isinstance(value, bool):
            return {"boolean"}
        if isinstance(value, int):
            return {"integer"}
        if isinstance(value, float):
            return {"number"}
        if isinstance(value, dict):
            return {"object"}
        if isinstance(value, list):
            return {"array"}
        if not isinstance(value, str):
            return set()

        text = value.strip()
        if not text:
            return {"string"}

        if text.startswith("${") and text.endswith("}"):
            expression = text[2:-1].strip()
            return self._infer_expression_static_types(expression, var_to_output_schema)

        if text.startswith("$"):
            return self._infer_reference_static_types(text[1:], var_to_output_schema)

        if self._is_template_reference_string(text, defined_vars):
            return set()

        return {"string"}

    def _is_template_reference_string(self, text: str, defined_vars: Set[str]) -> bool:
        normalized = (text or "").strip()
        if not normalized:
            return False

        if normalized in defined_vars:
            return True

        if _IMPLICIT_REF_PATTERN.match(normalized):
            return normalized.split('.', 1)[0] in defined_vars

        if normalized.startswith("{") and normalized.endswith("}"):
            inner = normalized[1:-1].strip()
            if _IMPLICIT_REF_PATTERN.match(inner):
                return True

        if "{item." in normalized and "}" in normalized:
            return True

        return False

    def _infer_expression_static_types(
        self,
        expression: str,
        var_to_output_schema: Dict[str, Dict[str, Any]],
    ) -> Set[str]:
        if not expression:
            return set()

        try:
            expr_node = ast.parse(expression, mode="eval").body
        except Exception:
            return set()

        return self._infer_ast_node_types(expr_node, var_to_output_schema)

    def _infer_ast_node_types(
        self,
        node: ast.AST,
        var_to_output_schema: Dict[str, Dict[str, Any]],
    ) -> Set[str]:
        if isinstance(node, ast.Constant):
            return self._python_literal_to_json_types(node.value)

        if isinstance(node, ast.Dict):
            return {"object"}
        if isinstance(node, (ast.List, ast.ListComp, ast.Tuple, ast.Set, ast.SetComp)):
            return {"array"}
        if isinstance(node, ast.DictComp):
            return {"object"}
        if isinstance(node, ast.JoinedStr):
            return {"string"}

        if isinstance(node, ast.Name):
            return self._infer_reference_static_types(node.id, var_to_output_schema)

        if isinstance(node, ast.Attribute):
            ref = self._attribute_to_ref(node)
            if not ref:
                return set()
            return self._infer_reference_static_types(ref, var_to_output_schema)

        if isinstance(node, ast.Subscript):
            base_types = self._infer_ast_node_types(node.value, var_to_output_schema)
            if "array" in base_types:
                return set()
            if "object" in base_types:
                return set()
            return set()

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                builtin_name = node.func.id
                builtin_type_map = {
                    "str": {"string"},
                    "int": {"integer"},
                    "float": {"number"},
                    "bool": {"boolean"},
                    "list": {"array"},
                    "dict": {"object"},
                    "len": {"integer"},
                    "sum": {"number"},
                }
                if builtin_name in builtin_type_map:
                    return builtin_type_map[builtin_name]

            if isinstance(node.func, ast.Attribute) and node.func.attr == "join":
                return {"string"}
            return set()

        if isinstance(node, ast.IfExp):
            body_types = self._infer_ast_node_types(node.body, var_to_output_schema)
            else_types = self._infer_ast_node_types(node.orelse, var_to_output_schema)
            return body_types | else_types

        if isinstance(node, ast.BoolOp):
            return {"boolean"}
        if isinstance(node, ast.Compare):
            return {"boolean"}

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return {"boolean"}
            return self._infer_ast_node_types(node.operand, var_to_output_schema)

        if isinstance(node, ast.BinOp):
            left_types = self._infer_ast_node_types(node.left, var_to_output_schema)
            right_types = self._infer_ast_node_types(node.right, var_to_output_schema)
            if "string" in left_types or "string" in right_types:
                return {"string"}
            if "number" in left_types or "number" in right_types:
                return {"number"}
            if "integer" in left_types and "integer" in right_types:
                return {"integer"}
            return set()

        return set()

    def _python_literal_to_json_types(self, value: Any) -> Set[str]:
        if value is None:
            return {"null"}
        if isinstance(value, bool):
            return {"boolean"}
        if isinstance(value, int):
            return {"integer"}
        if isinstance(value, float):
            return {"number"}
        if isinstance(value, str):
            return {"string"}
        if isinstance(value, list):
            return {"array"}
        if isinstance(value, dict):
            return {"object"}
        return set()

    def _attribute_to_ref(self, node: ast.Attribute) -> Optional[str]:
        parts: List[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.insert(0, current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.insert(0, current.id)
        return ".".join(parts)

    def _infer_reference_static_types(
        self,
        ref: str,
        var_to_output_schema: Dict[str, Dict[str, Any]],
    ) -> Set[str]:
        if not ref:
            return set()

        parts = ref.split(".")
        var_name = parts[0]

        # 根變量引用（$var）在 DSL 中常用於“句柄/延遲解析”語義，
        # 這裏按動態類型處理，避免誤判（如 Logic.Wait.tasks=$async_node）。
        if len(parts) == 1:
            return {"any"}

        root_schema = var_to_output_schema.get(var_name)
        if not root_schema:
            return set()

        current_candidates: List[Dict[str, Any]] = [root_schema]
        for part in parts[1:]:
            next_candidates: List[Dict[str, Any]] = []
            for candidate in current_candidates:
                candidate = self._resolve_schema_refs(candidate, root_schema)
                for option in self._expand_schema_options(candidate):
                    option = self._resolve_schema_refs(option, root_schema)

                    properties = option.get("properties") if isinstance(option, dict) else None
                    if isinstance(properties, dict) and isinstance(properties.get(part), dict):
                        next_candidates.append(properties[part])
                        continue

                    additional = option.get("additionalProperties") if isinstance(option, dict) else None
                    if isinstance(additional, dict):
                        next_candidates.append(additional)
                        continue

            if not next_candidates:
                return set()
            current_candidates = next_candidates

        inferred_types: Set[str] = set()
        for candidate in current_candidates:
            inferred_types.update(self._extract_expected_types(candidate, root_schema))
        return inferred_types

    def _types_compatible(self, expected_types: Set[str], actual_types: Set[str]) -> bool:
        if not expected_types or not actual_types:
            return True

        if "any" in expected_types or "any" in actual_types:
            return True

        for actual in actual_types:
            if actual in expected_types:
                return True
            if actual == "integer" and "number" in expected_types:
                return True

        return False
    
    def _validate_expression_nodes(self, statements):
        """檢查 Expression 節點特殊規則"""
        for stmt in statements:
            if stmt.node_type != "Logic.Expression":
                continue
            
            expression = stmt.config.get('expression', '')
            if not expression:
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='expression',
                    message="Expression 節點缺少 expression 參數",
                    suggestion="請填寫表達式內容"
                ))
    
    def _validate_async_dependencies(self, statements):
        """檢查異步節點依賴

        規則：如果某個同步節點使用了異步節點的輸出，那麼在此之前必須出現過一個
        `Logic.Wait` 來等待該異步任務完成。

        說明：這裏採用“代碼順序”的屏障語義做校驗（更符合執行器實際行爲），不要求
        下游節點必須顯式引用 `wait_xxx` 變量。
        """

        async_nodes = {stmt.variable for stmt in statements if stmt.is_async}
        if not async_nodes:
            return

        waited_async_nodes: set[str] = set()

        def _extract_waited_async_vars(wait_stmt) -> set[str]:
            tasks = wait_stmt.config.get("tasks") or wait_stmt.config.get("wait_for")
            waited: set[str] = set()
            if not tasks:
                return waited

            if isinstance(tasks, str):
                task_var = tasks.lstrip("$")
                if task_var in async_nodes:
                    waited.add(task_var)
                return waited

            if isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, str):
                        continue
                    task_var = task.lstrip("$")
                    if task_var in async_nodes:
                        waited.add(task_var)
                return waited

            # 其它複雜類型（極少見）：不做靜態推斷
            return waited

        # 基於“代碼順序”的屏障語義進行校驗：只要在某條語句之前執行過 wait，後續語句就可以安全使用對應異步結果。
        for stmt in statements:
            if stmt.node_type == "Logic.Wait":
                waited_async_nodes.update(_extract_waited_async_vars(stmt))
                continue

            if stmt.is_async:
                continue

            # 收集所有依賴的變量（包括 Expression.expression 內部引用）
            all_deps = set(stmt.depends_on)
            if stmt.node_type == "Logic.Expression":
                expression = stmt.config.get("expression", "")
                if expression:
                    all_deps.update(get_expression_dependencies(expression))

            async_deps = all_deps & async_nodes
            if not async_deps:
                continue

            for async_dep in async_deps:
                if async_dep in waited_async_nodes:
                    continue

                self.errors.append(
                    ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type="async_dependency",
                        message=(
                            f"同步節點 '{stmt.variable}' 依賴異步節點 '{async_dep}'，但在此之前沒有執行 Logic.Wait 等待該異步任務完成"
                        ),
                        suggestion=(
                            f"在使用 '{async_dep}' 之前插入 wait 節點，例如：\n"
                            f"#@node(description=\"等待 {async_dep} 完成\")\n"
                            f"wait_{async_dep} = Logic.Wait(tasks={async_dep})\n"
                            f"#</node>"
                        ),
                    )
                )
    
    def _validate_parameter_values(self, statements):
        """檢查參數值的有效性
        
        檢測常見的錯誤值，如：
        - '[object Object]': JavaScript 對象未正確序列化
        - 'undefined': JavaScript undefined 值
        - 'null' 字符串（應該是 None）
        """
        for stmt in statements:
            if not stmt.node_type:
                continue

            for path, value in self._iter_config_values(stmt.config):
                if not isinstance(value, str):
                    continue

                # 檢測 [object Object]
                if value == '[object Object]' or '[object Object]' in value:
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='invalid_value',
                        message=f"參數 '{path}' 的值無效: '{value}'",
                        suggestion="這通常是因爲前端未正確序列化對象。請刷新頁面或重新編輯該參數。"
                    ))
                    continue

                # 檢測 undefined
                if value == 'undefined':
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='invalid_value',
                        message=f"參數 '{path}' 的值爲 undefined",
                        suggestion="請爲該參數提供有效值或刪除該參數。"
                    ))
                    continue

                # 檢測“把表達式包成字符串字面量”的常見錯誤
                if stmt.node_type != "Logic.Expression" and self._looks_like_quoted_expression_literal(value):
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='expression_literal',
                        message=(
                            f"參數 '{path}' 看起來是表達式字符串字面量，執行時不會被當作表達式計算"
                        ),
                        suggestion=(
                            "如果需要計算表達式，請使用 `${...}` 或新增 `Logic.Expression` 節點並引用 `.result`。"
                        )
                    ))

            self._validate_card_payload_static_rules(stmt)
            self._validate_card_content_schema(stmt)

    def _validate_card_payload_static_rules(self, stmt) -> None:
        """卡片寫入參數的靜態約束。"""
        rules = {
            "Card.Create": ("content", False),
            "Card.Update": ("content_merge", False),
            "Card.BatchUpsert": ("content_template", True),
        }

        rule = rules.get(stmt.node_type)
        if not rule:
            return

        field_name, allow_item_template = rule
        if field_name not in stmt.config:
            return

        payload = stmt.config.get(field_name)
        if payload is None:
            return

        # 支持結構化輸出契約直傳（如 content = structured.data）
        if stmt.node_type in ("Card.Create", "Card.BatchUpsert") and self._card_content_reference_matches_contract(stmt, field_name):
            return

        if not isinstance(payload, dict):
            node_param = f"{stmt.node_type}.{field_name}"
            card_type_hint = ""
            if stmt.node_type in ("Card.Create", "Card.BatchUpsert"):
                card_type_name = stmt.config.get("card_type")
                if isinstance(card_type_name, str) and card_type_name.strip():
                    schema_fields = self._get_card_schema_fields_preview(card_type_name.strip())
                    if schema_fields:
                        card_type_hint = f" 可用字段示例：{', '.join(schema_fields)}。"

            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='type_mismatch',
                message=f"{node_param} 必須是字面量 dict(object)，當前不是可校驗對象。",
                suggestion=(
                    f"請直接寫成 `{{...}}`"
                    f"{card_type_hint}"
                )
            ))
            return

        bad_ref = self._find_forbidden_dynamic_value(
            payload,
            path=f"config.{field_name}",
            allow_item_template=allow_item_template,
        )
        if bad_ref:
            bad_path, bad_value, reason = bad_ref
            node_param = f"{stmt.node_type}.{field_name}"
            reason_hint = ""
            if reason == "inline_expression":
                reason_hint = "檢測到 `${...}` 表達式。"
            elif reason == "expression_result":
                reason_hint = "檢測到 `Logic.Expression.result` 引用。"
            elif reason == "item_template_not_allowed":
                reason_hint = "檢測到 `{item.xxx}` 模板，但該節點不支持。"
            elif reason == "unknown_reference":
                reason_hint = "檢測到無法識別的變量引用。"
            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='type_mismatch',
                message=(
                    f"{node_param} 包含不可靜態校驗的動態賦值: {bad_path} = {bad_value!r}"
                ),
                suggestion=(
                    "卡片寫入參數必須可靜態校驗。"
                    "請使用字面量 dict"
                    f" {reason_hint}"
                )
            ))

    def _find_forbidden_dynamic_value(
        self,
        value: Any,
        path: str,
        allow_item_template: bool,
    ) -> Optional[Tuple[str, Any, str]]:
        if isinstance(value, str):
            text = value.strip()
            reason = self._classify_forbidden_card_dynamic(text, allow_item_template)
            if reason:
                return path, value, reason
            return None

        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}"
                bad = self._find_forbidden_dynamic_value(item, child_path, allow_item_template)
                if bad:
                    return bad
            return None

        if isinstance(value, list):
            for idx, item in enumerate(value):
                child_path = f"{path}[{idx}]"
                bad = self._find_forbidden_dynamic_value(item, child_path, allow_item_template)
                if bad:
                    return bad
            return None

        return None

    def _classify_forbidden_card_dynamic(self, text: str, allow_item_template: bool) -> Optional[str]:
        normalized = (text or "").strip()
        if not normalized:
            return None

        # 允許 `$var.path`，後續由契約匹配或 schema 校驗決定是否通過
        if normalized.startswith("$"):
            return None

        if normalized.startswith("${") and normalized.endswith("}"):
            return "inline_expression"

        if not allow_item_template and "{item." in normalized and "}" in normalized:
            return "item_template_not_allowed"

        return None

    def _iter_config_values(self, value: Any, path: str = "config") -> Iterable[Tuple[str, Any]]:
        """遞歸展開配置值，返回 (path, value)。"""
        yield path, value

        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                yield from self._iter_config_values(item, child_path)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                child_path = f"{path}[{idx}]"
                yield from self._iter_config_values(item, child_path)

    def _looks_like_quoted_expression_literal(self, text: str) -> bool:
        """啓發式檢測：字符串是否像“被錯誤加引號的表達式”。"""
        normalized = (text or "").strip()
        if not normalized:
            return False

        if normalized.startswith("${") and normalized.endswith("}"):
            return False
        if normalized.startswith("$"):
            return False

        has_var_path = bool(_EXPR_LITERAL_VAR_PATTERN.search(normalized))
        has_func_call = bool(_EXPR_LITERAL_FUNC_PATTERN.search(normalized))
        has_operator = any(token in normalized for token in (" + ", " - ", " * ", " / ", " and ", " or "))
        has_comprehension = (
            (" for " in normalized and " in " in normalized)
            and ("[" in normalized or "{" in normalized)
        )

        return has_comprehension or ((has_var_path or has_func_call) and has_operator)

    def _validate_card_content_schema(self, stmt) -> None:
        """基於卡片類型 schema 做通用 content 結構校驗。"""
        if stmt.node_type not in ("Card.Create", "Card.BatchUpsert", "Card.Update"):
            return

        if stmt.node_type == "Card.Update":
            content_merge = stmt.config.get("content_merge")
            if not isinstance(content_merge, dict):
                return

            schema = self._get_card_update_content_schema(stmt)
            if not schema:
                return

            self._validate_content_obj_against_schema(
                stmt,
                "config.content_merge",
                content_merge,
                schema,
                ignore_required=True,
            )
            return

        card_type_name = stmt.config.get("card_type")
        if not isinstance(card_type_name, str) or not card_type_name.strip():
            return

        schema = self._get_card_content_schema(card_type_name.strip())
        if not schema:
            return

        if stmt.node_type == "Card.Create":
            content = stmt.config.get("content")
            if self._card_content_reference_matches_contract(stmt, "content"):
                return
            if isinstance(content, dict):
                self._validate_content_obj_against_schema(stmt, "config.content", content, schema)
            return

        # Card.BatchUpsert：僅校驗字面量對象模板；字符串模板無法靜態展開
        content_template = stmt.config.get("content_template")
        if isinstance(content_template, dict):
            self._validate_content_obj_against_schema(stmt, "config.content_template", content_template, schema)

    def _get_card_update_content_schema(self, stmt) -> Optional[Dict[str, Any]]:
        if not self.session:
            return None

        card_id = stmt.config.get("card_id")
        if not isinstance(card_id, int):
            return None

        try:
            from app.db.models import Card, CardType

            card = self.session.get(Card, card_id)
            if not card:
                return None

            if isinstance(card.json_schema, dict) and card.json_schema:
                return card.json_schema

            card_type = self.session.get(CardType, card.card_type_id)
            if card_type and isinstance(card_type.json_schema, dict):
                return card_type.json_schema
        except Exception as exc:
            logger.warning("[WorkflowValidator] load Card.Update schema failed: {}", exc)
        return None

    def _get_card_content_schema(self, card_type_name: str) -> Optional[Dict[str, Any]]:
        if not self.session:
            return None

        if self._card_schema_by_name is None:
            self._card_schema_by_name = {}
            try:
                from app.db.models import CardType

                rows = self.session.exec(select(CardType)).all()
                for row in rows:
                    schema = row.json_schema if isinstance(row.json_schema, dict) else None
                    if not schema:
                        continue
                    if row.name:
                        self._card_schema_by_name[row.name] = schema
                    model_name = getattr(row, "model_name", None)
                    if model_name:
                        self._card_schema_by_name[model_name] = schema
            except Exception as exc:
                logger.warning("[WorkflowValidator] load card schemas failed: {}", exc)
                self._card_schema_by_name = {}

        return self._card_schema_by_name.get(card_type_name)

    def _validate_content_obj_against_schema(
        self,
        stmt,
        source_path: str,
        content_obj: Dict[str, Any],
        schema: Dict[str, Any],
        ignore_required: bool = False,
    ) -> None:
        known_fields = self._extract_known_top_level_fields(schema)
        if known_fields:
            unknown_fields = [key for key in content_obj.keys() if key not in known_fields]
            if unknown_fields:
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='type_mismatch',
                    message=(
                        f"{source_path} 包含 schema 未定義字段: {', '.join(unknown_fields)}"
                    ),
                    suggestion=(
                        f"請僅使用該卡片類型已定義字段: {', '.join(sorted(known_fields))}"
                    )
                ))

        if Draft202012Validator is None:
            props = schema.get("properties") if isinstance(schema, dict) else None
            if not (isinstance(props, dict) and props):
                return

            required_fields: Set[str] = set(schema.get("required") or [])
            unknown_fields = [key for key in content_obj.keys() if key not in props]

            if unknown_fields:
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='type_mismatch',
                    message=(
                        f"{source_path} 包含未定義字段: {', '.join(unknown_fields)}"
                    ),
                    suggestion=(
                        f"請僅使用該卡片類型 schema 中定義的字段: {', '.join(sorted(props.keys()))}"
                    )
                ))

            missing_required = [field for field in required_fields if field not in content_obj]
            if missing_required and not ignore_required:
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='type_mismatch',
                    message=(
                        f"{source_path} 缺少必填字段: {', '.join(missing_required)}"
                    ),
                    suggestion="請補齊 schema 要求的必填字段。"
                ))
            return

        try:
            validator = Draft202012Validator(schema)
            for err in validator.iter_errors(content_obj):
                if ignore_required and err.validator == "required":
                    continue
                if (
                    err.validator == "type"
                    and isinstance(err.instance, str)
                    and self._is_dynamic_value_string(err.instance)
                ):
                    continue

                field_path = ".".join(str(p) for p in err.path)
                full_path = f"{source_path}.{field_path}" if field_path else source_path
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='type_mismatch',
                    message=f"{full_path} 不符合卡片 schema 約束: {err.message}",
                    suggestion="請根據該卡片類型 schema 修正字段結構與類型。"
                ))
        except Exception as exc:
            logger.warning("[WorkflowValidator] jsonschema validation failed: {}", exc)

    def _extract_known_top_level_fields(self, schema: Dict[str, Any]) -> Set[str]:
        if not isinstance(schema, dict):
            return set()

        known_fields: Set[str] = set()
        root = self._resolve_schema_refs(schema, schema)
        options = self._expand_schema_options(root)
        if not options:
            options = [root]

        for option in options:
            normalized = self._resolve_schema_refs(option, schema)
            properties = normalized.get("properties") if isinstance(normalized, dict) else None
            if isinstance(properties, dict):
                known_fields.update(properties.keys())

        return known_fields

    def _is_dynamic_value_string(self, text: str) -> bool:
        """是否爲運行期動態值引用。"""
        normalized = (text or "").strip()
        if not normalized:
            return False
        if normalized.startswith("${") and normalized.endswith("}"):
            return True
        if normalized.startswith("$"):
            return True
        if "{item." in normalized and "}" in normalized:
            return True
        return False


def validate_workflow(code: str, session: Optional[Session] = None) -> ValidationResult:
    """便捷函數：校驗工作流代碼
    
    Args:
        code: 工作流代碼
        
    Returns:
        校驗結果
    """
    validator = WorkflowValidator(session=session)
    return validator.validate(code)
