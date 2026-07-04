from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
from app.db.models import Prompt
from app.schemas.prompt import PromptCreate, PromptUpdate
from string import Template
import re

def get_prompt(session: Session, prompt_id: int) -> Optional[Prompt]:
    """根據ID獲取單個提示詞"""
    return session.get(Prompt, prompt_id)

def get_prompt_by_name(session: Session, prompt_name: str) -> Optional[Prompt]:
    """根據名稱獲取單個提示詞"""
    statement = select(Prompt).where(Prompt.name == prompt_name)
    return session.exec(statement).first()

def get_prompts(session: Session, skip: int = 0, limit: int = 100) -> List[Prompt]:
    """獲取提示詞列表"""
    statement = select(Prompt).offset(skip).limit(limit)
    return session.exec(statement).all()

def create_prompt(session: Session, prompt_create: PromptCreate) -> Prompt:
    """創建新提示詞"""
    # 檢查名稱是否已存在
    existing_prompt = get_prompt_by_name(session, prompt_create.name)
    if existing_prompt:
        raise ValueError(f"提示詞名稱 '{prompt_create.name}' 已存在")
    
    db_prompt = Prompt.model_validate(prompt_create)
    session.add(db_prompt)
    session.commit()
    session.refresh(db_prompt)
    return db_prompt

def update_prompt(session: Session, prompt_id: int, prompt_update: PromptUpdate) -> Optional[Prompt]:
    """更新提示詞"""
    db_prompt = session.get(Prompt, prompt_id)
    if not db_prompt:
        return None
    prompt_data = prompt_update.model_dump(exclude_unset=True)
    for key, value in prompt_data.items():
        setattr(db_prompt, key, value)
    session.add(db_prompt)
    session.commit()
    session.refresh(db_prompt)
    return db_prompt

def delete_prompt(session: Session, prompt_id: int) -> bool:
    """刪除提示詞"""
    db_prompt = session.get(Prompt, prompt_id)
    if not db_prompt:
        return False
    session.delete(db_prompt)
    session.commit()
    return True

def render_prompt(prompt_template: str, context: Dict[str, Any]) -> str:
    """
    使用上下文渲染提示詞模板。
    
    :param prompt_template: 帶有佔位符的字符串模板 (e.g., "你好, ${name}")
    :param context: 包含要填充到模板中的值的字典 (e.g., {"name": "世界"})
    :return: 渲染後的字符串 ("你好, 世界")
    """
    template = Template(prompt_template)
    try:
        return template.substitute(context)
    except KeyError as e:
        raise ValueError(f"渲染提示詞失敗：上下文中缺少變量 '{e.args[0]}'")
    except Exception as e:
        raise ValueError(f"渲染提示詞時發生未知錯誤: {e}")


# 知識庫佔位符解析
_KB_ID_PATTERN = re.compile(r"@KB\{\s*id\s*=\s*(\d+)\s*\}")
_KB_NAME_PATTERN = re.compile(r"@KB\{\s*name\s*=\s*([^}]+)\}")


def inject_knowledge(session: Session, template: str) -> str:
    """將模板中的知識庫佔位符注入爲實際內容
    
    規則：
    1) 對 "- knowledge:" 段落內的多個佔位符，按順序注入並以編號分隔：
       - knowledge:\n1.\n<KB1>\n\n2.\n<KB2> ...
    2) knowledge 段之外若出現佔位符，做就地替換爲知識全文。
    3) 若找不到對應知識庫，保留提示註釋，避免中斷。
    
    Args:
        session: 數據庫會話
        template: 提示詞模板
        
    Returns:
        注入知識庫後的模板
    """
    from app.services.knowledge_service import KnowledgeService
    
    svc = KnowledgeService(session)

    def fetch_kb_by_id(kid: int) -> str:
        kb = svc.get_by_id(kid)
        return kb.content if kb and kb.content else f"/* 知識庫未找到: id={kid} */"

    def fetch_kb_by_name(name: str) -> str:
        kb = svc.get_by_name(name)
        return kb.content if kb and kb.content else f"/* 知識庫未找到: name={name} */"

    # 先處理 knowledge 分段（更結構化的注入）
    lines = template.splitlines()
    i = 0
    out_lines: list[str] = []
    while i < len(lines):
        line = lines[i]
        # 匹配頂級的 "- knowledge:" 行（大小寫不敏感）
        if re.match(r"^\s*-\s*knowledge\s*:\s*$", line, flags=re.IGNORECASE):
            # 收集該段落內的佔位符行，直到遇到下一個頂級 "- <Something>" 行或文件結尾
            j = i + 1
            block_lines: list[str] = []
            while j < len(lines) and not re.match(r"^\s*-\s*\w", lines[j]):
                block_lines.append(lines[j])
                j += 1
            # 提取佔位符順序
            placeholders: list[tuple[str, str]] = []  # (mode, value)
            for bl in block_lines:
                for m in _KB_ID_PATTERN.finditer(bl):
                    placeholders.append(("id", m.group(1)))
                for m in _KB_NAME_PATTERN.finditer(bl):
                    placeholders.append(("name", m.group(1).strip().strip('\"\'')))
            # 構建編號內容
            out_lines.append(line)  # 保留標題行 "- knowledge:"
            if placeholders:
                for idx, (mode, val) in enumerate(placeholders, start=1):
                    out_lines.append(f"{idx}.")
                    if mode == "id":
                        try:
                            content = fetch_kb_by_id(int(val))
                        except Exception:
                            content = f"/* 知識庫未找到: id={val} */"
                    else:
                        content = fetch_kb_by_name(val)
                    out_lines.append(content.strip())
                    # 段落間空行
                    if idx < len(placeholders):
                        out_lines.append("")
            # 跳過原 block
            i = j
            continue
        else:
            out_lines.append(line)
            i += 1

    enumerated_text = "\n".join(out_lines)

    # knowledge 段之外的就地替換（若仍有佔位符殘留）
    def repl_id(m: re.Match) -> str:
        try:
            kid = int(m.group(1))
        except Exception:
            return f"/* 知識庫未找到: id={m.group(1)} */"
        return fetch_kb_by_id(kid)

    def repl_name(m: re.Match) -> str:
        name = m.group(1).strip().strip('\"\'')
        return fetch_kb_by_name(name)

    result = _KB_ID_PATTERN.sub(repl_id, enumerated_text)
    result = _KB_NAME_PATTERN.sub(repl_name, result)
    return result 