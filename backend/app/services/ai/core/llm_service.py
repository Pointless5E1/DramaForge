"""通用LLM服務

提供ChatModel構建、結構化生成和續寫功能。
"""

from typing import Any, Dict, Type, Optional, AsyncGenerator
from pydantic import BaseModel
from sqlmodel import Session
from loguru import logger
import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage
from app.services.ai.generation.continuation_budget_runtime import (
    build_budget_hint_text,
    build_round_plan,
    count_text_units,
    estimate_required_call_count,
    normalize_word_control_mode,
    trim_generated_text,
)
from app.services.ai.generation.structured_runtime import (
    generate_structured_via_instruction_flow_model,
)
from app.schemas.ai import ContinuationRequest
from .chat_model_factory import build_chat_model
from .token_utils import calc_input_tokens, estimate_tokens
from .quota_manager import precheck_quota, record_usage


async def generate_structured(
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    output_type: Type[BaseModel],
    system_prompt: Optional[str] = None,
    deps: str = "",
    max_tokens: Optional[int] = None,
    max_retries: int = 3,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    track_stats: bool = True,
    use_instruction_flow: bool = False,
    return_logs: bool = False,
) -> BaseModel | Dict[str, Any]:
    """結構化輸出生成
    
    使用LangChain ChatModel的structured output能力。
    
    Args:
        session: 數據庫會話
        llm_config_id: LLM配置ID
        user_prompt: 用戶提示詞
        output_type: 輸出Pydantic模型類型
        system_prompt: 系統提示詞
        deps: 依賴項（預留）
        max_tokens: 最大token數
        max_retries: 最大重試次數
        temperature: 溫度參數
        timeout: 超時時間
        track_stats: 是否記錄統計
        
    Returns:
        結構化輸出對象
    """
    if use_instruction_flow:
        return await generate_structured_via_instruction_flow_model(
            session=session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=output_type,
            system_prompt=system_prompt,
            deps=deps,
            max_tokens=max_tokens,
            max_retries=max_retries,
            temperature=temperature,
            timeout=timeout,
            track_stats=track_stats,
            return_logs=return_logs,
        )

    native_result = await _generate_structured_native(
        session=session,
        llm_config_id=llm_config_id,
        user_prompt=user_prompt,
        output_type=output_type,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        max_retries=max_retries,
        temperature=temperature,
        timeout=timeout,
        track_stats=track_stats,
    )

    if return_logs:
        return {
            "result": native_result,
            "logs": [],
        }

    return native_result


async def generate_review(
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    track_stats: bool = True,
) -> str:
    """審核文本生成。"""
    if track_stats:
        ok, reason = precheck_quota(
            session, llm_config_id,
            calc_input_tokens(system_prompt, user_prompt),
            need_calls=1
        )
        if not ok:
            raise ValueError(f"LLM配額不足: {reason}")

    try:
        model = build_chat_model(
            session=session,
            llm_config_id=llm_config_id,
            temperature=temperature or 0.7,
            max_tokens=16384 if max_tokens is None else max_tokens,
            timeout=timeout or 150,
        )

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=user_prompt))

        logger.info(f"開始審核，提示詞: {system_prompt} \n\n {user_prompt}")
        response = await model.ainvoke(messages)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        else:
            text = "" if content is None else str(content)

        if not text.strip():
            raise ValueError("LLM返回了空響應")

        if track_stats:
            in_tokens = calc_input_tokens(system_prompt, user_prompt)
            out_tokens = estimate_tokens(text)
            record_usage(
                session, llm_config_id,
                in_tokens, out_tokens,
                calls=1, aborted=False
            )

        return text.strip()
    except asyncio.CancelledError:
        logger.info("[LangChain-Text] LLM調用被取消（CancelledError），立即中止。")
        if track_stats:
            in_tokens = calc_input_tokens(system_prompt, user_prompt)
            record_usage(
                session, llm_config_id,
                in_tokens, 0,
                calls=1, aborted=True
            )
        raise


