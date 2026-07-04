"""多智能體辯論節點

在單個節點內實現通過兩個不同配置的智能體進行多輪辯論。
支持 CoT (Chain of Thought) 思維鏈，Thought 內容互不可見。
支持進度報告和斷點續傳。
"""

from typing import Any, Dict, List, Optional, AsyncIterator, TYPE_CHECKING
from pydantic import BaseModel, Field
from loguru import logger

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from ...registry import register_node
from ..base import BaseNode
from app.services.ai.core.llm_service import generate_structured


# ============================================================
# Helper Models
# ============================================================

class DebateMessage(BaseModel):
    """辯論消息結構 (強制CoT)"""
    thought: str = Field(..., description="內心的思考過程、戰術分析（對方不可見）")
    content: str = Field(..., description="公開的發言內容（對方可見）")


# ============================================================
# Input/Output Models
# ============================================================

class DebateInput(BaseModel):
    """辯論節點輸入"""
    topic: str = Field(..., description="辯論主題")
    context: Optional[str] = Field(None, description="背景資料/上下文")
    max_rounds: int = Field(3, description="最大辯論輪數 (A->B 爲一輪)", ge=1, le=20)
    
    # Agent 1 配置
    agent_1_name: str = Field("正方", description="角色1名稱")
    agent_1_system_prompt: str = Field("", description="角色1人設提示詞", json_schema_extra={"x-component": "Textarea"})
    agent_1_llm_config: int = Field(..., description="角色1 LLM配置", json_schema_extra={"x-component": "LLMSelect"})
    
    # Agent 2 配置
    agent_2_name: str = Field("反方", description="角色2名稱")
    agent_2_system_prompt: str = Field("", description="角色2人設提示詞", json_schema_extra={"x-component": "Textarea"})
    agent_2_llm_config: int = Field(..., description="角色2 LLM配置", json_schema_extra={"x-component": "LLMSelect"})
    
    temperature: float = Field(0.7, description="生成溫度", ge=0.0, le=2.0)
    max_tokens: int = Field(2000, description="單次回覆最大Token")


class DebateOutput(BaseModel):
    """辯論節點輸出"""
    summary: str = Field(..., description="辯論總結/最終發言")
    history: List[Dict[str, Any]] = Field(..., description="公開對話歷史 (不含思考)，格式爲[{'role': '正方'/'反方', 'content': '發言內容'}, ...]，如需展示，建議進行格式處理")
    full_log: List[Dict[str, Any]] = Field(..., description="完整日誌 (包含思考)")
    total_rounds: int = Field(..., description="實際完成的辯論輪數")


# ============================================================
# Node Implementation
# ============================================================

