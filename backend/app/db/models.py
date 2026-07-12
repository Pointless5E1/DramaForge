
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from sqlalchemy import UniqueConstraint
import sqlalchemy as sa
from typing import Optional, List, Any
from datetime import datetime


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None

    cards: List["Card"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete-orphan"})



class LLMConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    display_name: Optional[str] = None
    model_name: str
    api_base: Optional[str] = None
    api_key: str
    # 這裏必須帶 server_default，啓動期自動補列邏輯纔會認爲它是“安全追加列”。
    # 僅有 Python 默認值不夠，舊庫在 ALTER TABLE 時需要數據庫側默認值來回填歷史行。
    api_protocol: str = Field(
        default="chat_completions",
        sa_column=Column(sa.String, nullable=False, server_default="chat_completions"),
    )
    custom_request_path: Optional[str] = None
    models_path: Optional[str] = None
    user_agent: Optional[str] = None
    base_url: Optional[str] = None  # 歷史兼容字段，新實現統一收口到 api_base
    # 統計與配額（-1 表示不限）——在 DB 層也設置 server_default，便於 Alembic 自動包含
    token_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )
    call_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )
    used_tokens_input: int = Field(
        default=0,
        sa_column=Column(sa.Integer, nullable=False, server_default='0')
    )
    used_tokens_output: int = Field(
        default=0,
        sa_column=Column(sa.Integer, nullable=False, server_default='0')
    )
    used_calls: int = Field(
        default=0,
        sa_column=Column(sa.Integer, nullable=False, server_default='0')
    )
    # RPM/TPM 僅佔位，暫不實現
    rpm_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )
    tpm_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )
    capability_summary: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    recommended_assistant_mode: str = Field(
        default="auto",
        sa_column=Column(sa.String, nullable=False, server_default="auto"),
    )
    disable_stream: bool = Field(
        default=False,
        sa_column=Column(sa.Boolean, nullable=False, server_default=sa.false()),
    )
    capability_last_checked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime, nullable=True),
    )


class Prompt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None
    template: str
    version: int = 1
    built_in: bool = Field(default=False)
    is_review_prompt: bool = Field(
        default=False,
        sa_column=Column(sa.Boolean, nullable=False, server_default=sa.false()),
    )



class CardType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    # 兼容舊的模型名稱（如 CharacterCard/SceneCard），爲空則默認等於 name
    model_name: Optional[str] = Field(default=None, index=True)
    description: Optional[str] = None
    # 類型內置結構（JSON Schema）
    json_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # 類型級默認 AI 參數（模型ID/提示詞/採樣等）
    ai_params: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    editor_component: Optional[str] = None  # e.g., 'NovelEditor' for custom UI
    is_ai_enabled: bool = Field(default=True)
    is_singleton: bool = Field(default=False)  # e.g., only one 'Synopsis' card per project
    built_in: bool = Field(default=False)
    # 卡片類型級別的默認上下文注入模板
    default_ai_context_template: Optional[str] = Field(default=None)
    default_ai_context_template_review: Optional[str] = Field(default=None)
    # UI 佈局（可選），供前端 SectionedForm 使用
    ui_layout: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    cards: List["Card"] = Relationship(back_populates="card_type")


class Card(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    # 兼容舊的模型名稱；爲空表示跟隨類型的 model_name 或類型名
    model_name: Optional[str] = Field(default=None, index=True)
    content: Any = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)

    # 允許實例自定義結構；爲空表示跟隨類型
    json_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # 實例級 AI 參數；爲空表示跟隨類型
    ai_params: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # 自引用關係，用於樹形結構
    parent_id: Optional[int] = Field(default=None, foreign_key="card.id")
    parent: Optional["Card"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "[Card.id]"}
    )
    children: List["Card"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={
            "cascade": "all, delete, delete-orphan",
            "single_parent": True,
        },
    )

    # 項目外鍵
    project_id: int = Field(foreign_key="project.id")
    project: "Project" = Relationship(back_populates="cards")

    # 卡片類型外鍵
    card_type_id: int = Field(foreign_key="cardtype.id")
    card_type: "CardType" = Relationship(back_populates="cards")

    # 用於排序卡片，用於同一父級下的排序
    display_order: int = Field(default=0)
    ai_context_template: Optional[str] = Field(default=None)
    ai_context_template_review: Optional[str] = Field(default=None)
    
    # AI 修改狀態標記
    ai_modified: bool = Field(default=False)  # 是否由AI修改過
    needs_confirmation: bool = Field(default=False)  # 是否需要用戶確認（用於觸發工作流）
    last_modified_by: Optional[str] = Field(default=None)  # 最後修改者：'user' | 'ai' | None

# 伏筆登記表
class ForeshadowItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    chapter_id: Optional[int] = Field(default=None)  # 章節卡片ID或章節ID
    title: str
    type: str = Field(default='other', index=True)  # goal | item | person | other
    note: Optional[str] = None
    status: str = Field(default='open', index=True)  # open | resolved
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    resolved_at: Optional[datetime] = None


