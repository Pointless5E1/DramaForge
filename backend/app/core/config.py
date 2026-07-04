"""應用配置管理

統一管理所有配置項，支持環境變量和默認值。
"""

import os
import sys
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class DatabaseSettings(BaseSettings):
    """數據庫配置"""
    
    # 數據庫路徑
    db_path: Optional[str] = Field(default=None, alias="NOVELFORGE_DB_PATH")
    
    # 是否打印SQL日誌
    echo: bool = Field(default=False, alias="DB_ECHO")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略額外字段
    
    def get_database_url(self) -> str:
        """獲取數據庫URL
        
        策略：
        1) 打包(onefile/onedir)：優先放在可執行文件同目錄
        2) 開發態：放在源碼 backend 目錄
        3) 支持通過環境變量 NOVELFORGE_DB_PATH 覆蓋絕對路徑（兼容舊變量 AIAUTHOR_DB_PATH）
        
        Returns:
            數據庫URL
        """
        override_path = self.db_path or os.getenv("AIAUTHOR_DB_PATH")
        if override_path:
            db_file = Path(override_path)
        else:
            if getattr(sys, "frozen", False):
                base_dir = Path(sys.executable).resolve().parent
            else:
                # 從 app/core/config.py 向上2層到 backend/
                # config.py -> core/ -> app/ -> backend/
                base_dir = Path(__file__).resolve().parents[2]
            db_file = base_dir / 'novelforge.db'
        
        return f"sqlite:///{db_file.as_posix()}"


class KnowledgeGraphSettings(BaseSettings):
    """知識圖譜配置"""
    
    # 知識圖譜Provider
    provider: str = Field(default="sqlmodel", alias="KNOWLEDGE_GRAPH_PROVIDER")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略額外字段


class Neo4jSettings(BaseSettings):
    """Neo4j圖數據庫配置"""
    
    uri: str = Field(default="neo4j://127.0.0.1:7687", alias="NEO4J_URI")
    user: str = Field(default="neo4j", alias="NEO4J_USER")
    password: str = Field(default="neo4j", alias="NEO4J_PASSWORD")
    
    # 兼容舊環境變量
    graph_db_uri: Optional[str] = Field(default=None, alias="GRAPH_DB_URI")
    graph_db_user: Optional[str] = Field(default=None, alias="GRAPH_DB_USER")
    graph_db_password: Optional[str] = Field(default=None, alias="GRAPH_DB_PASSWORD")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略額外字段
    
    def get_uri(self) -> str:
        """獲取URI（兼容舊環境變量）"""
        return self.graph_db_uri or self.uri
    
    def get_user(self) -> str:
        """獲取用戶名（兼容舊環境變量）"""
        return self.graph_db_user or self.user
    
    def get_password(self) -> str:
        """獲取密碼（兼容舊環境變量）"""
        return self.graph_db_password or self.password


class BootstrapSettings(BaseSettings):
    """啓動初始化配置"""
    
    # 是否覆蓋更新內置數據（提示詞、知識庫等）
    overwrite: bool = Field(default=True, alias="BOOTSTRAP_OVERWRITE")
    # 是否覆蓋內置卡片類型的 schema
    overwrite_card_schemas: bool = Field(default=False, alias="BOOTSTRAP_OVERWRITE_CARD_SCHEMAS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略額外字段
    
    @property
    def should_overwrite(self) -> bool:
        """是否應該覆蓋更新
        
        支持多種格式：true/false, 1/0, yes/no, on/off
        
        Returns:
            是否覆蓋
        """
        if isinstance(self.overwrite, bool):
            return self.overwrite
        return str(self.overwrite).lower() in ('1', 'true', 'yes', 'on')

    @property
    def should_overwrite_card_schemas(self) -> bool:
        """是否應該覆蓋內置卡片類型結構。"""
        if isinstance(self.overwrite_card_schemas, bool):
            return self.overwrite_card_schemas
        return str(self.overwrite_card_schemas).lower() in ('1', 'true', 'yes', 'on')


class AISettings(BaseSettings):
    """AI相關配置"""
    
    # 模型調用失敗時最大重試次數
    max_tool_call_retries: int = Field(default=3, alias="MAX_TOOL_CALL_RETRIES")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略額外字段


class AppSettings(BaseSettings):
    """應用配置"""
    
    # 應用名稱
    app_name: str = Field(default="NovelForge", alias="APP_NAME")
    
    # 應用版本
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    
    # 是否開啓調試模式
    debug: bool = Field(default=False, alias="DEBUG")
    
    # API前綴
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    
    # CORS允許的源
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # 忽略額外字段
    
    def get_cors_origins_list(self) -> list:
        """獲取CORS源列表
        
        Returns:
            源列表
        """
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]


class WorkflowSettings(BaseSettings):
    """工作流配置"""
    
    # 持久化記錄保留時間（天）
    retention_persistent_days: int = Field(default=30, alias="WORKFLOW_RETENTION_PERSISTENT_DAYS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


class Settings:
    """全局配置對象"""
    
    def __init__(self):
        self.database = DatabaseSettings()
        self.kg = KnowledgeGraphSettings()
        self.neo4j = Neo4jSettings()
        self.ai = AISettings()
        self.bootstrap = BootstrapSettings()
        self.workflow = WorkflowSettings()
        self.app = AppSettings()
    
    def __repr__(self) -> str:
        return (
            f"Settings(\n"
            f"  database_url={self.database.get_database_url()},\n"
            f"  kg_provider={self.kg.provider},\n"
            f"  neo4j_uri={self.neo4j.get_uri()},\n"
            f"  max_retries={self.ai.max_tool_call_retries},\n"
            f"  bootstrap_overwrite={self.bootstrap.should_overwrite},\n"
            f"  bootstrap_overwrite_card_schemas={self.bootstrap.should_overwrite_card_schemas},\n"
            f"  app_name={self.app.app_name}\n"
            f")"
        )


# 全局配置實例
settings = Settings()
