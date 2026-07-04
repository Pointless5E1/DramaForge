"""異步執行器

基於代碼式工作流的異步執行器，支持SSE推送進度。
完全流式設計，所有節點通過 async for 消費事件。
"""

import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
from sqlmodel import Session

from .execution_plan import ExecutionPlan, Statement
from .execution_state import ExecutionState, CheckpointData
from .error_handler import ErrorHandler
from ..registry import get_registered_nodes
from ..expressions.evaluator import evaluate_expression

if TYPE_CHECKING:
    from .state_manager import StateManager


# 統一的進度事件（節點和執行器共用）
@dataclass
class ProgressEvent:
    """進度事件（統一類型）
    
    用於節點報告執行進度，執行器自動保存爲檢查點。
    
    節點使用時（簡單版）：
        yield ProgressEvent(
            percent=50.0,
            message="已處理 30/60",
            data={'processed_count': 30}
        )
    
    執行器使用時（包含 statement）：
        yield ProgressEvent(
            statement=stmt,
            type='progress',
            percent=50.0,
            message="已處理 30/60"
        )
    
    Attributes:
        percent: 進度百分比（0-100）
        message: 進度消息
        data: 檢查點數據（節點使用，可選，輕量級元數據）
            - 只保存位置信息：索引、計數器、ID 等
            - 不保存業務數據：卡片內容、處理結果等
            - 大小限制：< 10KB
        statement: 語句對象（執行器使用）
        type: 事件類型（執行器使用）
        result: 執行結果（執行器使用）
        error: 錯誤信息（執行器使用）
    """
    # 節點層字段
    percent: float = 0.0  # 0-100
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    
    # 執行器層字段
    statement: Optional[Statement] = None
    type: Optional[str] = None  # 'start', 'progress', 'complete', 'error', 'workflow_complete'
    result: Optional[Any] = None
    error: Optional[str] = None