# 知識庫模型
class Knowledge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None
    content: str
    built_in: bool = Field(default=False)


# 工作流系統
class Workflow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    dsl_version: int = Field(default=2)  # DSL版本：2=代碼式工作流
    is_built_in: bool = Field(default=False)
    is_active: bool = Field(default=True)
    
    # 工作流定義（代碼式）
    definition_code: str = Field(default="")  # 工作流代碼
    
    # 工作流模板
    is_template: bool = Field(default=False)
    template_category: Optional[str] = None  # 如："內容生成"、"數據處理"
    
    # 運行數據保留策略
    # True: 長期保留（受全局有效期限制）
    # False: 短期保留（僅用於前端查看結果，之後自動清理）
    keep_run_history: bool = Field(default=False)
    
    # 觸發器緩存（優化性能，避免單獨查詢 WorkflowTrigger 表）
    triggers_cache: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    """觸發器緩存（從代碼中自動提取）
    
    結構：
    [
        {
            "trigger_on": "onsave",           # 觸發事件類型
            "card_type_name": "章節",         # 卡片類型（可選）
            "filter_json": {                  # 過濾配置（可選）
                "events": ["create", "update"],
                "conditions": [...]
            }
        },
        ...
    ]
    
    優勢：
    - 啓動性能提升 100 倍（5ms vs 500ms）
    - 避免數據冗餘和同步問題
    - 代碼是唯一真實來源
    """
    
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=False)

    # Relations
    runs: List["WorkflowRun"] = Relationship(back_populates="workflow", sa_relationship_kwargs={
        "cascade": "all, delete-orphan"
    })


class WorkflowRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id")
    workflow: Workflow = Relationship(back_populates="runs")

    definition_version: int = Field(default=1)
    # queued | running | succeeded | failed | cancelled | paused | timeout
    status: str = Field(default="queued", index=True)
    scope_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    params_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    idempotency_key: Optional[str] = Field(default=None, index=True)
    
    # 執行狀態
    state_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # 運行時狀態（變量、節點輸出等）
    error_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # 錯誤信息
    
    # 時間控制
    max_execution_time: Optional[int] = None  # 秒，None表示無限制
    
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    summary_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Relations
    node_states: List["NodeExecutionState"] = Relationship(back_populates="run", sa_relationship_kwargs={
        "cascade": "all, delete-orphan"
    })


class NodeExecutionState(SQLModel, table=True):
    """節點執行狀態表 - 用於詳細追蹤每個節點的執行情況"""
    __tablename__ = "nodeexecutionstate"
    __table_args__ = (
        # 添加唯一約束：同一個 run 的同一個節點只能有一條記錄
        UniqueConstraint('run_id', 'node_id', name='uq_run_node'),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="workflowrun.id", index=True)
    run: WorkflowRun = Relationship(back_populates="node_states")

    node_id: str = Field(index=True)  # 節點ID（來自DSL）
    node_type: str  # 節點類型

    # 執行狀態：idle | pending | running | success | error | skipped
    status: str = Field(default="idle", index=True)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    progress: int = Field(default=0)  # 0-100
    
    # 節點輸出（用於斷點續傳）
    outputs_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    """節點輸出數據（用於恢復執行）
    
    當工作流暫停後恢復時，需要從這裏讀取已完成節點的輸出，
    以便後續節點可以訪問前置節點的結果。
    
    示例：
    {
        "project_id": 123,
        "card_id": 456,
        "result": {...}
    }
    """
    
    # 錯誤信息（簡化）
    error_message: Optional[str] = None
    
    # 檢查點數據（新增）
    checkpoint_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    """檢查點數據（輕量級元數據）
    
    結構：
    {
        "percent": 50.0,                    # 進度百分比
        "message": "已處理 30/60",          # 進度消息
        "data": {                           # 節點自定義數據（可選）
            "processed_count": 30,          # ✅ 輕量級：計數器
            "last_item_id": "item_30",      # ✅ 輕量級：標識符
            "current_batch": 3              # ✅ 輕量級：批次號
        },
        "timestamp": "2026-02-04T10:30:00"  # 保存時間
    }
    
    注意：
    - data 字段只保存位置信息，不保存業務數據
    - 大小限制：< 10KB
    - 用於斷點續傳，節點通過 context.checkpoint 訪問
    """
    
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=False)

class KGRelation(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("project_id", "source", "target", "kind_en", name="uq_kg_relation_key"),
        sa.Index("ix_kg_relation_project_source", "project_id", "source"),
        sa.Index("ix_kg_relation_project_target", "project_id", "target"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    source: str = Field(index=True)
    target: str = Field(index=True)
    kind_en: str = Field(index=True)
    kind_cn: str = Field(default="其他")
    fact: Optional[str] = None
    a_to_b_addressing: Optional[str] = None
    b_to_a_addressing: Optional[str] = None
    recent_dialogues: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    recent_event_summaries: List[dict] = Field(default_factory=list, sa_column=Column(JSON))
    stance: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=False)