@register_node
class DebateNode(BaseNode[DebateInput, DebateOutput]):
    """多智能體辯論節點"""
    
    node_type = "AI.Debate"
    category = "ai"
    label = "多智能體辯論"
    description = "兩個智能體針對特定主題進行多輪辯論 (支持CoT、進度報告、斷點續傳)"
    
    input_model = DebateInput
    output_model = DebateOutput

    async def execute(self, input_data: DebateInput) -> AsyncIterator:
        """執行辯論循環（串行處理，支持斷點續傳）"""
        from ...engine.async_executor import ProgressEvent
        
        # 1. 檢查點恢復
        checkpoint = getattr(self.context, 'checkpoint', None)
        completed_rounds = checkpoint.get('completed_rounds', 0) if checkpoint else 0
        history_public = checkpoint.get('history_public', []) if checkpoint else []
        full_log = checkpoint.get('full_log', []) if checkpoint else []
        
        # 恢復對話上下文（簡化：只保存消息內容）
        agent_1_context = checkpoint.get('agent_1_context', []) if checkpoint else []
        agent_2_context = checkpoint.get('agent_2_context', []) if checkpoint else []
        
        # 初始化（僅首次）
        if completed_rounds == 0:
            user_input = f"辯論主題：{input_data.topic}"
            if input_data.context:
                user_input += f"\n\n背景資料：\n{input_data.context}"
                
            logger.info(f"[AI.Debate] 開始辯論: {input_data.agent_1_name} vs {input_data.agent_2_name}, topic={input_data.topic}")

            # 初始化上下文（只保存字符串）
            agent_1_context = [user_input]
            agent_2_context = [user_input]
        else:
            logger.info(f"[AI.Debate] 從檢查點恢復: 已完成 {completed_rounds}/{input_data.max_rounds} 輪")
        
        # 2. 辯論循環（串行處理）
        for round_idx in range(completed_rounds, input_data.max_rounds):
            try:
                # === Agent 1 發言 ===
                logger.info(f"[AI.Debate] 第 {round_idx + 1} 輪 - {input_data.agent_1_name} 發言中...")
                
                msg_1 = await self._agent_turn(
                    name=input_data.agent_1_name,
                    llm_config_id=input_data.agent_1_llm_config,
                    system_prompt=input_data.agent_1_system_prompt,
                    context=agent_1_context,
                    input_data=input_data,
                    role="Agent 1"
                )
                
                # 更新記錄
                content_1 = msg_1.content
                thought_1 = msg_1.thought
                
                log_entry_1 = {
                    "round": round_idx + 1,
                    "role": input_data.agent_1_name,
                    "type": "Agent 1",
                    "thought": thought_1,
                    "content": content_1
                }
                full_log.append(log_entry_1)
                history_public.append({"role": input_data.agent_1_name, "content": content_1})
                
                # 更新上下文（簡化：只保存內容字符串）
                agent_2_context.append(f"【{input_data.agent_1_name}】: {content_1}")
                agent_1_context.append(f"【我的發言】: {content_1}")
                
                # === Agent 2 發言 ===
                logger.info(f"[AI.Debate] 第 {round_idx + 1} 輪 - {input_data.agent_2_name} 發言中...")
                
                msg_2 = await self._agent_turn(
                    name=input_data.agent_2_name,
                    llm_config_id=input_data.agent_2_llm_config,
                    system_prompt=input_data.agent_2_system_prompt,
                    context=agent_2_context,
                    input_data=input_data,
                    role="Agent 2"
                )
                
                content_2 = msg_2.content
                thought_2 = msg_2.thought
                
                log_entry_2 = {
                    "round": round_idx + 1,
                    "role": input_data.agent_2_name,
                    "type": "Agent 2",
                    "thought": thought_2,
                    "content": content_2
                }
                full_log.append(log_entry_2)
                history_public.append({"role": input_data.agent_2_name, "content": content_2})
                
                # 更新上下文
                agent_2_context.append(f"【我的發言】: {content_2}")
                agent_1_context.append(f"【{input_data.agent_2_name}】: {content_2}")
                
                # 3. 報告進度（一輪辯論完成）
                completed_rounds = round_idx + 1
                progress_percent = (completed_rounds / input_data.max_rounds) * 100
                
                logger.info(f"[AI.Debate] 推送進度: {progress_percent:.1f}% ({completed_rounds}/{input_data.max_rounds})")
                
                yield ProgressEvent(
                    percent=progress_percent,
                    message=f"第 {completed_rounds}/{input_data.max_rounds} 輪辯論完成",
                    data={
                        'completed_rounds': completed_rounds,
                        'history_public': history_public,
                        'full_log': full_log,
                        'agent_1_context': agent_1_context,
                        'agent_2_context': agent_2_context
                    }
                )
                
            except Exception as e:
                logger.error(f"[AI.Debate] 第 {round_idx + 1} 輪出錯: {e}", exc_info=True)
                # 出錯時停止辯論，返回當前結果
                break
        
        # 4. 返回最終結果
        logger.info(f"[AI.Debate] 辯論完成，共 {completed_rounds} 輪")
        
        yield DebateOutput(
            summary=history_public[-1]["content"] if history_public else "辯論未完成",
            history=history_public,
            full_log=full_log,
            total_rounds=completed_rounds
        )

    async def _agent_turn(
        self,
        name: str,
        llm_config_id: int,
        system_prompt: str,
        context: List[str],
        input_data: DebateInput,
        role: str
    ) -> DebateMessage:
        """執行單個 Agent 的回合（使用 generate_structured）"""
        try:
            # 構建 user_prompt（將上下文合併）
            user_prompt = "\n\n".join(context)
            
            # 使用 generate_structured 函數（包含配額管理、重試、token 統計）
            response = await generate_structured(
                session=self.context.session,
                llm_config_id=llm_config_id,
                user_prompt=user_prompt,
                output_type=DebateMessage,
                system_prompt=system_prompt,
                temperature=input_data.temperature,
                max_tokens=input_data.max_tokens,
                max_retries=3
            )
            
            logger.info(f"[AI.Debate] {role} ({name}) 發言完成")
            return response
            
        except Exception as e:
            logger.error(f"[AI.Debate] {role} ({name}) 調用失敗: {e}", exc_info=True)
            # 出錯時拋出異常，讓外層處理
            raise

