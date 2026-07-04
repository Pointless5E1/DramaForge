"""指令流生成服務

負責調用 LLM 生成指令流，並進行實時校驗和自動修復。
"""

import json
import re
import asyncio
from typing import AsyncIterator, Dict, Any, List, Optional
from sqlmodel import Session
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from pydantic import ValidationError
from loguru import logger

from app.services.ai.core.chat_model_factory import build_chat_model
from app.services.ai.core.quota_manager import precheck_quota, record_usage
from app.services.ai.core.token_utils import estimate_tokens
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.generation.instruction_validator import (
    validate_instruction, 
    apply_instruction,
    format_validation_errors
)
from app.services.ai.generation.prompt_builder import build_user_task_prompt
from app.schemas.instruction import ConversationMessage


def _estimate_messages_input_tokens(messages: List[BaseMessage]) -> int:
    parts: List[str] = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            parts.append(content)
            continue
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
                elif isinstance(block, str):
                    parts.append(block)
    return estimate_tokens("\n".join(parts))


async def generate_instruction_stream(
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    system_prompt: str,
    schema: Dict[str, Any],
    current_data: Dict[str, Any],
    conversation_context: List[ConversationMessage],
    context_info: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    timeout: float = 150,
    max_retry: int = 3,
    track_stats: bool = True,
) -> AsyncIterator[Dict[str, Any]]:
    """生成指令流（帶自動校驗與修復）
    
    Args:
        session: 數據庫會話
        llm_config_id: LLM 配置 ID
        user_prompt: 用戶輸入的提示詞
        system_prompt: 系統提示詞
        schema: 目標數據結構的 JSON Schema
        current_data: 當前已生成的數據
        conversation_context: 對話歷史
        temperature: 採樣溫度
        max_tokens: 最大生成 token 數
        timeout: 超時時間
        max_retry: 最大重試次數
        
    Yields:
        事件字典，包含 type 和對應的數據
    """
    # 構建 ChatModel
    try:
        chat_model = build_chat_model(
            session=session,
            llm_config_id=llm_config_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )
    except Exception as e:
        logger.error(f"構建 ChatModel 失敗: {e}")
        yield {
            "type": "error",
            "text": f"初始化 LLM 失敗: {str(e)}"
        }
        return
    
    # 創建 Pydantic 動態模型（用於最終驗證）
    try:
        DynamicModel = build_model_from_json_schema('DynamicResponseModel', schema)
    except Exception as e:
        logger.error(f"創建動態模型失敗: {e}")
        yield {
            "type": "error",
            "text": f"Schema 解析失敗: {str(e)}"
        }
        return
    
    # 收集已生成的數據（深拷貝避免修改原始數據）
    collected_data = dict(current_data)
    
    # 構建消息歷史
    messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]
    
    # 如果是首次生成（conversation_context爲空），構建第一條用戶消息
    if not conversation_context:
        # 構建第一條用戶消息：上下文 + 用戶要求 + 已有數據
        # （任務說明和 Schema 已經在 System Prompt 中）
        task_prompt = build_user_task_prompt(
            user_prompt=user_prompt or "請開始生成卡片內容",
            context_info=context_info,
            current_data=collected_data if collected_data else None
        )
        messages.append(HumanMessage(content=task_prompt))
    else:
        # 繼續生成：添加歷史對話上下文
        for msg in conversation_context:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
        
        # 始終在最後添加已生成數據信息（如果有）
        # 這樣 LLM 能夠知道當前狀態，避免重複生成
        if collected_data:
            current_data_info = f"\n\n## 當前已生成的數據\n\n```json\n{json.dumps(collected_data, ensure_ascii=False, indent=2)}\n```\n\n請繼續生成缺失的字段，不要重複生成已有字段。"
            
            # 如果最後一條是用戶消息，追加到該消息
            if messages and isinstance(messages[-1], HumanMessage):
                messages[-1].content += current_data_info
            else:
                # 否則新建一條用戶消息
                messages.append(HumanMessage(content=current_data_info))
    
    # 打印完整的消息上下文（用於調試）
    # logger.info("=" * 80)
    # logger.info(f"[指令生成] 開始生成，共 {len(messages)} 條消息")
    # for idx, msg in enumerate(messages):
    #     msg_type = type(msg).__name__
    #     content_preview = msg.content
    #     logger.info(f"  [{idx}] {msg_type}: {content_preview}")
    # logger.info("=" * 80)
    
    # 開始生成循環（支持自動修復）
    failed_instructions = []  # 累積失敗的指令
    generation_completed = False  # 標記是否正常完成
    
    for attempt in range(max_retry):
        logger.info(f"[生成輪次 {attempt + 1}/{max_retry}] 開始生成...")
        attempt_input_tokens = _estimate_messages_input_tokens(messages)
        if track_stats:
            ok, reason = precheck_quota(
                session,
                llm_config_id,
                attempt_input_tokens,
                need_calls=1,
            )
            if not ok:
                yield {
                    "type": "error",
                    "text": f"LLM配額不足: {reason}",
                }
                return

        attempt_output_text = ""
        attempt_started = False
        attempt_aborted = False
        try:
            # 流式調用 LLM
            buffer = ""
            ai_output_lines = []  # 記錄AI的所有輸出（用於反饋）
            need_fix = False  # 是否需要修復（完整性校驗失敗）
            fix_prompt = ""  # 修復提示
            should_break_stream = False  # 是否應該中斷流
            
            json_buffer = ""  # JSON 累積緩衝區
            brace_depth = 0  # 花括號深度
            in_string = False  # 是否在字符串內
            escape_next = False  # 下一個字符是否被轉義

            attempt_started = True
            async for chunk in chat_model.astream(messages):
                raw = getattr(chunk, "content", "")
                if isinstance(raw, str):
                    content = raw
                elif isinstance(raw, list):
                    parts = []
                    for part in raw:
                        if isinstance(part, dict):
                            # 只拼 text，避免 reasoning/tool 片段污染你後面的 JSON 行解析
                            if part.get("type") == "text" and isinstance(part.get("text"), str):
                                parts.append(part["text"])
                        elif isinstance(part, str):
                            parts.append(part)
                    content = "".join(parts)
                else:
                    content = str(raw) if raw is not None else ""

                if not content:
                    continue

                attempt_output_text += content
                buffer += content
                
                # 按行解析
                lines = buffer.split('\n')
                buffer = lines[-1]  # 保留不完整的行
                
                for line in lines[:-1]:
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    
                    ai_output_lines.append(line_stripped)  # 記錄輸出
                    
                    # 逐字符處理，累積完整的 JSON 對象
                    instruction = None
                    for char in line:
                        # 處理轉義
                        if escape_next:
                            if brace_depth > 0:
                                json_buffer += char
                            escape_next = False
                            continue
                        
                        if char == '\\':
                            if brace_depth > 0:
                                json_buffer += char
                            escape_next = True
                            continue
                        
                        # 處理字符串邊界
                        if char == '"' and brace_depth > 0:
                            in_string = not in_string
                            json_buffer += char
                            continue
                        
                        # 只在字符串外計數花括號
                        if not in_string:
                            if char == '{':
                                brace_depth += 1
                                json_buffer += char
                            elif char == '}':
                                json_buffer += char
                                brace_depth -= 1
                                
                                # JSON 對象完整
                                if brace_depth == 0:
                                    instruction = try_parse_instruction(json_buffer)
                                    if not instruction:
                                        # 解析失敗，可能是無效 JSON
                                        logger.warning(f"JSON 解析失敗: {json_buffer}")
                                        # 嘗試修復常見錯誤 (如末尾逗號)
                                        try:
                                            # 簡單的清理邏輯，可以根據需要增強
                                            cleaned_json = json_buffer.replace(",}", "}").replace(",]", "]")
                                            instruction = try_parse_instruction(cleaned_json)
                                        except Exception:
                                            pass
                                            
                                        if not instruction:
                                            # JSON 解析失敗，累積錯誤
                                            failed_instructions.append({
                                                "instruction": json_buffer[:100],
                                                "error": "JSON 解析失敗"
                                            })
                                            yield {
                                                "type": "warning",
                                                "text": f"無法解析指令 JSON: {json_buffer[:50]}..."
                                            }
                                            # JSON 解析失敗，累積錯誤但不立即打斷，讓LLM繼續生成
                                            # 除非累積錯誤過多，才強制中斷
                                            if len(failed_instructions) >= 5:
                                                should_break_stream = True
                                    
                                    json_buffer = ""
                                    if instruction:
                                        break  # 找到指令，處理它
                            elif brace_depth > 0:
                                json_buffer += char
                        elif brace_depth > 0:
                            json_buffer += char
                    
                    if instruction:
                        # ... (existing instruction processing logic) ...
                        # 解析成功，校驗指令
                        try:
                            # ...
                            validate_instruction(instruction, schema)
                            apply_instruction(collected_data, instruction)
                            yield {
                                "type": "instruction",
                                "instruction": instruction
                            }
                            
                            # done logic ...
                            if instruction.get('op') == 'done':
                                logger.info("[Done 指令] 收到 done 指令，準備進行最終校驗...")
                                
                                # 1. 檢查是否有累積的指令錯誤
                                has_instruction_errors = len(failed_instructions) > 0
                                
                                # 2. 使用 Pydantic 進行數據完整性校驗
                                validation_errors = []
                                try:
                                    validated_model = DynamicModel(**collected_data)
                                except ValidationError as e:
                                    # 格式化 Pydantic 錯誤
                                    validation_errors = e.errors()
                                
                                # 3. 如果有任何問題（指令錯誤 OR 數據校驗失敗），拒絕完成並反饋
                                if has_instruction_errors or validation_errors:
                                    logger.warning(f"[Done 拒絕] 指令錯誤: {len(failed_instructions)} 個, 數據校驗問題: {len(validation_errors)} 個")
                                    
                                    feedback_parts = []
                                    
                                    # 構建指令錯誤反饋
                                    if failed_instructions:
                                        feedback_parts.append("【指令執行失敗】以下指令解析或執行出錯：")
                                        for item in failed_instructions:
                                            feedback_parts.append(f"- {item['error']}: {str(item['instruction'])[:100]}")
                                    
                                    # 構建數據完整性反饋
                                    if validation_errors:
                                        feedback_parts.append("\n【數據完整性缺失】以下字段未通過校驗：")
                                        feedback_parts.append(format_validation_errors(validation_errors))
                                    
                                    feedback_text = "\n".join(feedback_parts)
                                    
                                    # 設置修復標誌
                                    need_fix = True
                                    fix_prompt = f"""你發送了 done 指令，但生成過程存在錯誤或數據不完整：

{feedback_text}

當前已成功應用的數據狀態：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

請修正上述指令錯誤，並補充缺失的必填字段。
**重要**：請不要解釋，直接輸出修正用的 JSON 指令（set/append），修復完成後再次輸出 {{"op":"done"}}
"""
                                    should_break_stream = True
                                else:
                                    # 一切完美，通過！
                                    logger.info("[Done 指令] ✅ 校驗完美通過！")
                                    generation_completed = True
                                    yield {
                                        "type": "done",
                                        "success": True,
                                        "message": "生成完成",
                                        "final_data": validated_model.model_dump(mode='json')
                                    }
                                    return

                        except ValueError as e:
                            logger.warning(f"指令校驗失敗: {e}")
                            failed_instructions.append({"instruction": instruction, "error": str(e)})
                            yield {"type": "warning", "text": f"指令校驗失敗: {str(e)}"}
                            # 指令校驗失敗，累積錯誤但不中斷，繼續
                            # should_break_stream = True

                    else:
                        # 不是 JSON 指令，視爲自然語言思考
                        # 只有在不在 JSON 累積過程中時才輸出
                        if brace_depth == 0 and line_stripped:
                             yield {
                                "type": "thinking",
                                "text": line
                            }
                
                # 檢查是否需要中斷流
                if should_break_stream:
                    break
            
            # 處理殘留的 JSON 緩衝區（多行 JSON 的最後部分）
            if json_buffer.strip() and brace_depth == 0:
                instruction = try_parse_instruction(json_buffer.strip())
                if instruction:
                    try:
                        validate_instruction(instruction, schema)
                        apply_instruction(collected_data, instruction)
                        yield {
                            "type": "instruction",
                            "instruction": instruction
                        }
                    except ValueError as e:
                        logger.warning(f"殘留 JSON 指令校驗失敗: {e}")
            
            # 處理最後一行（如果有）
            if buffer.strip():
                instruction = try_parse_instruction(buffer.strip())
                if instruction:
                    try:
                        validate_instruction(instruction, schema)
                        apply_instruction(collected_data, instruction)
                        yield {
                            "type": "instruction",
                            "instruction": instruction
                        }
                        
                        if instruction.get('op') == 'done':
                            try:
                                validated_model = DynamicModel(**collected_data)
                                yield {
                                    "type": "done",
                                    "success": True,
                                    "message": "生成完成",
                                    # 將最終校驗過的數據（包含注入的默認值）回傳給前端，確保一致性
                                    "final_data": validated_model.model_dump(mode='json')
                                }
                                return
                            except ValidationError as e:
                                error_msg = format_validation_errors(e.errors())
                                logger.warning(f"完整性校驗失敗: {error_msg}")
                                # 設置修復標誌，準備反饋給 LLM
                                need_fix = True
                                fix_prompt = f"""生成的數據不完整或有誤，請修正以下問題：

{error_msg}

當前數據：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

請繼續生成缺失或錯誤的字段，完成後再次輸出 {{"op":"done"}}
"""
                                should_break_stream = True
                    except ValueError as e:
                        logger.warning(f"指令校驗失敗: {e}")
                else:
                    yield {
                        "type": "thinking",
                        "text": buffer.strip()
                    }
            
            # 流結束後，處理各種情況
            
            # 情況1：完整性校驗失敗，需要修復
            if need_fix:
                logger.info(f"完整性校驗失敗，將反饋給LLM重新生成（嘗試 {attempt + 1}/{max_retry}）")
                
                # 將AI輸出和修復提示加入對話歷史
                messages.append(AIMessage(content="\n".join(ai_output_lines)))
                messages.append(HumanMessage(content=fix_prompt))
                
                # 重試前等待，避免立即重試觸發限流
                if attempt < max_retry - 1:
                    retry_delay = min(2 ** attempt, 5)  # 指數退避：1秒、2秒、4秒...
                    logger.info(f"等待 {retry_delay} 秒後重試...")
                    await asyncio.sleep(retry_delay)
                
                # 繼續下一輪生成
                continue
            
            # 情況2：指令校驗失敗，需要反饋給LLM
            if failed_instructions:
                # 構建錯誤反饋消息
                error_summary = "\n".join([
                    f"- 指令: {json.dumps(item['instruction'], ensure_ascii=False)}\n  錯誤: {item['error']}"
                    for item in failed_instructions
                ])
                
                feedback_prompt = f"""
你生成的以下 {len(failed_instructions)} 條指令校驗失敗：

{error_summary}

當前已成功應用的數據：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

請注意：
1. 檢查字段路徑是否正確
2. 對於數組字段，使用 append 操作前確保該字段是數組類型
3. 對於對象字段，使用 set 操作設置整個對象或使用嵌套路徑設置子字段
4. 參考Schema定義，確保操作符與字段類型匹配

請修正這些錯誤並繼續生成，完成後輸出 {{"op":"done"}}
"""
                
                logger.info(f"反饋 {len(failed_instructions)} 個失敗指令給LLM，重新生成")
                
                # 將AI輸出和反饋加入對話歷史
                messages.append(AIMessage(content="\n".join(ai_output_lines)))
                messages.append(HumanMessage(content=feedback_prompt))
                
                # 清空失敗列表，準備下一輪
                failed_instructions = []
                
                # 重試前等待，避免立即重試觸發限流
                if attempt < max_retry - 1:
                    retry_delay = min(2 ** attempt, 5)  # 指數退避：1秒、2秒、4秒...
                    logger.info(f"等待 {retry_delay} 秒後重試...")
                    await asyncio.sleep(retry_delay)
                
                # 繼續下一輪生成
                continue
            
            # 如果流結束但沒有 done 指令，可能是 max_tokens 限制或其他原因
            logger.warning("⚠️ LLM 流結束但未收到 done 指令")
            logger.info(f"當前已收集數據字段: {list(collected_data.keys())}")

            # 嘗試隱式完成（嘗試校驗）
            try:
                # 使用 Pydantic 模型進行最終校驗
                validated_model = DynamicModel(**collected_data)
                
                yield {
                    "type": "done",
                    "success": True,
                    "message": "生成結束 (自動補全)",
                    "final_data": validated_model.model_dump(mode='json')
                }
                generation_completed = True
                break
            except Exception as e:
                 logger.warning(f"流結束後的隱式校驗失敗: {e}")
                 # 如果真的校驗失敗，可能確實是截斷了，需要用戶反饋或者重試（這裏暫不自動重試，因爲已經是最後了）
                 pass
            logger.info(f"當前數據: {json.dumps(collected_data, ensure_ascii=False, indent=2)[:500]}...")
            
            # 嘗試驗證當前數據的完整性
            try:
                validated_model = DynamicModel(**collected_data)
                
                # 檢查是否有 Optional 字段缺失（可能是被截斷）
                schema_properties = schema.get("properties", {})
                missing_optional_fields = []
                for field_name, field_schema in schema_properties.items():
                    # 檢查是否是 Optional 字段（不在 required 中）
                    is_optional = field_name not in schema.get("required", [])
                    # 如果是 Optional 字段但數據中沒有（或爲空列表/空字符串）
                    if is_optional:
                        field_value = collected_data.get(field_name)
                        if field_value is None or field_value == [] or field_value == "":
                            missing_optional_fields.append(field_name)
                
                # 如果有 Optional 字段缺失，很可能是 max_tokens 截斷
                if missing_optional_fields:
                    logger.warning(f"⚠️ 雖然必填字段完整，但以下 Optional 字段缺失: {missing_optional_fields}")
                    logger.warning("結合 LLM 未發送 done 指令，懷疑是 max_tokens 截斷")
                    yield {
                        "type": "warning",
                        "text": f"⚠️ 生成被截斷（LLM 未發送 done 指令）。以下字段缺失：{', '.join(missing_optional_fields)}。\n\n原因可能是：\n1. max_tokens 設置過小（建議增加）\n2. 網絡波動或服務限流\n\n建議：稍後重試或調整參數。"
                    }
                    # 嘗試修復
                    if attempt < max_retry - 1:
                        logger.info(f"嘗試自動補充缺失字段（嘗試 {attempt + 1}/{max_retry}）")
                        fix_prompt = f"""
生成未完成，以下字段缺失：{', '.join(missing_optional_fields)}

當前數據：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

請繼續生成缺失的字段，完成後輸出 {{"op":"done"}}
"""
                        messages.append(AIMessage(content="\n".join(ai_output_lines)))
                        messages.append(HumanMessage(content=fix_prompt))
                        
                        # 重試前等待
                        retry_delay = min(2 ** attempt, 5)
                        logger.info(f"等待 {retry_delay} 秒後重試...")
                        await asyncio.sleep(retry_delay)
                        
                        continue
                    else:
                        # 最後一輪了，直接返回不完整的數據
                        logger.warning("已達最大重試次數，返回不完整的數據")
                        generation_completed = True
                        yield {
                            "type": "done",
                            "success": True,
                            "message": f"生成完成（部分字段缺失：{', '.join(missing_optional_fields)}）"
                        }
                        return
                
                # 所有字段都有值，數據完整
                logger.info("✅ 數據完整性校驗通過，雖然沒有 done 指令，但數據是完整的")
                generation_completed = True
                yield {
                    "type": "done",
                    "success": True,
                    "message": "生成完成（LLM 未發送 done 指令，但數據完整）"
                }
                return
            except ValidationError as e:
                # 數據不完整，可能是 max_tokens 限制導致輸出被截斷
                error_msg = format_validation_errors(e.errors())
                logger.warning(f"❌ 數據不完整: {error_msg}")
                
                # 檢查是否是第一輪就失敗（可能是 max_tokens 太小）
                if attempt == 0:
                    yield {
                        "type": "error",
                        "text": f"⚠️ 生成被截斷，原因可能是：\n1. max_tokens 設置過小（建議增加）\n2. 網絡波動或服務限流\n\n建議：稍後重試或調整參數。"
                    }
                    logger.error("第一輪生成就被截斷，強烈懷疑 max_tokens 過小")
                    break
                
                # 否則嘗試修復
                logger.info(f"嘗試自動修復缺失字段（嘗試 {attempt + 1}/{max_retry}）")
                need_fix = True
                fix_prompt = f"""
生成被中斷，數據不完整。缺失或錯誤的字段：

{error_msg}

當前數據：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

請繼續生成缺失的字段，完成後輸出 {{"op":"done"}}
"""
                messages.append(AIMessage(content="\n".join(ai_output_lines)))
                messages.append(HumanMessage(content=fix_prompt))
                
                # 重試前等待
                if attempt < max_retry - 1:
                    retry_delay = min(2 ** attempt, 4)
                    logger.info(f"等待 {retry_delay} 秒後重試...")
                    await asyncio.sleep(retry_delay)
                
                continue

        except asyncio.CancelledError:
            attempt_aborted = True
            raise
        except Exception as e:
            logger.error(f"生成過程出錯: {e}")
            yield {
                "type": "error",
                "text": f"生成失敗: {str(e)}"
            }
            break
        finally:
            if attempt_started and track_stats:
                try:
                    record_usage(
                        session,
                        llm_config_id,
                        attempt_input_tokens,
                        estimate_tokens(attempt_output_text),
                        calls=1,
                        aborted=attempt_aborted,
                    )
                except Exception as usage_error:
                    logger.warning(f"記錄指令流 token 統計失敗: {usage_error}")
    
    # 只有在未正常完成時才報告失敗
    if not generation_completed:
        logger.error(f"❌ 生成失敗：達到最大重試次數 {max_retry}")
        yield {
            "type": "error",
            "text": f"生成失敗：達到最大重試次數 {max_retry}"
        }


