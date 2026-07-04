"""提示詞初始化

從文件系統加載提示詞模板並初始化到數據庫。
"""

import os
from sqlmodel import Session, select
from loguru import logger

from app.db.models import Prompt
from app.core.config import settings
from .registry import initializer


def _parse_prompt_file(file_path: str) -> dict:
    """解析單個提示詞文件
    
    Args:
        file_path: 提示詞文件路徑
        
    Returns:
        包含name, description, template的字典
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    filename = os.path.basename(file_path)
    name = os.path.splitext(filename)[0]
    description = f"AI任務提示詞: {name}"
            
    return {
        "name": name,
        "description": description,
        "template": content.strip()
    }


def get_all_prompt_files() -> dict:
    """從文件系統加載所有提示詞
    
    Returns:
        提示詞字典，key爲提示詞名稱
    """
    prompt_dir = os.path.join(os.path.dirname(__file__), 'prompts')
    if not os.path.exists(prompt_dir):
        logger.warning(f"Prompt directory not found at {prompt_dir}. Cannot load prompts.")
        return {}

    prompt_files = {}
    for filename in os.listdir(prompt_dir):
        if filename.endswith(('.prompt', '.txt')):
            file_path = os.path.join(prompt_dir, filename)
            name = os.path.splitext(filename)[0]
            prompt_files[name] = _parse_prompt_file(file_path)
    return prompt_files


@initializer(name="提示詞", order=10)
def init_prompts(session: Session) -> None:
    """初始化默認提示詞
    
    行爲受配置項 BOOTSTRAP_OVERWRITE 控制：
    - True: 覆蓋更新已存在的提示詞
    - False: 跳過已存在的提示詞
    
    Args:
        session: 數據庫會話
    """
    overwrite = settings.bootstrap.should_overwrite
    existing_prompts = session.exec(select(Prompt)).all()
    existing_names = {p.name for p in existing_prompts}

    all_prompts_data = get_all_prompt_files()

    new_count = 0
    updated_count = 0
    skipped_count = 0
    prompts_to_add = []
    
    for name, prompt_data in all_prompts_data.items():
        if name in existing_names:
            if overwrite:
                existing_prompt = next(p for p in existing_prompts if p.name == name)
                existing_prompt.template = prompt_data['template']
                existing_prompt.description = prompt_data.get('description')
                existing_prompt.built_in = True
                updated_count += 1
            else:
                skipped_count += 1
        else:
            prompts_to_add.append(Prompt(**prompt_data, built_in=True))
            new_count += 1
    
    if prompts_to_add:
        session.add_all(prompts_to_add)

    if new_count > 0 or updated_count > 0:
        session.commit()
        logger.info(f"提示詞更新完成: 新增 {new_count} 個，更新 {updated_count} 個（overwrite={overwrite}，跳過 {skipped_count} 個）。")
    else:
        logger.info(f"所有提示詞已是最新狀態（overwrite={overwrite}，跳過 {skipped_count} 個）。")
