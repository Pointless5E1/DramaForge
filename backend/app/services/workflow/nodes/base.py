"""節點基礎類和工具函數

極簡類型安全設計：
1. 只有 Input 和 Output 模型，不需要 Config
2. 充分利用 Pydantic 的類型驗證和 JSON Schema
3. execute 方法直接接收和返回 Pydantic 模型
4. 自動從模型生成元數據
"""

from typing import Any, Dict, Optional, List, Type, Union, AsyncIterator, Generic, TypeVar, TYPE_CHECKING
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from typing_extensions import ClassVar
from abc import ABC, abstractmethod
import inspect
import asyncio

if TYPE_CHECKING:
    from ..engine.async_executor import ProgressEvent

from app.db.models import Card, CardType
from ..types import ExecutionContext, NodeMetadata


# 類型變量
TInput = TypeVar('TInput', bound=BaseModel)
TOutput = TypeVar('TOutput', bound=BaseModel)


def get_card_by_id(session: Session, card_id: int) -> Optional[Card]:
    """根據ID獲取卡片"""
    return session.get(Card, card_id)


def get_card_type_by_name(session: Session, type_name: str) -> Optional[CardType]:
    """根據名稱獲取卡片類型"""
    stmt = select(CardType).where(CardType.name == type_name)
    return session.exec(stmt).first()


def resolve_card_reference(
    session: Session,
    reference: Any,
    context_card_id: Optional[int] = None
) -> Optional[Card]:
    """解析卡片引用

    支持的引用格式：
    - 數字：直接作爲卡片ID
    - "$self": 當前上下文卡片
    - "$parent": 父卡片
    - 字典 {"id": 123}: 顯式指定ID

    Args:
        session: 數據庫會話
        reference: 卡片引用
        context_card_id: 上下文卡片ID（用於$self等引用）

    Returns:
        Card對象，不存在則返回None
    """
    # 數字直接作爲ID
    if isinstance(reference, int):
        return get_card_by_id(session, reference)

    # 字符串引用
    if isinstance(reference, str):
        if reference == "$self" and context_card_id:
            return get_card_by_id(session, context_card_id)
        elif reference == "$parent" and context_card_id:
            card = get_card_by_id(session, context_card_id)
            if card and card.parent_id:
                return get_card_by_id(session, card.parent_id)

    # 字典引用
    if isinstance(reference, dict):
        card_id = reference.get("id")
        if card_id:
            return get_card_by_id(session, card_id)

    return None


