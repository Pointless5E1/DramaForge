# 所有 Data 節點已被刪除
# 在代碼式工作流中，這些功能可以用 Python 表達式替代：
# - Data.ExtractPath → 直接屬性訪問：novel.chapter_list
# - Data.Text → 字符串字面量："Hello World"
# - Data.Log → Python logger：logger.info(...)
# - Data.Reduce → Python reduce/sum：sum(numbers)
# - Data.GenerateRange → range + 列表推導：[{"index": i} for i in range(n)]
# - Data.Group → groupby/字典推導：{k: list(v) for k, v in groupby(...)}

__all__ = []
