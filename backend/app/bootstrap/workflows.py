"""工作流初始化

從文件系統加載工作流定義並初始化到數據庫。
支持 .wf 格式的代碼式工作流。
"""

import os
from sqlmodel import Session, select
from loguru import logger

from app.db.models import Workflow
from app.core.config import settings
from .registry import initializer


def _parse_code_workflow(file_path: str) -> dict:
    """解析代碼式工作流文件（.wf格式）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        code = f.read()

    # 工作流名稱統一以文件名爲準，避免文件頭註釋導致初始化名稱漂移
    name = os.path.splitext(os.path.basename(file_path))[0]
    description = f"內置工作流: {name}"
    
    return {
        "name": name,
        "description": description,
        "code": code,
        "keep_run_history": False,  # 代碼式工作流默認不保留歷史
    }


def _create_or_update_workflow(session: Session, name: str, description: str, 
                               code: str, keep_run_history: bool, 
                               overwrite: bool) -> tuple[int, int, int]:
    """創建或更新單個工作流（使用 triggers_cache）"""
    created_count = updated_count = skipped_count = 0
    
    wf = session.exec(select(Workflow).where(Workflow.name == name)).first()
    if not wf:
        wf = Workflow(
            name=name, 
            description=description, 
            is_built_in=True, 
            is_active=True, 
            dsl_version=2,  # 代碼式工作流使用版本2
            definition_code=code,
            keep_run_history=keep_run_history
        )
        session.add(wf)
        session.commit()
        session.refresh(wf)
        created_count += 1
        logger.info(f"已創建內置工作流: {name} (id={wf.id})")
    else:
        if overwrite:
            wf.definition_code = code
            wf.description = description
            wf.is_built_in = True
            wf.is_active = True
            wf.dsl_version = 2
            wf.keep_run_history = keep_run_history
            session.add(wf)
            session.commit()
            updated_count += 1
            logger.info(f"已更新內置工作流: {name} (id={wf.id})")
        else:
            skipped_count += 1
    
    # 同步觸發器緩存
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(wf, session)
    session.commit()
    
    return created_count, updated_count, skipped_count


def get_all_workflow_files() -> dict:
    """從文件系統加載所有工作流
    
    掃描 .wf 格式的代碼式工作流文件
    
    Returns:
        工作流字典，key爲工作流名稱
    """
    workflow_dir = os.path.join(os.path.dirname(__file__), 'workflows')
    if not os.path.exists(workflow_dir):
        logger.warning(f"Workflow directory not found at {workflow_dir}. Cannot load workflows.")
        return {}

    workflow_files = {}
    for filename in os.listdir(workflow_dir):
        if filename.endswith('.wf'):
            file_path = os.path.join(workflow_dir, filename)
            try:
                workflow_data = _parse_code_workflow(file_path)
                name = workflow_data["name"]
                workflow_files[name] = workflow_data
                logger.debug(f"加載工作流文件: {filename} -> {name}")
            except Exception as e:
                logger.error(f"Failed to parse workflow file {filename}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    return workflow_files

@initializer(name="工作流", order=50)
def init_workflows(session: Session) -> None:
    """初始化內置工作流
    
    從 bootstrap/workflows/ 目錄加載所有 .wf 工作流文件。
    行爲受配置項 BOOTSTRAP_OVERWRITE 控制。
    
    Args:
        session: 數據庫會話
    """
    overwrite = settings.bootstrap.should_overwrite
    total_created = total_updated = total_skipped = 0
    
    # 加載所有工作流文件
    all_workflows = get_all_workflow_files()
    
    if not all_workflows:
        logger.warning("未找到任何工作流定義文件")
        return
    
    # 逐個處理工作流
    for name, workflow_data in all_workflows.items():
        try:
            c, u, s = _create_or_update_workflow(
                session,
                name=workflow_data["name"],
                description=workflow_data["description"],
                code=workflow_data["code"],
                keep_run_history=workflow_data.get("keep_run_history", False),
                overwrite=overwrite
            )
            total_created += c
            total_updated += u
            total_skipped += s
        except Exception as e:
            logger.error(f"初始化工作流 {name} 失敗: {e}")
            import traceback
            traceback.print_exc()
            continue
            
    if total_created > 0 or total_updated > 0:
        logger.info(f"工作流初始化完成: +{total_created}, ~{total_updated}, -{total_skipped}")
    else:
        logger.info(f"所有工作流已是最新 (skip={total_skipped})")