class BaseNode(ABC, Generic[TInput, TOutput]):
    """節點基類 - 極簡類型安全設計
    
    使用示例：
    ```python
    class NovelLoadInput(BaseModel):
        root_path: str = Field(..., description="小說根目錄")
        file_pattern: str = Field(r".*\\.txt$", description="文件匹配")
    
    class NovelLoadOutput(BaseModel):
        chapter_list: List[Dict] = Field(..., description="章節列表")
        volume_list: List[str] = Field(..., description="分卷列表")
    
    @register_node
    class NovelLoadNode(BaseNode[NovelLoadInput, NovelLoadOutput]):
        node_type = "Novel.Load"
        category = "novel"
        label = "加載小說"
        description = "掃描小說目錄"
        
        input_model = NovelLoadInput
        output_model = NovelLoadOutput
        
        async def execute(self, inputs: NovelLoadInput) -> NovelLoadOutput:
            # 直接使用類型化的輸入
            chapters = scan_directory(inputs.root_path)
            
            # 直接返回類型化的輸出
            return NovelLoadOutput(
                chapter_list=chapters,
                volume_list=volumes
            )
    ```
    """
    
    # 元數據（子類必須定義）
    node_type: ClassVar[str]
    category: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str] = ""
    
    # 輸入/輸出模型（子類必須定義）
    input_model: ClassVar[Type[TInput]]
    output_model: ClassVar[Type[TOutput]]

    @classmethod
    def get_output_schema_contract(
        cls,
        config: Dict[str, Any],
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """返回節點輸出的結構化 schema 契約（可選）。

        用於靜態校驗“節點輸出對象直傳到卡片 content”這類場景。
        默認無契約，具體節點可按需覆蓋。
        """
        return None
    
    def __init__(self, context: ExecutionContext):
        """初始化節點
        
        Args:
            context: 執行上下文（包含 session, variables 等）
        """
        self.context = context
        self._cleanup_tasks: List[Any] = []  # 需要清理的任務列表
    
    async def cleanup(self):
        """清理節點資源
        
        當工作流暫停或取消時調用，用於清理節點內部的資源：
        - 取消正在運行的子任務
        - 關閉文件句柄
        - 釋放數據庫連接
        - 清理臨時文件
        
        子類可以重寫此方法來實現自定義清理邏輯。
        
        默認實現：取消所有通過 register_task() 註冊的任務。
        """
        if self._cleanup_tasks:
            from loguru import logger
            logger.info(f"[{self.node_type}] 清理 {len(self._cleanup_tasks)} 個任務")
            
            for task in self._cleanup_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass  # 正常取消
                    except Exception as e:
                        logger.error(f"[{self.node_type}] 取消任務時出錯: {e}")
            
            self._cleanup_tasks.clear()
    
    def register_task(self, task):
        """註冊需要清理的任務
        
        節點內部創建的異步任務應該通過此方法註冊，
        以便在工作流暫停時能夠正確取消。
        
        Args:
            task: asyncio.Task 對象
        """
        self._cleanup_tasks.append(task)
    
    @classmethod
    def get_metadata(cls) -> NodeMetadata:
        """獲取節點元數據
        
        自動從 Pydantic 模型生成完整的 JSON Schema。
        
        Returns:
            NodeMetadata 對象
        """
        # 輸入 Schema（自動從 Pydantic 生成）
        input_schema = {}
        if hasattr(cls, 'input_model') and cls.input_model:
            input_schema = cls.input_model.model_json_schema()
        
        # 輸出 Schema（自動從 Pydantic 生成）
        output_schema = {}
        if hasattr(cls, 'output_model') and cls.output_model:
            output_schema = cls.output_model.model_json_schema()
        
        return NodeMetadata(
            type=cls.node_type,
            category=cls.category,
            label=cls.label,
            description=cls.description,
            documentation=inspect.getdoc(cls) or "",
            input_schema=input_schema,
            output_schema=output_schema,
            executor=cls
        )
    
    @abstractmethod
    async def execute(self, inputs: TInput) -> AsyncIterator[Union['ProgressEvent', TOutput]]:
        """執行節點邏輯（統一流式接口）
        
        節點可以 yield 兩種類型：
        1. ProgressEvent：報告進度（可選，用於批量處理）
        2. TOutput：最終結果（必須，至少 yield 一次）
        
        Args:
            inputs: 類型化的輸入模型
            
        Yields:
            ProgressEvent: 進度事件（可選，用於批量處理）
            TOutput: 輸出模型實例（必須，至少 yield 一次）
            
        注意：
        - 簡單節點：只 yield 結果，零額外代碼
        - 批量處理節點：可以多次 yield ProgressEvent 報告進度，最後 yield 結果
        - 最後一次 yield 的 TOutput 會被作爲節點的輸出
        
        示例：
            # 簡單節點（只 yield 結果）
            async def execute(self, inputs):
                result = await process(inputs)
                yield Output(result=result)
            
            # 批量處理節點（yield 進度 + 結果）
            async def execute(self, inputs):
                for i, item in enumerate(inputs.items):
                    result = await process(item)
                    
                    # 報告進度（自動保存檢查點）
                    yield ProgressEvent(
                        percent=(i + 1) / len(inputs.items) * 100,
                        message=f"已處理 {i + 1}/{len(inputs.items)}"
                    )
                
                # 返回最終結果
                yield Output(results=results)
        
        Raises:
            Exception: 執行失敗時拋出異常
        """
        raise NotImplementedError


# --- 便利的基類 ---

class NoInputNode(BaseNode[BaseModel, TOutput]):
    """無輸入節點的便利基類
    
    用於不需要輸入參數的節點（如觸發器）。
    """
    
    class EmptyInput(BaseModel):
        """空輸入"""
        pass
    
    input_model = EmptyInput
    
    async def execute(self, inputs: BaseModel) -> AsyncIterator[Union['ProgressEvent', TOutput]]:
        """執行節點（忽略輸入）"""
        result = await self.execute_no_input()
        yield result
    
    @abstractmethod
    async def execute_no_input(self) -> TOutput:
        """無輸入的執行方法"""
        raise NotImplementedError


class NoOutputNode(BaseNode[TInput, BaseModel]):
    """無輸出節點的便利基類
    
    用於只有副作用、不返回數據的節點（如日誌、顯示）。
    """
    
    class EmptyOutput(BaseModel):
        """空輸出"""
        pass
    
    output_model = EmptyOutput
    
    async def execute(self, inputs: TInput) -> AsyncIterator[Union['ProgressEvent', BaseModel]]:
        """執行節點（無返回值）"""
        await self.execute_no_output(inputs)
        yield self.EmptyOutput()
    
    @abstractmethod
    async def execute_no_output(self, inputs: TInput) -> None:
        """無輸出的執行方法"""
        raise NotImplementedError


# --- 工具函數 ---