async def _generate_structured_native(
    *,
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    output_type: Type[BaseModel],
    system_prompt: Optional[str],
    max_tokens: Optional[int],
    max_retries: int,
    temperature: Optional[float],
    timeout: Optional[float],
    track_stats: bool,
) -> BaseModel:
    """原生結構化輸出實現（LangChain with_structured_output）。"""

    # 配額預檢
    if track_stats:
        ok, reason = precheck_quota(
            session, llm_config_id,
            calc_input_tokens(system_prompt, user_prompt),
            need_calls=1
        )
        if not ok:
            raise ValueError(f"LLM配額不足: {reason}")

    last_exception = None
    for attempt in range(max_retries):
        try:
            model = build_chat_model(
                session=session,
                llm_config_id=llm_config_id,
                temperature=temperature or 0.7,
                max_tokens=16384 if max_tokens is None else max_tokens,
                timeout=timeout or 150,
            )

            structured_llm = model.with_structured_output(output_type)

            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=user_prompt))

            response = await structured_llm.ainvoke(messages)

            if response is None:
                raise ValueError("LLM返回了空響應")

            logger.info(f"[LangChain-Structured] response: {response}")

            if track_stats:
                in_tokens = calc_input_tokens(system_prompt, user_prompt)
                try:
                    out_text = (
                        response
                        if isinstance(response, str)
                        else json.dumps(response, ensure_ascii=False)
                    )
                except Exception:
                    out_text = str(response)
                out_tokens = estimate_tokens(out_text)
                record_usage(
                    session, llm_config_id,
                    in_tokens, out_tokens,
                    calls=1, aborted=False
                )

            return response

        except asyncio.CancelledError:
            logger.info("[LangChain-Structured] LLM調用被取消（CancelledError），立即中止，不再重試。")
            if track_stats:
                in_tokens = calc_input_tokens(system_prompt, user_prompt)
                record_usage(
                    session, llm_config_id,
                    in_tokens, 0,
                    calls=1, aborted=True
                )
            raise
        except Exception as e:
            last_exception = e
            logger.warning(
                f"[LangChain-Structured] 調用失敗，重試 {attempt + 1}/{max_retries}，llm_config_id={llm_config_id}: {e}"
            )

            if attempt < max_retries - 1:
                retry_delay = min(2 ** attempt, 4)
                logger.info(f"[LangChain-Structured] 等待 {retry_delay} 秒後重試...")
                await asyncio.sleep(retry_delay)

    logger.error(
        f"[LangChain-Structured] 調用在重試 {max_retries} 次後仍失敗，llm_config_id={llm_config_id}. Last error: {last_exception}"
    )
    raise ValueError(
        f"調用LLM服務失敗，已重試 {max_retries} 次: {str(last_exception)}"
    )


async def generate_continuation_streaming(
    session: Session,
    request: ContinuationRequest,
    system_prompt: str,
    track_stats: bool = True
) -> AsyncGenerator[str, None]:
    """續寫流式生成
    
    Args:
        session: 數據庫會話
        request: 續寫請求對象
        system_prompt: 系統提示詞（由外部傳入）
        track_stats: 是否記錄統計
        
    Yields:
        生成的文本片段
    """
    current_word_count = getattr(request, "existing_word_count", None)
    if current_word_count is None:
        current_word_count = count_text_units(getattr(request, "previous_content", ""))

    control_mode = normalize_word_control_mode(request)
    expected_rounds = estimate_required_call_count(request)
    if control_mode == "prompt_only" or expected_rounds <= 1:
        round_plan = build_round_plan(request, current_word_count, 1)
        async for chunk in _stream_continuation_single_round(
            session=session,
            request=request,
            system_prompt=system_prompt,
            round_plan=round_plan,
            track_stats=track_stats,
        ):
            yield chunk
        return

    current_content = request.previous_content or ""

    for round_index in range(1, expected_rounds + 1):
        round_plan = build_round_plan(request, current_word_count, round_index)
        round_request = request.model_copy(update={
            "previous_content": current_content,
            "existing_word_count": current_word_count,
            "word_control_mode": control_mode,
            "budget_round_hint": round_plan.round_index,
            "remaining_word_count_hint": round_plan.remaining_word_count,
            "is_final_round_hint": round_plan.is_final_round,
        })

        round_chunks: list[str] = []
        async for chunk in _stream_continuation_single_round(
            session=session,
            request=round_request,
            system_prompt=system_prompt,
            round_plan=round_plan,
            track_stats=track_stats,
        ):
            round_chunks.append(chunk)
            if getattr(request, "stream", False):
                yield chunk

        round_text = "".join(round_chunks)
        if not round_text.strip():
            logger.warning("續寫預算運行時在第 {} 輪拿到空輸出，提前結束。", round_index)
            break

        trim_result = trim_generated_text(round_text, round_plan)
        final_text = round_text if getattr(request, "stream", False) else trim_result.text
        if not final_text.strip():
            logger.warning("續寫預算運行時在第 {} 輪裁剪後爲空，提前結束。", round_index)
            break

        current_content = f"{current_content}{final_text}"
        current_word_count = count_text_units(current_content)

        if not getattr(request, "stream", False):
            for chunk in _chunk_text(final_text):
                yield chunk

        target_word_count = getattr(request, "target_word_count", None)
        if trim_result.trimmed and not getattr(request, "stream", False):
            logger.info("續寫預算運行時在第 {} 輪觸發句邊界收束。", round_index)
            break
        if target_word_count is not None and current_word_count >= target_word_count:
            break
        if round_plan.is_final_round:
            break


