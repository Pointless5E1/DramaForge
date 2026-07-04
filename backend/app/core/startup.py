"""應用啓動初始化

統一的啓動初始化流程。
"""

from loguru import logger
from sqlalchemy import UniqueConstraint, inspect
from sqlalchemy.schema import CreateColumn
from sqlmodel import Session

from app.bootstrap.registry import discover_and_run_initializers
from app.core.events import discover_event_handlers
from app.db.models import SQLModel
from app.db.session import engine
from app.services.workflow.registry import discover_workflow_nodes


def init_database():
    """初始化數據庫表結構

    開發階段可用；生產環境建議通過 Alembic 遷移。
    """
    logger.info("[啓動] 初始化數據庫表結構...")
    SQLModel.metadata.create_all(engine)
    # 對已有數據庫執行輕量補齊：自動發現模型新增的安全追加列並補齊。
    # 僅處理“加列”場景；複雜變更仍建議使用 Alembic 遷移。
    _ensure_safe_additive_columns()
    logger.info("[啓動] 數據庫表結構初始化完成")


def _column_has_table_level_unique_constraint(column) -> bool:
    table = column.table
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and column.name in constraint.columns.keys():
            return True
    return False


def _can_auto_add_column(column) -> tuple[bool, str]:
    """檢查列是否適合自動補齊（僅處理安全的追加場景）。"""
    if column.primary_key:
        return False, "primary key"
    if column.unique or _column_has_table_level_unique_constraint(column):
        return False, "unique constraint"
    if column.foreign_keys:
        return False, "foreign key"
    if getattr(column, "computed", None) is not None:
        return False, "computed column"
    if not column.nullable and column.server_default is None:
        return False, "not-null without server_default"
    return True, ""


def _ensure_safe_additive_columns():
    """自動發現模型與現有表結構差異，並補齊可安全追加的缺失列。

    職責邊界：
    - 處理已存在數據表上的“新增列”場景
    - 僅補齊安全追加的列
    - 不處理刪列、改列類型、改約束、索引補建、數據回填等複雜遷移

    新表的創建仍由 `SQLModel.metadata.create_all(engine)` 負責。
    """
    added_columns: list[str] = []
    skipped_columns: list[str] = []

    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        preparer = conn.dialect.identifier_preparer

        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue

            try:
                db_columns = {item["name"] for item in inspector.get_columns(table.name)}
            except Exception:
                logger.exception(f"[啓動] 讀取現有表結構失敗: {table.name}")
                continue

            missing_columns = [column for column in table.columns if column.name not in db_columns]

            for column in missing_columns:
                allowed, reason = _can_auto_add_column(column)
                display_name = f"{table.name}.{column.name}"

                if not allowed:
                    skipped_columns.append(f"{display_name} ({reason})")
                    continue

                try:
                    column_ddl = str(CreateColumn(column).compile(dialect=conn.dialect))
                    table_name = preparer.format_table(table)
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}")
                    added_columns.append(display_name)
                except Exception as exc:
                    skipped_columns.append(f"{display_name} (add failed: {exc})")
                    logger.exception(f"[啓動] 自動補齊列失敗: {display_name}")

    if added_columns:
        logger.info(f"[啓動] 已自動補齊缺失列: {', '.join(added_columns)}")
    else:
        logger.info("[啓動] 表結構檢查完成，無需補齊缺失列")

    if skipped_columns:
        logger.warning(f"[啓動] 檢測到不安全或失敗列，已跳過自動補齊: {', '.join(skipped_columns)}")


def init_application_data():
    """初始化應用數據

    自動發現並執行所有已註冊的初始化器。
    初始化器通過 @initializer 裝飾器註冊，按 order 順序執行。
    """
    logger.info("[啓動] 初始化應用數據...")
    with Session(engine) as session:
        # 自動發現並執行所有初始化器
        discover_and_run_initializers(session)
    logger.info("[啓動] 應用數據初始化完成")


def register_event_handlers():
    """註冊事件處理器

    自動發現並導入所有事件處理器模塊以觸發 @on_event 裝飾器。
    """
    logger.info("[啓動] 註冊事件處理器...")
    # 導入事件處理器模塊以觸發裝飾器註冊
    import app.services  # noqa: F401

    discover_event_handlers()
    logger.info("[啓動] 事件處理器註冊完成")


def register_workflow_nodes():
    """註冊工作流節點

    自動發現並導入所有工作流節點模塊以觸發 @register_node 裝飾器。
    """
    logger.info("[啓動] 註冊工作流節點...")
    discover_workflow_nodes()
    logger.info("[啓動] 工作流節點註冊完成")


def cleanup_zombie_runs():
    """清理死機運行

    將所有狀態爲 "running" 的運行標記爲 "failed"。
    這些運行可能是因爲服務器崩潰或重啓而中斷的。
    """
    logger.info("[啓動] 清理死機運行...")

    from sqlmodel import select

    from app.db.models import WorkflowRun

    with Session(engine) as session:
        # 查找所有運行中的任務
        stmt = select(WorkflowRun).where(WorkflowRun.status == "running")
        zombie_runs = session.exec(stmt).all()

        if zombie_runs:
            logger.warning(f"[啓動] 發現 {len(zombie_runs)} 個死機工作流運行，正在清理...")
            for run in zombie_runs:
                run.status = "failed"
                if not run.error_json:
                    run.error_json = {"error": "服務器重啓，運行中斷"}
                session.add(run)
                logger.info(f"[啓動] 清理死機運行: run_id={run.id}, workflow_id={run.workflow_id}")
            session.commit()
            logger.info(f"[啓動] 已清理 {len(zombie_runs)} 個死機工作流運行")
        else:
            logger.info("[啓動] 沒有發現死機工作流運行")

    logger.info("[啓動] 死機工作流運行清理完成")


def startup():
    """應用啓動入口

    執行所有啓動初始化任務。
    """
    logger.info("=" * 50)
    logger.info("NovelForge 後端啓動中...")
    logger.info("=" * 50)

    # 1. 初始化數據庫
    init_database()
    # 2. 初始化應用數據
    init_application_data()
    # 3. 註冊事件處理器
    register_event_handlers()
    # 4. 註冊工作流節點
    register_workflow_nodes()
    # 5. 清理死機運行
    cleanup_zombie_runs()

    logger.info("=" * 50)
    logger.info("NovelForge 後端啓動完成！")
    logger.info("=" * 50)


def shutdown():
    """應用關閉清理

    執行關閉時的清理任務（如有需要）。
    """
    logger.info("NovelForge 後端正在關閉...")
    # 可以在這裏添加清理邏輯
    logger.info("NovelForge 後端已關閉")
