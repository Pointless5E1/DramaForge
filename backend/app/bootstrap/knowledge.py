"""知識庫初始化

從文件系統加載知識庫內容並初始化到數據庫。
"""

import os
from sqlmodel import Session, select
from loguru import logger

from app.db.models import Knowledge
from app.core.config import settings
from .registry import initializer


@initializer(name="知識庫", order=30)
def init_knowledge(session: Session) -> None:
    """初始化知識庫
    
    從 bootstrap/knowledge 目錄導入 *.txt 和 *.md 文件。
    
    Args:
        session: 數據庫會話
    """
    knowledge_dir = os.path.join(os.path.dirname(__file__), 'knowledge')
    if not os.path.exists(knowledge_dir):
        logger.warning(f"Knowledge directory not found at {knowledge_dir}. Cannot load knowledge base.")
        return

    existing = {k.name: k for k in session.exec(select(Knowledge)).all()}
    created = 0
    updated = 0
    skipped = 0
    overwrite = settings.bootstrap.should_overwrite

    for filename in os.listdir(knowledge_dir):
        if not filename.lower().endswith(('.txt', '.md')):
            continue
        file_path = os.path.join(knowledge_dir, filename)
        name = os.path.splitext(filename)[0]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
        except Exception as e:
            logger.warning(f"讀取知識庫文件失敗 {file_path}: {e}")
            continue
        description = f"預置知識庫：{name}"
        if name in existing:
            if overwrite:
                kb = existing[name]
                kb.content = content
                kb.description = description
                kb.built_in = True
                updated += 1
            else:
                skipped += 1
        else:
            session.add(Knowledge(name=name, description=description, content=content, built_in=True))
            created += 1

    if created or updated:
        session.commit()
        logger.info(f"知識庫初始化完成：新增 {created}，更新 {updated}（overwrite={overwrite}，跳過 {skipped}）")
    else:
        logger.info(f"知識庫已是最新狀態（overwrite={overwrite}，跳過 {skipped}）。")
