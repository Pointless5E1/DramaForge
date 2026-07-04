"""執行計劃

表示工作流的執行計劃，包含語句列表、依賴關係和並行組。
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any


@dataclass
class Statement:
    """單條語句（一個節點調用或表達式）"""
    line_number: int
    variable: str              # 變量名
    node_type: Optional[str]   # 節點類型（如"Novel.Load"），None表示純表達式
    config: Dict[str, Any]     # 節點配置
    is_async: bool             # 是否異步執行
    depends_on: List[str]      # 依賴的變量列表
    code: Optional[str] = None # 原始代碼
    disabled: bool = False     # 是否禁用（從元數據註釋中提取）
    description: str = ""      # 節點描述（來自 #@node(description=...) 元數據）

    def __repr__(self):
        return f"Statement(line={self.line_number}, var={self.variable}, type={self.node_type}, disabled={self.disabled})"


@dataclass
class ExecutionPlan:
    """執行計劃"""
    statements: List[Statement]           # 語句列表（按代碼順序）
    dependencies: Dict[str, List[str]]    # 依賴關係：變量 → 依賴的變量列表

    def get_parallel_groups(self) -> List[List[Statement]]:
        """獲取可並行執行的語句組

        設計原則：
        1. 默認順序執行：每個語句一個組
        2. async 節點：標記爲異步，但立即返回，不阻塞後續語句
        3. wait 語句：等待之前的異步節點完成

        返回：[[stmt1], [stmt2], [stmt3]]
        表示：按順序執行每個語句
        """
        # 簡化實現：每個語句一個組，順序執行
        # async 和 wait 的處理在 AsyncExecutor 中實現
        groups = [[stmt] for stmt in self.statements]
        return groups

    def _can_merge_with_last_group(
        self,
        last_group: List[Statement],
        new_stmts: List[Statement]
    ) -> bool:
        """檢查新語句是否可以與上一組並行執行

        條件：新語句不依賴上一組中的任何變量
        """
        last_group_vars = {stmt.variable for stmt in last_group}

        for new_stmt in new_stmts:
            # 如果新語句依賴上一組的變量，不能並行
            if any(dep in last_group_vars for dep in new_stmt.depends_on):
                return False

        return True

    def validate(self) -> None:
        """驗證執行計劃的正確性

        檢查：
        1. 所有依賴的變量都有定義
        2. 沒有循環依賴
        """
        defined_vars = set()

        for stmt in self.statements:
            # 檢查依賴
            for dep in stmt.depends_on:
                if dep not in defined_vars:
                    raise ValueError(
                        f"行 {stmt.line_number}: 變量 '{stmt.variable}' "
                        f"依賴未定義的變量 '{dep}'"
                    )

            # 添加到已定義集合
            defined_vars.add(stmt.variable)

        # 嘗試獲取並行組（會檢測循環依賴）
        try:
            self.get_parallel_groups()
        except ValueError as e:
            raise ValueError(f"執行計劃驗證失敗: {e}")
