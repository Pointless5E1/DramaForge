
from sqlmodel import SQLModel
from typing import Optional

# 1. 定義基礎模型 (Base Model)
class ProjectBase(SQLModel):
    name: str
    description: Optional[str] = None

# 2. 用於創建項目的模型 (Create Schema)
class ProjectCreate(ProjectBase):
    # 項目模板標識（如 "snowflake"），用於觸發對應的初始化工作流
    # None 表示空白項目，不觸發任何工作流
    template: Optional[str] = None

# 3. 用於從數據庫讀取項目的模型 (Read Schema)
class ProjectRead(ProjectBase):
    id: int

# 4. 用於更新項目的模型 (Update Schema)
class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None 