def _build_continuation_user_prompt(
    request: ContinuationRequest,
    round_plan,
) -> str:
    # 組裝用戶消息
    user_prompt_parts = []
    
    # 1. 添加上下文信息（引用上下文 + 事實子圖）
    context_info = (getattr(request, 'context_info', None) or '').strip()
    if context_info:
        # 檢測context_info是否已包含結構化標記
        has_structured_marks = any(
            mark in context_info 
            for mark in ['【引用上下文】', '【上文】', '【需要潤色', '【需要擴寫']
        )
        
        if has_structured_marks:
            # 已經是結構化的上下文，直接使用
            user_prompt_parts.append(context_info)
        else:
            # 未結構化的上下文（老格式），添加標記
            user_prompt_parts.append(f"【參考上下文】\n{context_info}")
    
    # 2. 添加已有章節內容（僅當previous_content非空時）
    previous_content = (request.previous_content or '').strip()
    if previous_content:
        user_prompt_parts.append(f"【已有章節內容】\n{previous_content}")
        
        # 續寫指令
        if getattr(request, 'append_continuous_novel_directive', True):
            user_prompt_parts.append("【指令】請接着上述內容繼續寫作，保持文風和劇情連貫。直接輸出小說正文。")
    else:
        # 新寫模式或潤色/擴寫模式（previous_content爲空）
        if getattr(request, 'append_continuous_novel_directive', True):
            if context_info and '【已有章節內容】' in context_info:
                user_prompt_parts.append("【指令】請接着上述內容繼續寫作，保持文風和劇情連貫。直接輸出小說正文。")
            else:
                user_prompt_parts.append("【指令】請開始創作新章節。直接輸出小說正文。")

    budget_hint = build_budget_hint_text(
        round_plan,
        getattr(request, "continuation_guidance", None),
        include_outline_boundary=getattr(request, "append_continuous_novel_directive", True),
    )
    if budget_hint:
        user_prompt_parts.append(budget_hint)

    return "\n\n".join(user_prompt_parts)


