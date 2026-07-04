"""表達式驗證器（與執行引擎同源規則）"""

from typing import List

from .evaluator import validate_expression_syntax


class ExpressionValidator:
    """表達式驗證器"""

    def validate(self, expression: str) -> List[str]:
        return validate_expression_syntax(expression)


def validate_expression(expression: str) -> List[str]:
    """便捷函數：驗證表達式"""
    validator = ExpressionValidator()
    return validator.validate(expression)