def try_parse_instruction(line: str) -> Optional[Dict[str, Any]]:
    """嘗試將一行文本解析爲 JSON 指令
    
    Args:
        line: 文本行
        
    Returns:
        解析成功返回指令字典，否則返回 None
    """
    # 移除可能的 markdown 代碼塊標記
    line = line.strip()
    if line.startswith('```') or line.endswith('```'):
        return None
    
    # 嘗試直接解析 JSON
    try:
        obj = json.loads(line)
        if isinstance(obj, dict) and 'op' in obj:
            return obj
    except json.JSONDecodeError:
        pass
    
    # 嘗試提取 JSON 對象（支持嵌套結構）
    # 逐字符掃描，匹配完整的 JSON 對象
    start_idx = line.find('{')
    if start_idx == -1:
        return None
    
    # 從第一個 { 開始，匹配完整的 JSON 對象
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(line)):
        char = line[i]
        
        # 處理字符串內的字符
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        # 只在字符串外計數花括號
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                
                # 找到匹配的閉合括號
                if brace_count == 0:
                    json_str = line[start_idx:i+1]
                    try:
                        obj = json.loads(json_str)
                        if isinstance(obj, dict) and 'op' in obj:
                            return obj
                    except json.JSONDecodeError:
                        # 繼續查找下一個可能的JSON對象
                        next_start = line.find('{', i+1)
                        if next_start != -1:
                            start_idx = next_start
                            brace_count = 0
                            in_string = False
                            escape_next = False
                        else:
                            return None
    
    return None
