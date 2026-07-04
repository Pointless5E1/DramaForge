"""靈感助手服務

提供基於 LangChain 的工具調用與流式對話能力。
React 文本協議模式與 Workflow Agent 共享核心實現。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from sqlmodel import Session

from app.schemas.ai import AssistantChatRequest
from app.services import llm_config_service
from app.services.ai.core.chat_model_factory import build_chat_model
from app.services.ai.core.quota_manager import precheck_quota, record_usage
from app.services.ai.core.react_text_agent import stream_chat_with_react_protocol
from app.services.ai.core.tool_agent_stream import stream_agent_with_tools
from app.services.ai.core.token_utils import calc_input_tokens, estimate_tokens
from .tools import (
    ASSISTANT_TOOL_DESCRIPTIONS,
    ASSISTANT_TOOL_REGISTRY,
    ASSISTANT_TOOLS,
    AssistantDeps,
    set_assistant_deps,
)


MAX_REACT_STEPS = 100


ASSISTANT_REACT_PROTOCOL_INSTRUCTIONS = """
你處於寫作助手 React-Tool 模式。

工具調用格式（嚴格）：
<Action>{"tool":"工具名","args":{"參數名":參數值}}</Action>

執行規則：
1) 只能調用“可用工具列表”裏的工具，禁止調用任何 wf_* 工具。
2) 用戶要求創建/修改卡片內容時，必須通過工具執行（如 create_card / update_card / modify_card_field / replace_field_text / propose_card_text_patches）。
3) 每一輪最多輸出一個 Action 塊；工具執行結果會以 Observation 返回，再決定下一步。
4) 若參數中包含長文本，必須輸出合法 JSON（換行與引號要正確轉義）。
5) 不要輸出僞調用文本（例如 tool(...)）。
6) 當用戶要求對正文提出多條可審閱修改建議時，必須調用 propose_card_text_patches，不要調用 update_card、modify_card_field、replace_field_text 或 replace_card_text_by_lines 直接改正文。
7) propose_card_text_patches 的每條 patches 項必須包含 old_text 和 new_text；可以同時提供 start_line/end_line、context_before/context_after 輔助前端重新定位。
8) 多條正文建議必須作爲一個批次返回，讓前端逐條顯示“建議 #當前 / 共 N”，由用戶接受或拒絕。
""".strip()


ASSISTANT_TEXT_PATCH_TOOL_INSTRUCTIONS = """
正文批量修改建議規則：
- 當用戶要求靈感助手提出正文修改建議，尤其是多條建議、逐條確認、複用右鍵潤色/擴寫預覽機制時，必須使用 propose_card_text_patches。
- propose_card_text_patches 只提交建議給當前正文編輯器預覽，不直接寫數據庫，也不直接改正文。
- 不要爲這類正文建議使用 update_card、modify_card_field、replace_field_text 或 replace_card_text_by_lines。
- 每條建議必須包含 old_text 和 new_text；old_text 應儘量是當前正文中的精確原文片段。
- 建議同時提供 start_line/end_line、context_before/context_after，方便用戶接受前後重新定位，避免前面建議被接受後造成後續錯位。
""".strip()


def _with_assistant_tool_guidance(system_prompt: str) -> str:
    base = system_prompt or ""
    if ASSISTANT_TEXT_PATCH_TOOL_INSTRUCTIONS in base:
        return base
    return base + "\n\n" + ASSISTANT_TEXT_PATCH_TOOL_INSTRUCTIONS


def _should_fallback_to_plain_chat(session: Session, llm_config_id: int) -> bool:
    cfg = llm_config_service.get_llm_config(session, llm_config_id)
    if not cfg:
        return False
    transport = llm_config_service.resolve_transport_settings(
        provider=cfg.provider,
        api_base=cfg.api_base,
        base_url=cfg.base_url,
        api_protocol=getattr(cfg, "api_protocol", None),
        custom_request_path=getattr(cfg, "custom_request_path", None),
        models_path=getattr(cfg, "models_path", None),
        user_agent=getattr(cfg, "user_agent", None),
    )
    return bool(transport["use_responses_api"] and transport["provider"] == "openai_compatible")


async def stream_chat_plain(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    final_user_prompt = "\n\n".join(
        part for part in [request.context_info or "", request.user_prompt or ""] if part
    ) or "(User input is empty; assistant should clarify intent first.)"

    ok, reason = precheck_quota(
        session,
        request.llm_config_id,
        calc_input_tokens(system_prompt, final_user_prompt),
        need_calls=1,
    )
    if not ok:
        raise ValueError(f"LLM配額不足: {reason}")

    model = build_chat_model(
        session=session,
        llm_config_id=request.llm_config_id,
        temperature=request.temperature or 0.6,
        max_tokens=16384 if request.max_tokens is None else request.max_tokens,
        timeout=request.timeout or 90,
        thinking_enabled=getattr(request, "thinking_enabled", None),
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=final_user_prompt),
    ]

    accumulated_text = ""
    reasoning_accumulated = ""
    try:
        async for chunk in model.astream(messages):
            content_blocks = getattr(chunk, "content_blocks", None)
            delta_text = ""
            if isinstance(content_blocks, list):
                reasoning_parts: list[str] = []
                text_parts: list[str] = []
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type")
                    if block_type == "text":
                        text_parts.append(str(block.get("text") or ""))
                    elif block_type == "reasoning":
                        text = str(block.get("reasoning") or block.get("text") or "")
                        if text:
                            reasoning_parts.append(text)
                delta_text = "".join(text_parts)
                reasoning_delta = "".join(reasoning_parts)
                if reasoning_delta:
                    reasoning_accumulated += reasoning_delta
                    yield {"type": "reasoning", "data": {"text": reasoning_delta, "delta": True}}
            else:
                content = getattr(chunk, "content", None)
                if isinstance(content, str):
                    delta_text = content

            if delta_text:
                accumulated_text += delta_text
                yield {"type": "token", "data": {"text": delta_text, "delta": True}}
    except asyncio.CancelledError:
        record_usage(
            session,
            request.llm_config_id,
            calc_input_tokens(system_prompt, final_user_prompt),
            estimate_tokens(accumulated_text + reasoning_accumulated),
            calls=1,
            aborted=True,
        )
        raise

    record_usage(
        session,
        request.llm_config_id,
        calc_input_tokens(system_prompt, final_user_prompt),
        estimate_tokens(accumulated_text + reasoning_accumulated),
        calls=1,
        aborted=False,
    )


async def stream_chat_with_react(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    deps = AssistantDeps(session=session, project_id=request.project_id)
    async for event in stream_chat_with_react_protocol(
        session=session,
        llm_config_id=request.llm_config_id,
        system_prompt=system_prompt,
        context_info=request.context_info or "",
        user_prompt=request.user_prompt or "",
        tool_registry=ASSISTANT_TOOL_REGISTRY,
        tool_descriptions=ASSISTANT_TOOL_DESCRIPTIONS,
        set_deps=set_assistant_deps,
        deps=deps,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        timeout=request.timeout,
        thinking_enabled=getattr(request, "thinking_enabled", None),
        max_steps=MAX_REACT_STEPS,
        protocol_instructions=ASSISTANT_REACT_PROTOCOL_INSTRUCTIONS,
        log_tag="Assistant-React",
    ):
        yield event


async def stream_chat_with_tools(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """標準模式：複用共享 Tool Agent 流式核心。"""
    parts: list[str] = []
    if request.context_info:
        parts.append(request.context_info)
    if request.user_prompt:
        parts.append("\nUser: " + request.user_prompt)
    final_user_prompt = "\n\n".join(parts) if parts else "(User input is empty; assistant should clarify intent first.)"

    enable_summarization = getattr(request, "context_summarization_enabled", None)
    max_tokens_before_summary = (
        int(request.context_summarization_threshold)
        if getattr(request, "context_summarization_threshold", None)
        else 8192
    )

    deps = AssistantDeps(session=session, project_id=request.project_id)

    async for event in stream_agent_with_tools(
        session=session,
        llm_config_id=request.llm_config_id,
        system_prompt=system_prompt,
        user_prompt=final_user_prompt,
        tools=ASSISTANT_TOOLS,
        set_deps=set_assistant_deps,
        deps=deps,
        temperature=request.temperature or 0.6,
        max_tokens=16384 if request.max_tokens is None else request.max_tokens,
        timeout=request.timeout or 90,
        thinking_enabled=getattr(request, "thinking_enabled", None),
        enable_summarization=bool(enable_summarization),
        max_tokens_before_summary=max_tokens_before_summary,
        log_tag="LangChain+Agent",
    ):
        yield event


async def generate_assistant_chat_streaming(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
    track_stats: bool = True,
) -> AsyncGenerator[str, None]:
    """靈感助手專用流式對話生成（結構化事件流協議）。"""
    _ = track_stats
    manual_react_mode = getattr(request, "react_mode_enabled", None)
    cfg = llm_config_service.get_llm_config(session, request.llm_config_id)
    recommended_mode = (getattr(cfg, "recommended_assistant_mode", None) or "auto").strip().lower() if cfg else "auto"
    if manual_react_mode is None:
        react_enabled = recommended_mode == "react"
        recommended_plain_chat = recommended_mode == "plain"
    else:
        react_enabled = bool(manual_react_mode)
        recommended_plain_chat = False
    fallback_plain_chat = _should_fallback_to_plain_chat(session, request.llm_config_id)
    plain_chat_enabled = fallback_plain_chat or recommended_plain_chat
    logger.info(
        "[LangChain] generate_assistant_chat_streaming: 使用{}模式，模型id:{}",
        "純對話" if plain_chat_enabled else ("React" if react_enabled else "標準"),
        request.llm_config_id
    )

    if plain_chat_enabled:
        engine = stream_chat_plain
        effective_system_prompt = system_prompt
    else:
        engine = stream_chat_with_react if react_enabled else stream_chat_with_tools
        effective_system_prompt = _with_assistant_tool_guidance(system_prompt)
    has_visible_output = False
    has_tool_events = False

    try:
        async for evt in engine(
            session=session,
            request=request,
            system_prompt=effective_system_prompt,
        ):
            evt_type = evt.get("type") if isinstance(evt, dict) else None
            evt_data = evt.get("data") if isinstance(evt, dict) else None

            if evt_type in ("token", "reasoning") and isinstance(evt_data, dict):
                evt_text = str(evt_data.get("text") or "")
                if evt_text.strip():
                    has_visible_output = True
            elif evt_type in ("tool_start", "tool_end", "tool_summary"):
                has_tool_events = True

            yield json.dumps(evt, ensure_ascii=False)

        if not has_visible_output:
            fallback_text = (
                "已執行工具調用，請查看工具結果。"
                if has_tool_events
                else "本輪未產生可見回覆文本，請重試或調整提問。"
            )
            yield json.dumps(
                {
                    "type": "token",
                    "data": {"text": fallback_text, "delta": False},
                },
                ensure_ascii=False,
            )
    except asyncio.CancelledError:
        logger.info("[LangChain] 助手調用被取消（CancelledError）")
        return
    except Exception as exc:
        logger.error("[LangChain] 靈感助手生成失敗: {}", exc)
        error_event = {
            "type": "error",
            "data": {"error": str(exc)},
        }
        yield json.dumps(error_event, ensure_ascii=False)
        raise
