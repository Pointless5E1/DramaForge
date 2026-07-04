"""Bootstrap初始化模塊

基於裝飾器的插件化初始化系統。

## 架構設計

使用 @initializer 裝飾器實現自動發現和註冊：
- 每個初始化器獨立成文件，通過裝飾器聲明
- 啓動時自動掃描並按 order 順序執行
- 新增初始化器無需修改任何現有代碼

## 模塊結構

- registry.py: 裝飾器和自動發現機制
- prompts.py: 提示詞初始化
- card_types.py: 卡片類型初始化
- knowledge.py: 知識庫初始化  
- projects.py: 保留項目初始化
- workflows.py: 工作流初始化

## 使用方式

### 定義初始化器
```python
from .registry import initializer

@initializer(name="我的功能", order=60)
def init_my_feature(session: Session):
    logger.info("初始化我的功能...")
    # ... 初始化邏輯
```

### 自動執行所有初始化器
```python
from app.bootstrap.registry import discover_and_run_initializers

with Session(engine) as session:
    discover_and_run_initializers(session)
```

## 執行順序

初始化器按 order 值從小到大執行：
- 10: 提示詞
- 20: 卡片類型
- 30: 知識庫
- 40: 保留項目
- 50: 工作流
- 60+: 自定義初始化器
"""

# 導出核心功能
from .registry import initializer, discover_and_run_initializers

# 導入所有初始化器模塊以觸發裝飾器註冊
from . import prompts
from . import card_types
from . import workflows
from . import knowledge

__all__ = [
    'initializer',
    'discover_and_run_initializers',
]
