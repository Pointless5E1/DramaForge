"""結構化生成節點

利用指令流生成服務（Instruction Generator）實現結構化數據的生成。
支持自動校驗、自動修復和 Pydantic 模型輸出。
"""

from typing import Any, Dict, Optional, List, AsyncIterator, TYPE_CHECKING
from pydantic import BaseModel, Field
from loguru import logger

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from ...registry import register_node
from ..base import BaseNode
from app.services import prompt_service
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.core.llm_service import generate_structured
from app.services.schema_service import compose_full_schema
from app.db.models import CardType
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from sqlmodel import select


class StructuredGenerateInput(BaseModel):
    """結構化生成輸入"""
    user_prompt: str = Field(..., description="用戶提示詞")
    llm_config_id: int = Field(..., description="LLM配置ID", json_schema_extra={"x-component": "LLMSelect"})
    response_model_id: str = Field(..., description="響應模型", json_schema_extra={"x-component": "ResponseModelSelect"})
    context: Optional[Dict[str, Any]] = Field(None, description="上下文數據/初始數據")
    schema_extra: Optional[Dict[str, Any]] = Field(None, description="額外的 Schema 定義 (可選)")
    max_retry: int = Field(3, description="最大重試/修復次數")
    prompt_template: Optional[str] = Field(None, description="提示詞模版名稱(可選)", json_schema_extra={"x-component": "PromptSelect"})
    temperature: float = Field(0.7, description="溫度參數")
    max_tokens: Optional[int] = Field(None, description="最大token數")
    timeout: int = Field(60, description="超時時間(秒)")
    fail_soft: bool = Field(False, description="失敗時是否降級返回空結果而非拋錯")
    use_instruction_flow: bool = Field(
        False,
        description="是否使用指令流模式（複雜結構推薦開啓，簡單結構可關閉以使用原生結構化）",
    )


class StructuredGenerateOutput(BaseModel):
    """結構化生成輸出"""
    data: Dict[str, Any] = Field(..., description="生成的結構化數據")
    logs: List[Dict[str, Any]] = Field(..., description="生成過程日誌")

@register_node
class StructuredGenerateNode(BaseNode[StructuredGenerateInput, StructuredGenerateOutput]):
    """結構化生成節點"""
    
    node_type = "AI.StructuredGenerate"
    category = "ai"
    label = "結構化生成"
    description = "生成符合指定 Schema 的結構化數據 (支持自動修復)"
    
    input_model = StructuredGenerateInput
    output_model = StructuredGenerateOutput

    @classmethod
    def get_output_schema_contract(
        cls,
        config: Dict[str, Any],
        session=None,
    ) -> Optional[Dict[str, Any]]:
        """聲明輸出 `data` 字段的 schema 契約。

        契約格式：
        {
            "kind": "structured_output",
            "schema_id": "角色卡",
            "data_path": "data"
        }
        """
        model_id = config.get("response_model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            return None

        return {
            "kind": "structured_output",
            "schema_id": model_id.strip(),
            "data_path": "data",
        }

    async def execute(
        self,
        inputs: StructuredGenerateInput
    ) -> AsyncIterator[StructuredGenerateOutput]:
        """執行生成"""
        session = self.context.session
        user_prompt = inputs.user_prompt
        current_data = inputs.context or {}
        
        # 1. 獲取目標 Schema
        target_schema = self._get_schema(session, inputs)
        if not target_schema:
            raise ValueError(f"無法加載模型 Schema: {inputs.response_model_id}")
            
        # 2. 準備參數
        # 組裝完整 Schema (處理 $ref)
        full_schema = compose_full_schema(session, target_schema)

        # 加載提示詞模板（如果配置了）
        card_prompt_content = None
        if inputs.prompt_template:
            prompt = prompt_service.get_prompt_by_name(session, inputs.prompt_template)
            if prompt and prompt.template:
                card_prompt_content = prompt.template
        
        logger.info(f"[AI.Structured] 開始生成: model={inputs.response_model_id}")

        # 3. 調用指令流聚合生成（節點層保持非流式）
        try:
            dynamic_output = build_model_from_json_schema(
                f"WorkflowStructured_{inputs.response_model_id}",
                full_schema,
            )
            generated = await generate_structured(
                session=session,
                llm_config_id=inputs.llm_config_id,
                user_prompt=user_prompt,
                output_type=dynamic_output,
                system_prompt=card_prompt_content,
                deps="",
                temperature=inputs.temperature,
                max_tokens=inputs.max_tokens,
                timeout=inputs.timeout,
                max_retries=inputs.max_retry,
                use_instruction_flow=inputs.use_instruction_flow,
                track_stats=True,
                return_logs=True,
            )
        except Exception as e:
            if inputs.fail_soft:
                logger.warning(
                    f"[AI.Structured] 生成失敗但啓用 fail_soft，返回降級結果: model={inputs.response_model_id}, err={e}"
                )
                yield StructuredGenerateOutput(data=current_data or {}, logs=[{"type": "error", "text": str(e)}])
                return
            logger.exception(f"[AI.Structured] 執行異常")
            raise

        result_data = generated["result"].model_dump(mode="json")

        yield StructuredGenerateOutput(
            data=result_data,
            logs=generated["logs"],
        )

    def _get_schema(self, session, inputs: StructuredGenerateInput) -> Optional[Dict[str, Any]]:
        """根據配置獲取 JSON Schema
        """
        
        stmt = select(CardType).where(CardType.name == inputs.response_model_id)
        ct = session.exec(stmt).first()
        if ct and ct.json_schema:
            return ct.json_schema

        builtin_model = RESPONSE_MODEL_MAP.get(inputs.response_model_id)
        if builtin_model is not None:
            return builtin_model.model_json_schema(ref_template="#/$defs/{model}")
                
        return None
