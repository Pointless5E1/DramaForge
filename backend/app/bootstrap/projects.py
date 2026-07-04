"""保留項目初始化

初始化系統保留項目。
"""

from sqlmodel import Session, select
from loguru import logger

from app.db.models import Project
from .registry import initializer


@initializer(name="保留項目", order=40)
def init_reserved_project(session: Session) -> None:
    """初始化保留項目
    
    確保存在一個保留項目 __free__，用於跨項目的自由卡片歸檔。
    
    Args:
        session: 數據庫會話
    """
    FREE_NAME = "__free__"
    exists = session.exec(select(Project).where(Project.name == FREE_NAME)).first()
    if not exists:
        p = Project(name=FREE_NAME, description="系統保留項目：存放自由卡片")
        session.add(p)
        session.commit()
        session.refresh(p)
        logger.info(f"已創建保留項目: {FREE_NAME} (id={p.id})")
    else:
        # 可在此處做增量更新（如描述字段）
        pass