async def _stream_continuation_single_round(
    session: Session,
    request: ContinuationRequest,
    system_prompt: str,
    round_plan,
    track_stats: bool = True,
) -> AsyncGenerator[str, None]:
    user_prompt = _build_continuation_user_prompt(request, round_plan)

    # 限額預檢
    if track_stats:
        ok, reason = precheck_quota(
            session, request.llm_config_id,
            calc_input_tokens(system_prompt, user_prompt),
            need_calls=1
        )
        if not ok:
            raise ValueError(f"LLM配額不足: {reason}")

    # 使用LangChain ChatModel進行流式續寫
    model = build_chat_model(
        session=session,
        llm_config_id=request.llm_config_id,
        temperature=request.temperature or 0.7,
        max_tokens=round_plan.max_tokens,
        timeout=request.timeout or 64,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    logger.info(f"開始續寫，提示詞: {system_prompt} \n\n {user_prompt}")

    accumulated: str = ""
    pending_buffer: str = ""
    stream_with_hard_limit = bool(
        getattr(request, "stream", False)
        and round_plan.mode != "prompt_only"
        and not round_plan.is_final_round
        and round_plan.hard_word_limit
    )
    should_stop_current_round = False

    try:
        logger.debug("正在以LangChain ChatModel流式生成續寫內容")
        async for chunk in model.astream(messages):
            content = getattr(chunk, "content", None)
            if not content:
                continue

            if isinstance(content, str):
                delta = content
            elif isinstance(content, list):
                texts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                ]
                delta = "".join(texts)
            else:
                delta = str(content)

            if not delta:
                continue

            if stream_with_hard_limit:
                pending_buffer += delta
                emitted_text, pending_buffer, reached_limit = _flush_streaming_buffer_with_limit(
                    already_emitted=accumulated,
                    pending_text=pending_buffer,
                    hard_limit=round_plan.hard_word_limit or 0,
                )
                if emitted_text:
                    accumulated += emitted_text
                    yield emitted_text
                if reached_limit:
                    should_stop_current_round = True
                    break
                continue

            accumulated += delta
            yield delta

        if stream_with_hard_limit and not should_stop_current_round and pending_buffer:
            emitted_tail, pending_buffer, reached_limit = _flush_streaming_buffer_with_limit(
                already_emitted=accumulated,
                pending_text=pending_buffer,
                hard_limit=round_plan.hard_word_limit or 0,
                force_flush_tail=True,
            )
            if emitted_tail:
                accumulated += emitted_tail
                yield emitted_tail

    except asyncio.CancelledError:
        logger.info("流式LLM調用被取消（CancelledError），停止推送。")
        if track_stats:
            in_tokens = calc_input_tokens(system_prompt, user_prompt)
            out_tokens = estimate_tokens(accumulated)
            record_usage(
                session, request.llm_config_id,
                in_tokens, out_tokens,
                calls=1, aborted=True
            )
        return
    except Exception as e:
        logger.error(f"流式LLM調用失敗: {e}")
        raise

    # 正常結束後統計
    try:
        if track_stats:
            in_tokens = calc_input_tokens(system_prompt, user_prompt)
            out_tokens = estimate_tokens(accumulated)
            record_usage(
                session, request.llm_config_id,
                in_tokens, out_tokens,
                calls=1, aborted=False
            )
    except Exception as stat_e:
        logger.warning(f"記錄LLM流式統計失敗: {stat_e}")


async def _collect_continuation_single_round(
    session: Session,
    request: ContinuationRequest,
    system_prompt: str,
    round_plan,
    track_stats: bool = True,
) -> str:
    chunks: list[str] = []
    async for chunk in _stream_continuation_single_round(
        session=session,
        request=request,
        system_prompt=system_prompt,
        round_plan=round_plan,
        track_stats=track_stats,
    ):
        chunks.append(chunk)
    return "".join(chunks)


def _chunk_text(text: str, chunk_size: int = 240) -> list[str]:
    if not text:
        return []
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]


def _flush_streaming_buffer_with_limit(
    *,
    already_emitted: str,
    pending_text: str,
    hard_limit: int,
    force_flush_tail: bool = False,
) -> tuple[str, str, bool]:
    if not pending_text:
        return "", "", False

    emitted_parts: list[str] = []
    rest = pending_text

    while True:
        sentence_end = _find_first_sentence_boundary(rest)
        if sentence_end is None:
            break
        sentence = rest[:sentence_end]
        next_text = already_emitted + "".join(emitted_parts) + sentence
        if count_text_units(next_text) > hard_limit:
            return "".join(emitted_parts), rest, True
        emitted_parts.append(sentence)
        rest = rest[sentence_end:]

    if force_flush_tail and rest:
        next_text = already_emitted + "".join(emitted_parts) + rest
        if count_text_units(next_text) <= hard_limit:
            emitted_parts.append(rest)
            rest = ""
        elif not emitted_parts:
            truncated = _take_text_by_units(rest, hard_limit - count_text_units(already_emitted))
            return truncated, "", True
        else:
            return "".join(emitted_parts), rest, True

    return "".join(emitted_parts), rest, False


def _find_first_sentence_boundary(text: str) -> int | None:
    for idx, char in enumerate(text):
        if char in "。！？!?…\n":
            return idx + 1
    return None


def _take_text_by_units(text: str, limit_units: int) -> str:
    if limit_units <= 0:
        return ""
    units = 0
    out_chars: list[str] = []
    for char in text:
        if not char.isspace():
            units += 1
        if units > limit_units:
            break
        out_chars.append(char)
    return "".join(out_chars).rstrip()
