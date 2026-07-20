from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session
from app.db.session import get_session
from app.schemas.ai import ContinuationRequest, ContinuationResponse, GeneralAIRequest
from app.schemas.response import ApiResponse
from app.services import prompt_service, llm_config_service

from app.services.schema_service import compose_full_schema
from app.utils.stream_utils import wrap_sse_stream
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from typing import Type, Dict, Any, List
import json

from app.db.models import Card, CardType
from app.utils.schema_utils import filter_schema_for_ai

# 引入知識庫
from app.services.knowledge_service import KnowledgeService
from app.schemas.entity import DYNAMIC_INFO_TYPES
from app.schemas import entity as entity_schemas
from app.core import emit_event
from app.services.ai.core import llm_service
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.generation.continuation_context_service import (
    enrich_continuation_context_info,
    enrich_relation_graph_context_info,
)
from app.services.ai.generation.continuation_budget_runtime import estimate_required_call_count
from app.services.ai.generation.instruction_validator import validate_instruction, apply_instruction
from app.services.ai.generation.instruction_generator import generate_instruction_stream
from app.services.ai.generation.prompt_builder import build_instruction_system_prompt
from app.schemas.instruction import InstructionGenerateRequest
from app.schemas.wizard import Tags as _Tags
from loguru import logger

router = APIRouter()

# 響應模型映射表（內置）
from app.schemas.response_registry import RESPONSE_MODEL_MAP


@router.get("/schemas", response_model=Dict[str, Any], summary="獲取所有輸出模型的JSON Schema（僅內置）")
def get_all_schemas(session: Session = Depends(get_session)):
    """返回內置 pydantic 模型的 schema 聚合，鍵爲模型名稱。"""
    all_definitions: Dict[str, Any] = {}

    # 1) 內置 pydantic 模型
    for name, model_class in RESPONSE_MODEL_MAP.items():
        schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
        if '$defs' in schema:
            all_definitions.update(schema['$defs'])
            del schema['$defs']
        all_definitions[name] = schema

    # 動態修復 CharacterCard.dynamic_info 的屬性
    try:
        cc = all_definitions.get('CharacterCard')
        if isinstance(cc, dict):
            props = (cc.get('properties') or {})
            if 'dynamic_info' in props:
                item_schema = {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "info": {"type": "string"},
                        "weight": {"type": "number"}
                    },
                    "required": ["id", "info", "weight"]
                }
                enum_values = DYNAMIC_INFO_TYPES
                props['dynamic_info'] = {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        ev: {"type": "array", "items": item_schema} for ev in enum_values
                    },
                    "description": "角色動態信息，按類別分組的數組（鍵爲中文枚舉值）"
                }
                cc['properties'] = props
                all_definitions['CharacterCard'] = cc
    except Exception:
        pass

    # 2) 注入 entity 動態信息相關模型（用於前端解析 $ref: DynamicInfo 等）
    try:
        entity_models = [
            entity_schemas.DynamicInfoItem,
            entity_schemas.DynamicInfo,
            entity_schemas.UpdateDynamicInfo,
        ]
        for mdl in entity_models:
            sch = mdl.model_json_schema(ref_template="#/$defs/{model}")
            if '$defs' in sch:
                all_definitions.update(sch['$defs'])
                del sch['$defs']
            all_definitions[mdl.__name__] = sch
    except Exception:
        pass

    return all_definitions

@router.get("/content-models", response_model=List[str], summary="獲取所有可用輸出模型名稱")
def get_content_models(session: Session = Depends(get_session)):
    # 僅返回內置模型名稱
    return list(RESPONSE_MODEL_MAP.keys())