class AsyncExecutor:
    """異步執行器
    
    完全流式設計：
    1. 所有節點通過 async for 消費事件
    2. 異步任務收集並並行執行
    3. wait 節點等待並轉發事件
    4. 同步節點自動等待所有異步任務
    5. 支持暫停/恢復和斷點續傳
    
    使用統一的 ExecutionState 管理所有狀態。
    """

    def __init__(self, session: Session, state_manager: Optional['StateManager'] = None, run_id: int = 0):
        self.session = session  # 數據庫會話
        self.state_manager = state_manager  # 狀態管理器（可選，用於兼容）
        self.run_id = run_id  # 運行ID
        self.execution_state = ExecutionState(run_id)  # 統一的執行狀態
        self.node_registry = get_registered_nodes()
        self.async_tasks: Dict[str, asyncio.Task] = {}  # 異步任務（保存引用用於取消）
        self.node_instances: Dict[str, Any] = {}  # 節點實例（用於清理）
        self.event_queue: asyncio.Queue = asyncio.Queue()  # 事件隊列（實時轉發）
        self.pending_async_tasks: int = 0  # 待完成的異步任務數量
        self.pause_event = asyncio.Event()  # 暫停信號
        self.pause_event.set()  # 默認不暫停
        self.is_paused = False  # 是否已暫停
    
    @property
    def context(self) -> Dict[str, Any]:
        """執行上下文（兼容舊代碼）"""
        return self.execution_state.context
    
    @property
    def completed_statements(self) -> set:
        """已完成的語句（兼容舊代碼）"""
        return self.execution_state.completed_nodes

    async def execute_stream(
        self,
        plan: ExecutionPlan,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[ProgressEvent]:
        """流式執行工作流，返回進度事件
        
        使用事件隊列實時轉發進度：
        1. 異步任務的進度事件實時放入隊列
        2. 主協程從隊列中讀取事件並 yield
        3. 支持多個異步任務同時報告進度
        4. 支持暫停/恢復和斷點續傳
        
        Args:
            plan: 執行計劃
            initial_context: 初始上下文
            
        Yields:
            進度事件
        """
        # 嘗試恢復狀態（斷點續傳）
        is_resuming = False
        if self.run_id:
            # 從數據庫加載完整狀態
            self.execution_state = ExecutionState.load(self.run_id, self.session)
            
            # 只有當有已完成的節點時纔算恢復執行
            if self.execution_state.completed_nodes:
                is_resuming = True
                logger.info(
                    f"[AsyncExecutor] 檢測到恢復執行: run_id={self.run_id}, "
                    f"已完成={len(self.execution_state.completed_nodes)}個節點"
                )
            else:
                # 有 run_id 但沒有已完成的節點，說明是新執行或失敗重試
                self.execution_state.context = initial_context or {}
                logger.info(f"[AsyncExecutor] 新執行或重試: run_id={self.run_id}, 使用初始上下文")
        else:
            # 新執行，使用初始上下文
            self.execution_state.context = initial_context or {}
            logger.info(f"[AsyncExecutor] 新執行: 使用初始上下文")
        
        # 如果是恢復執行，先推送已完成節點的狀態（讓前端顯示）
        if is_resuming:
            for node_id in self.execution_state.completed_nodes:
                node_state = self.execution_state.get_node_state(node_id)
                if node_state and node_state.status == "success":
                    # 找到對應的語句
                    stmt = next((s for s in plan.statements if s.variable == node_id), None)
                    if stmt:
                        # 推送已完成事件
                        await self.event_queue.put(ProgressEvent(
                            statement=stmt,
                            type='complete',
                            result=node_state.outputs,
                            message=f"[已恢復] {node_id}"
                        ))
                        logger.info(f"[AsyncExecutor] 推送已完成節點狀態: {node_id}")
        
        logger.info(f"[AsyncExecutor] 開始流式執行工作流，共 {len(plan.statements)} 個語句")
        
        # 啓動事件消費協程
        consumer_task = asyncio.create_task(self._process_statements(plan))
        
        try:
            # 從隊列中讀取事件並轉發
            while True:
                event = await self.event_queue.get()
                
                if event is None:  # 結束標記
                    break
                    
                yield event
                
        finally:
            # 等待語句處理完成
            try:
                await consumer_task
            except Exception as e:
                logger.error(f"[AsyncExecutor] 語句處理失敗: {e}")
                raise
    
    async def _process_statements(self, plan: ExecutionPlan):
        """處理所有語句（在單獨的協程中運行）"""
        try:
            for stmt in plan.statements:
                # 跳過已完成的語句（斷點續傳）
                if self.execution_state.is_completed(stmt.variable):
                    logger.info(f"[AsyncExecutor] 跳過已完成的語句: {stmt.variable}")
                    continue
                
                # 檢查暫停信號（如果已暫停，停止執行）
                if self.is_paused:
                    logger.info(f"[AsyncExecutor] 檢測到暫停狀態，停止執行")
                    break
                
                # 等待暫停信號（如果暫停，會在這裏阻塞）
                await self.pause_event.wait()
                
                logger.info(f"[AsyncExecutor] 執行語句: {stmt.variable} (類型: {stmt.node_type}, async: {stmt.is_async}, disabled: {stmt.disabled})")
                
                # 跳過禁用的節點
                if stmt.disabled:
                    logger.info(f"[AsyncExecutor] 跳過禁用的節點: {stmt.variable}")
                    
                    # 發送跳過事件到隊列
                    await self.event_queue.put(ProgressEvent(
                        statement=stmt,
                        type='skipped',
                        message=f"節點已禁用，跳過執行: {stmt.variable}"
                    ))
                    
                    # 將結果設置爲 None（避免後續節點引用時出錯）
                    self.execution_state.context[stmt.variable] = None
                    self.execution_state.completed_nodes.add(stmt.variable)
                    continue
                
                # 發送開始事件到隊列
                await self.event_queue.put(ProgressEvent(
                    statement=stmt,
                    type='start',
                    message=f"開始執行: {stmt.variable}"
                ))
                
                try:
                    if stmt.is_async:
                        # 異步節點：創建任務，事件實時放入隊列
                        logger.info(f"[AsyncNode] 創建異步任務: {stmt.variable}")
                        self.pending_async_tasks += 1
                        
                        # 創建任務，將事件實時放入隊列（保存引用用於取消）
                        task = asyncio.create_task(
                            self._execute_async_node_to_queue(stmt),
                            name=f"async_node_{stmt.variable}"  # 設置任務名稱便於調試
                        )
                        self.async_tasks[stmt.variable] = task
                        logger.info(f"[AsyncNode] 任務已創建並保存引用: {stmt.variable}")
                        # 不等待，繼續下一個語句
                        
                    elif stmt.node_type == "Logic.Wait" or stmt.node_type == "_wait":
                        # wait 節點：等待指定的異步任務
                        # 支持兩種配置格式：tasks (新) 和 wait_for (舊)
                        wait_for = stmt.config.get("tasks") or stmt.config.get("wait_for", [])
                        
                        # 確保 wait_for 是列表
                        if isinstance(wait_for, str):
                            # 如果是字符串，按逗號分割
                            wait_for = [v.strip() for v in wait_for.split(",") if v.strip()]
                        elif not isinstance(wait_for, list):
                            wait_for = [wait_for] if wait_for else []
                        
                        # 清理變量名：移除 $ 前綴（如果有）
                        wait_for = [v.lstrip('$') if isinstance(v, str) else v for v in wait_for]
                        
                        logger.info(f"[Wait] 等待異步任務: {','.join(wait_for)}")
                        
                        for var in wait_for:
                            if var in self.async_tasks:
                                # 異步任務還在運行，等待它完成
                                logger.info(f"[Wait] 等待異步任務完成: {var}")
                                await self.async_tasks[var]
                                del self.async_tasks[var]
                            elif var in self.execution_state.context:
                                # 變量已經在上下文中（已完成或恢復的節點）
                                logger.info(f"[Wait] 變量已存在於上下文: {var}")
                            else:
                                # 變量不存在
                                raise ValueError(f"等待的變量不存在: {var}")
                        
                        # 保存 wait 結果到上下文
                        self.execution_state.context[stmt.variable] = {
                            'waited_tasks': wait_for,
                            'count': len(wait_for)
                        }
                        
                        # wait 節點本身發送完成事件
                        await self.event_queue.put(ProgressEvent(
                            statement=stmt,
                            type='complete',
                            result=self.execution_state.context[stmt.variable]
                        ))
                        
                        # 標記爲已完成
                        self.execution_state.completed_nodes.add(stmt.variable)
                        
                    elif stmt.node_type is None:
                        # 純表達式
                        result = self._execute_expression(stmt)
                        self.execution_state.context[stmt.variable] = result
                        
                        # 保存節點輸出
                        self.execution_state.update_node_state(
                            node_id=stmt.variable,
                            node_type="expression",
                            status="success",
                            progress=100.0,
                            outputs=result
                        )
                        self.execution_state.save(self.session)
                        
                        await self.event_queue.put(ProgressEvent(
                            statement=stmt,
                            type='complete',
                            result=result
                        ))
                        
                    else:
                        # 同步節點：直接執行，不等待異步任務
                        async for event in self._execute_node_stream(stmt):
                            await self.event_queue.put(event)
                    
                    # 標記語句已完成
                    self.execution_state.completed_nodes.add(stmt.variable)
                            
                except Exception as e:
                    logger.error(f"[AsyncExecutor] 語句執行失敗: {stmt.variable}, 錯誤: {e}")
                    # 使用錯誤處理器
                    error_event = await ErrorHandler.handle_node_error(
                        e, stmt, self.execution_state, self.session
                    )
                    await self.event_queue.put(error_event)
                    raise
            
            # 工作流結束，等待所有剩餘的異步任務
            if self.async_tasks:
                logger.info(f"[AsyncExecutor] 工作流結束，等待剩餘 {len(self.async_tasks)} 個異步任務")
                for var, task in list(self.async_tasks.items()):
                    logger.info(f"[AsyncExecutor] 等待異步任務: {var}")
                    await task
                    del self.async_tasks[var]
            
            logger.info(f"[AsyncExecutor] 工作流流式執行完成，共定義 {len(self.execution_state.context)} 個變量")
            
            # 發送工作流完成事件
            await self.event_queue.put(ProgressEvent(
                statement=plan.statements[-1] if plan.statements else Statement(line_number=0, variable="", node_type=None, config={}, depends_on=[]),
                type='workflow_complete',
                message="工作流執行完成"
            ))
            
        finally:
            # 發送結束標記
            await self.event_queue.put(None)
    
    async def _execute_async_node_to_queue(self, stmt: Statement):
        """執行異步節點，並將事件實時放入隊列"""
        try:
            async for event in self._execute_node_stream(stmt):
                await self.event_queue.put(event)
        except asyncio.CancelledError:
            # 任務被取消，使用錯誤處理器保存狀態
            await ErrorHandler.handle_cancellation(
                stmt, self.execution_state, self.session
            )
            raise  # 重新拋出，讓上層處理
        except Exception as e:
            # 節點執行錯誤
            logger.error(f"[AsyncNode] 異步節點執行失敗: {stmt.variable}, 錯誤: {e}")
            error_event = await ErrorHandler.handle_node_error(
                e, stmt, self.execution_state, self.session
            )
            await self.event_queue.put(error_event)
            raise
        finally:
            self.pending_async_tasks -= 1

    async def _execute_node_stream(self, stmt: Statement) -> AsyncIterator[ProgressEvent]:
        """執行節點並流式返回事件（支持自動檢查點）
        
        核心功能：
        1. 加載檢查點（如果存在）並注入到 ExecutionContext
        2. 攔截所有 yield，自動保存檢查點
        3. 轉發進度事件到前端
        
        Args:
            stmt: 語句對象
            
        Yields:
            進度事件（progress 和 complete）
        """
        node_type = stmt.node_type
        
        # 獲取節點執行器
        executor_fn = self.node_registry.get(node_type)
        if not executor_fn:
            raise ValueError(f"未註冊的節點類型: {node_type}")
        
        # 解析配置，處理變量引用
        config = self._resolve_config(stmt.config)
        
        # 構建輸入
        inputs = self._resolve_inputs(config)
        
        # === 初始化節點狀態 ===
        self.execution_state.update_node_state(
            node_id=stmt.variable,
            node_type=node_type,
            status="running",
            progress=0.0
        )
        
        # === 1. 加載檢查點 ===
        checkpoint_data = self.execution_state.get_checkpoint(stmt.variable)
        checkpoint = checkpoint_data.data if checkpoint_data else None
        
        if checkpoint:
            logger.info(
                f"[Checkpoint] 恢復節點 {stmt.variable}: "
                f"進度={checkpoint_data.percent}%, "
                f"數據={checkpoint}"
            )
        
        # 執行節點
        import inspect
        if inspect.isclass(executor_fn):
            # 類式節點 - 需要創建 ExecutionContext
            from ..types import ExecutionContext, WorkflowSettings
            
            # === 2. 創建執行上下文（注入檢查點）===
            context = ExecutionContext(
                run_id=self.run_id or 0,
                node_id=stmt.variable,
                node_type=node_type,
                config=config,
                inputs=inputs,
                variables=self.execution_state.context,
                node_outputs={},
                settings=WorkflowSettings(),
                session=self.session,
                checkpoint=checkpoint  # 注入檢查點數據
            )
            
            # 實例化節點
            node = executor_fn(context)
            
            # ⚠️ 保存節點實例引用（用於清理）
            self.node_instances[stmt.variable] = node
            
            # 準備輸入數據（合併 config 和 inputs）
            if hasattr(executor_fn, 'input_model') and executor_fn.input_model:
                input_data = {**config, **inputs}
                input_instance = executor_fn.input_model(**input_data)
            else:
                raise ValueError(f"節點 {node_type} 缺少 input_model 定義")
            
            # === 3. 執行節點並攔截 yield ===
            result = None
            async for event in node.execute(input_instance):
                # 處理進度事件（節點的 ProgressEvent）
                if isinstance(event, ProgressEvent):
                    # === 自動保存檢查點 ===
                    checkpoint_data = CheckpointData(
                        percent=event.percent,
                        message=event.message,
                        data=event.data,
                        timestamp=datetime.utcnow()
                    )
                    
                    self.execution_state.update_node_state(
                        node_id=stmt.variable,
                        node_type=node_type,
                        status="running",
                        progress=event.percent,
                        checkpoint=checkpoint_data
                    )
                    self.execution_state.save(self.session)
                    
                    # 轉發進度事件（包裝成執行器事件）
                    yield ProgressEvent(
                        statement=stmt,
                        type='progress',
                        percent=event.percent,
                        message=event.message
                    )
                else:
                    # 這是最終結果（Pydantic 模型）
                    result = event
            
            # 檢查執行結果
            if result is None:
                raise ValueError(f"節點 {node_type} 沒有返回結果")
            
            # 轉換爲字典
            if hasattr(result, 'model_dump'):
                final_result = result.model_dump()
            elif hasattr(result, 'dict'):
                final_result = result.dict()
            else:
                final_result = result
            
            # 保存到上下文（統一使用完整的輸出字典）
            self.execution_state.context[stmt.variable] = final_result
            
            # === 4. 保存完成狀態（100% 進度）===
            self.execution_state.update_node_state(
                node_id=stmt.variable,
                node_type=node_type,
                status="success",
                progress=100.0,
                outputs=final_result,
                checkpoint=CheckpointData(
                    percent=100.0,
                    message="完成",
                    data={'completed': True},
                    timestamp=datetime.utcnow()
                )
            )
            self.execution_state.save(self.session)
            
            # 發送完成事件
            yield ProgressEvent(
                statement=stmt,
                type='complete',
                result=final_result
            )
                
        elif inspect.iscoroutinefunction(executor_fn):
            # 異步函數節點
            result = await executor_fn(**inputs)
            self.execution_state.context[stmt.variable] = result
            
            # 保存節點輸出
            self.execution_state.update_node_state(
                node_id=stmt.variable,
                node_type=node_type or "async_function",
                status="success",
                progress=100.0,
                outputs=result
            )
            self.execution_state.save(self.session)
            
            yield ProgressEvent(
                statement=stmt,
                type='complete',
                result=result
            )
        else:
            # 同步函數節點
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: executor_fn(**inputs))
            self.execution_state.context[stmt.variable] = result
            
            # 保存節點輸出
            self.execution_state.update_node_state(
                node_id=stmt.variable,
                node_type=node_type or "sync_function",
                status="success",
                progress=100.0,
                outputs=result
            )
            self.execution_state.save(self.session)
            
            yield ProgressEvent(
                statement=stmt,
                type='complete',
                result=result
            )

    def _execute_expression(self, stmt: Statement) -> Any:
        """執行純表達式"""
        expression = stmt.config.get("expression", "")
        logger.info(f"[Expression] 執行表達式: {expression}")
        
        # 使用表達式求值器求值
        context = self._resolve_context(stmt.depends_on)
        return evaluate_expression(expression, context)

    def _resolve_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析配置，處理變量引用（支持嵌套結構）"""
        resolved = {}
        for key, value in config.items():
            resolved[key] = self._resolve_value(value)
        return resolved

    def _resolve_value(self, value: Any) -> Any:
        """遞歸解析值，處理變量引用"""
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                # 表達式引用，如 ${len(items)}
                expression = value[2:-1]
                return evaluate_expression(expression, self.execution_state.context)
            elif value.startswith("$"):
                # 變量引用，如 $novel.chapter_list
                ref = value[1:]  # 去掉 $ 前綴
                return self._resolve_variable_reference(ref)
            else:
                return value
        elif isinstance(value, list):
            return [self._resolve_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._resolve_value(v) for k, v in value.items()}
        else:
            return value

    def _resolve_variable_reference(self, ref: str) -> Any:
        """解析變量引用
        
        支持：
        - 簡單變量：novel
        - 屬性訪問：novel.title
        - 嵌套屬性：novel.metadata.author
        """
        parts = ref.split(".")
        value = self.execution_state.context.get(parts[0])
        
        if value is None:
            raise ValueError(f"變量不存在: {parts[0]}")
        
        # 處理屬性訪問
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
            
            if value is None:
                raise ValueError(f"屬性不存在: {ref}")
        
        return value

    def _resolve_inputs(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """從配置中提取輸入參數"""
        # 對於大多數節點，config 就是 inputs
        return config

    def _resolve_context(self, depends_on: List[str]) -> Dict[str, Any]:
        """解析依賴的上下文"""
        context = {}
        for var in depends_on:
            if var in self.execution_state.context:
                context[var] = self.execution_state.context[var]
        return context

    def pause(self):
        """暫停執行
        
        立即取消所有異步任務並暫停執行。
        不等待任務完成，讓它們在後臺取消。
        """
        self.is_paused = True
        self.pause_event.clear()
        
        # 清理所有節點實例（不等待完成）
        if self.node_instances:
            logger.info(f"[AsyncExecutor] 清理 {len(self.node_instances)} 個節點實例")
            for var, node in list(self.node_instances.items()):
                try:
                    logger.info(f"[AsyncExecutor] 清理節點: {var}")
                    # 創建清理任務但不等待（後臺清理）
                    asyncio.create_task(node.cleanup())
                except Exception as e:
                    logger.error(f"[AsyncExecutor] 創建清理任務失敗: {var}, 錯誤: {e}")
        
        # 取消所有異步任務（不等待完成）
        if self.async_tasks:
            logger.info(f"[AsyncExecutor] 取消 {len(self.async_tasks)} 個異步任務")
            for var, task in list(self.async_tasks.items()):
                if not task.done():
                    logger.info(f"[AsyncExecutor] 取消異步任務: {var}")
                    task.cancel()
                    # ⚠️ 不等待任務完成，讓它在後臺取消
        
        logger.info(f"[AsyncExecutor] 工作流已暫停: run_id={self.run_id}")
    
    def resume(self):
        """恢復執行
        
        恢復之前暫停的工作流執行。
        """
        self.is_paused = False
        self.pause_event.set()
        logger.info(f"[AsyncExecutor] 工作流已恢復: run_id={self.run_id}")
    
    def is_paused(self) -> bool:
        """檢查是否處於暫停狀態"""
        return not self.pause_event.is_set()
