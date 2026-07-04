"""System Prompt 構建工具

負責爲指令流生成構建完整的 System Prompt。
"""

import json
from typing import Dict, Any, Optional
from sqlmodel import Session

from app.services import prompt_service


# 兜底的硬編碼指令說明（當提示詞文件不存在時使用）
FALLBACK_INSTRUCTION_GUIDE = """## 指令流生成規範

你需要使用指令流的方式生成內容。指令流允許你自由混合自然語言思考和 JSON 指令，逐步構建目標數據結構。

## 可用指令

1. **設置字段值**
   ```json
   {"op":"set","path":"<路徑>","value":<值>}
   ```
   - 可以設置任何類型的值：字符串、數字、布爾值、對象、數組
   - 路徑格式：JSON Pointer（如 /name, /age, /config/theme），請始終以 `/` 開頭
   - 示例：{"op":"set","path":"/name","value":"林風"}
   - 示例（數組）：{"op":"set","path":"/tags","value":["熱血","玄幻"]}  <-- 注意：必須包含 "value" 鍵

2. **向數組追加元素**
   ```json
   {"op":"append","path":"<數組路徑>","value":<元素>}
   ```
   - 用於向數組逐個添加元素
   - 示例：{"op":"append","path":"/hobbies","value":"閱讀"}

3. **生成完成**
   ```json
   {"op":"done"}
   ```
   - 表示所有字段已生成完成
   - 系統會自動校驗數據完整性

## 輸出格式要求

1. **每個 JSON 指令必須單獨一行**，且是完整的 JSON 對象
2. **可以自由混合自然語言和指令**，例如：
   ```
   讓我先思考角色的背景...
   {"op":"set","path":"/name","value":"林風"}
   這個名字很適合武俠背景
   {"op":"set","path":"/age","value":25}
   ```

3. **可以與用戶交互**：
   - 如果遇到需要用戶確認的細節，可以用自然語言提問
   - 用戶會在輸入框中回覆，你會看到他的回答
   - 但請優先參考任務說明中的要求，避免過度提問

4. **生成順序建議**：
   - 先設置簡單字段（如 name, age）
   - 再設置複雜字段（如嵌套對象）
   - 對於數組，使用 append 逐個添加元素

5. **完成標誌**：
   - 生成完所有必填字段後，輸出 {"op":"done"}
   - 系統會自動校驗，如果有缺失會提示你補充

## 重要提示

- 確保生成的值符合字段的類型和描述
- 每次只生成一個或幾個相關字段，不要一次性生成所有內容
- 保持輸出的自然流暢，可以用自然語言表達你的思考過程
- JSON 指令必須嚴格符合格式，確保可以被正確解析
- `path` 請優先使用 `/field_name` 這種 JSON Pointer，不要省略前導 `/`
- 所有必填字段生成完成後，務必輸出 {"op":"done"} 表示完成
"""


def build_instruction_system_prompt(
    session: Session,
    schema: Dict[str, Any],
    card_prompt: Optional[str] = None
) -> str:
    """構建指令流生成的 System Prompt
    
    組成部分：
    1. 卡片任務提示詞（角色定位 + 任務說明）
    2. 指令流生成規範
    3. JSON Schema（目標數據結構）
    
    Args:
        session: 數據庫會話
        schema: 目標數據結構的 JSON Schema
        card_prompt: 卡片類型的自定義提示詞
        
    Returns:
        完整的 System Prompt
    """
    parts = []
    
    # 1. 卡片任務提示詞（如果有）
    if card_prompt:
        parts.append(card_prompt)
    
    # 2. 加載指令規範說明
    instruction_guide = FALLBACK_INSTRUCTION_GUIDE
    try:
        prompt = prompt_service.get_prompt_by_name(session, "指令流生成規範")
        if prompt and prompt.template:
            instruction_guide = prompt.template
    except Exception:
        pass
    parts.append(instruction_guide)
    
    # 3. JSON Schema 定義
    schema_json = json.dumps(schema, indent=2, ensure_ascii=False)
    schema_section = f"\n## 目標數據結構（JSON Schema）\n\n```json\n{schema_json}\n```\n\n請參照此 Schema 使用指令流逐步生成內容。"
    parts.append(schema_section)
    
    return "\n\n".join(parts)


def build_user_task_prompt(
    user_prompt: str,
    context_info: Optional[str] = None,
    current_data: Optional[Dict[str, Any]] = None
) -> str:
    """構建用戶任務提示（第一條 User 消息）
    
    組成部分：
    1. 上下文注入信息
    2. 用戶要求
    3. 已有數據（如果是繼續生成）
    
    注意：卡片任務說明和 Schema 已經在 System Prompt 中，這裏不再重複。
    
    Args:
        user_prompt: 用戶輸入的要求
        context_info: 上下文注入信息
        current_data: 當前已有的數據
        
    Returns:
        完整的用戶任務提示
    """
    parts = []
    
    # 1. 上下文信息（如果有）
    if context_info:
        parts.append(f"## 相關上下文\n\n{context_info}")
    
    # 2. 用戶要求
    if user_prompt:
        parts.append(f"## 用戶要求\n\n{user_prompt}")
    else:
        parts.append("請開始生成卡片內容")
    
    # 3. 已有數據（如果是繼續生成）
    if current_data:
        current_data_json = json.dumps(current_data, indent=2, ensure_ascii=False)
        parts.append(f"## 當前已生成的數據\n\n```json\n{current_data_json}\n```\n\n請繼續生成缺失的字段。")
    
    return "\n\n".join(parts)