@router.get("/config-options", summary="獲取AI生成配置選項")
async def get_ai_config_options(session: Session = Depends(get_session)):
    """獲取AI生成時可用的配置選項"""
    try:
        # 獲取所有LLM配置
        llm_configs = llm_config_service.get_llm_configs(session)
        # 獲取所有提示詞
        prompts = prompt_service.get_prompts(session)
        # 響應模型僅內置
        response_models = get_content_models(session)
        return ApiResponse(data={
            "llm_configs": [{"id": config.id, "display_name": config.display_name or config.model_name} for config in llm_configs],
            "prompts": [{
                "id": prompt.id,
                "name": prompt.name,
                "description": prompt.description,
                "built_in": getattr(prompt, 'built_in', False),
                "is_review_prompt": getattr(prompt, 'is_review_prompt', False),
            } for prompt in prompts],
            "available_tasks": [],
            "response_models": response_models
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取配置選項失敗: {str(e)}")

@router.get("/prompts/render", summary="渲染並注入知識庫的提示詞模板")
async def render_prompt_with_knowledge(name: str, session: Session = Depends(get_session)):
    p = prompt_service.get_prompt_by_name(session, name)
    if not p or not p.template:
        raise HTTPException(status_code=404, detail=f"未找到提示詞: {name}")
    try:
        text = prompt_service.inject_knowledge(session, str(p.template))
        return ApiResponse(data={"text": text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"渲染失敗: {e}")

@router.post("/generate", summary="通用AI生成接口")
async def generate_ai_content(
    request: GeneralAIRequest = Body(...),
    session: Session = Depends(get_session),
):
    """
    通用的AI內容生成端點：前端必須提供 response_model_schema。
    """
    # 基本參數校驗：input/llm_config_id/prompt_name/response_model_schema 必填
    if not request.input or not request.llm_config_id or not request.prompt_name:
        raise HTTPException(status_code=400, detail="缺少必要的生成參數: input, llm_config_id 或 prompt_name")
    if request.response_model_schema is None:
        raise HTTPException(status_code=400, detail="請提供 response_model_schema")

    # 解析響應模型（僅動態 schema）
    try:
        # 完整 Schema 組裝：內置 defs + CardType defs
        composed = compose_full_schema(session, request.response_model_schema)
        # 基於 x-ai-exclude 過濾字段
        schema_for_prompt = filter_schema_for_ai(composed) if request.exclude_ai_fields else composed
        # 動態構建 Pydantic 模型
        resp_model = build_model_from_json_schema('DynamicResponseModel', schema_for_prompt or composed)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"動態創建模型失敗: {e}")

    # 獲取提示詞
    prompt = prompt_service.get_prompt_by_name(session, request.prompt_name)
    if not prompt:
        raise HTTPException(status_code=400, detail=f"未找到提示詞名稱: {request.prompt_name}")

    # 注入知識庫
    prompt_template = prompt_service.inject_knowledge(session, prompt.template or '')

    # System Prompt：攜帶 JSON Schema
    schema_json = json.dumps(schema_for_prompt if schema_for_prompt is not None else resp_model.model_json_schema(), indent=2, ensure_ascii=False)
    system_prompt = (
        f"{prompt_template}\n\n"
        f"```json\n{schema_json}\n```"
    )

    user_prompt = request.input['input_text']
    deps_str = request.deps or ""

    try:
        result = await llm_service.generate_structured(
            session=session,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            output_type=resp_model,
            llm_config_id=request.llm_config_id, 
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            timeout=request.timeout,
            deps=deps_str,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 觸發 OnGenerateFinish（若能定位 card）
    card: Card | None = None
    try:
        card_id = None
        if isinstance(request.input, dict):
            card_id = request.input.get('card_id')
        if card_id:
            card = session.get(Card, int(card_id))
        project_id = None
        if isinstance(request.input, dict):
            project_id = request.input.get('project_id') or (card.project_id if card else None)
        emit_event("generate.finished", {
            "session": session,
            "card": card,
            "project_id": int(project_id) if project_id else (card.project_id if card else None)
        })
    except Exception:
        pass
    return ApiResponse(data=result)

@router.post("/generate/continuation", 
             response_model=ApiResponse[ContinuationResponse], 
             summary="續寫正文",
             responses={
                 200: {
                     "content": {
                         "application/json": {},
                         "text/event-stream": {}
                     },
                     "description": "成功返回續寫結果或事件流"
                 }
             })
async def generate_continuation(
    request: ContinuationRequest,
    session: Session = Depends(get_session),
):
    try:
        # 強制從 prompt_name 讀取模板作爲 system prompt
        if not request.prompt_name:
            raise HTTPException(status_code=400, detail="續寫必須指定 prompt_name")
        p = prompt_service.get_prompt_by_name(session, request.prompt_name)
        if not p or not p.template:
            raise HTTPException(status_code=400, detail=f"未找到提示詞名稱: {request.prompt_name}")
        # 注入知識庫
        system_prompt = prompt_service.inject_knowledge(session, str(p.template))


        request.context_info = enrich_continuation_context_info(session, request)
        

        if request.stream:
            # 先做一次配額預檢，避免流式過程中才拋錯
            expected_calls = estimate_required_call_count(request)
            ok, reason = llm_config_service.can_consume(session, request.llm_config_id, 0, 0, expected_calls)
            if not ok:
                raise HTTPException(status_code=400, detail=f"LLM 配額不足：{reason}")
            async def _stream_and_trigger():
                content_acc = []
                async for chunk in llm_service.generate_continuation_streaming(session, request, system_prompt):
                    content_acc.append(chunk)
                    yield chunk
                try:
                    # 續寫結束後觸發
                    emit_event("generate.finished", {
                        "session": session,
                        "card": None,
                        "project_id": request.project_id
                    })
                except Exception:
                    pass
            return StreamingResponse(wrap_sse_stream(_stream_and_trigger()), media_type="text/event-stream")
        else:
            # 非流式模式：收集所有內容
            content_parts = []
            async for chunk in llm_service.generate_continuation_streaming(session, request, system_prompt):
                content_parts.append(chunk)
            result = "".join(content_parts)
            try:
                emit_event("generate.finished", {
                    "session": session,
                    "card": None,
                    "project_id": request.project_id
                })
            except Exception:
                pass
            return ApiResponse(data=ContinuationResponse(content=result))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/models/tags", response_model=_Tags, summary="導出 Tags 模型（用於類型生成）")
def export_tags_model():
    return _Tags()


# ==================== 指令流生成端點 ====================


@router.post("/generate/stream", summary="指令流式生成端點")
async def generate_with_instruction_stream(
    request: InstructionGenerateRequest,
    session: Session = Depends(get_session),
):
    """
    指令流式生成端點
    
    實時返回 LLM 生成的指令流，前端逐條執行並更新 UI。
    支持自動校驗和修復，用戶可以在生成過程中與 AI 交互。
    """
    async def event_generator():
        try:
            # 1. 組裝完整 Schema（注入 $defs）
            full_schema = compose_full_schema(session, request.response_model_schema)
            
            # 2. 加載卡片任務提示詞（如果提供了名稱）
            card_prompt_content = None
            if request.prompt_template:
                from app.services import prompt_service
                from loguru import logger
                prompt = prompt_service.get_prompt_by_name(session, request.prompt_template)
                if prompt and prompt.template:
                    card_prompt_content = prompt_service.inject_knowledge(session, str(prompt.template))
                    logger.info(f"[卡片生成] 加載提示詞模板: {request.prompt_template}, 長度: {len(card_prompt_content)}")
                else:
                    logger.warning(f"[卡片生成] 未找到提示詞模板: {request.prompt_template}")
            
            # 3. 構建 System Prompt（卡片任務 + 指令規範 + Schema）
            system_prompt = build_instruction_system_prompt(
                session=session,
                schema=full_schema,
                card_prompt=card_prompt_content
            )

            pipeline = None
            if request.generation_config and request.generation_config.custom:
                pipeline = request.generation_config.custom.get("pipeline")

            if pipeline == "screenplay_text_then_normalize":
                if not card_prompt_content:
                    raise ValueError("劇本正文文字生成缺少有效提示詞")
                normalizer = prompt_service.get_prompt_by_name(session, "劇本片段正文規範化")
                if not normalizer or not normalizer.template:
                    raise ValueError("未找到提示詞名稱: 劇本片段正文規範化")

                request.context_info = enrich_relation_graph_context_info(
                    session,
                    context_info=request.context_info,
                    project_id=request.project_id,
                    volume_number=request.volume_number,
                    chapter_number=request.chapter_number,
                    participants=request.participants,
                    log_label="劇本正文上下文",
                )

                task_parts = []
                if request.context_info:
                    task_parts.append(f"## 相關上下文\n\n{request.context_info}")
                task_parts.append(f"## 用戶要求\n\n{request.user_prompt or '請生成完整的劇本片段正文'}")
                existing_text = request.current_data.get("screenplay_text") if request.current_data else None
                if existing_text:
                    task_parts.append(
                        "## 目前劇本文字\n\n"
                        f"{existing_text}\n\n"
                        "請依照用戶要求產生完整修訂版；輸出必須包含未修改與已修改的全部正文。"
                    )

                yield f"data: {json.dumps({'type': 'thinking', 'text': '正在生成完整劇本文字'}, ensure_ascii=False)}\n\n"
                screenplay_text = await llm_service.generate_review(
                    session=session,
                    llm_config_id=request.llm_config_id,
                    user_prompt="\n\n".join(task_parts),
                    system_prompt=card_prompt_content,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    timeout=request.timeout,
                )

                yield f"data: {json.dumps({'type': 'thinking', 'text': '正文完成，正在依劇本規範整理段落'}, ensure_ascii=False)}\n\n"
                response_model = build_model_from_json_schema("ScreenplayNormalizedResponse", full_schema)
                normalized = await llm_service.generate_structured(
                    session=session,
                    llm_config_id=request.llm_config_id,
                    user_prompt=f"請規範化以下完整劇本文字：\n\n{screenplay_text}",
                    system_prompt=prompt_service.inject_knowledge(session, str(normalizer.template)),
                    output_type=response_model,
                    max_tokens=request.max_tokens,
                    temperature=0.1,
                    timeout=request.timeout,
                )
                final_data = normalized.model_dump(mode="json")
                if screenplay_text.strip() and not final_data.get("blocks"):
                    raise ValueError("劇本正文規範化未產生任何 blocks")
                yield f"data: {json.dumps({'type': 'done', 'success': True, 'message': '劇本文字已生成並完成規範化', 'final_data': final_data}, ensure_ascii=False)}\n\n"
                return
            
            # 4. 調用指令流生成服務
            async for event in generate_instruction_stream(
                session=session,
                llm_config_id=request.llm_config_id,
                user_prompt=request.user_prompt,
                system_prompt=system_prompt,
                schema=full_schema,
                current_data=request.current_data,
                conversation_context=request.conversation_context,
                context_info=request.context_info,
                temperature=request.temperature or 0.7,
                max_tokens=request.max_tokens,
                timeout=request.timeout or 150,
            ):
                # 5. 發送 SSE 事件（格式：data: {json}\n\n）
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            logger.error(f"指令流生成失敗: {e}", exc_info=True)
            error_event = {
                "type": "error",
                "text": f"生成失敗: {str(e)}"
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    ) 
