"""Token估算工具

純函數實現，無外部依賴。
"""

import re
from typing import Optional

_TOKEN_REGEX = re.compile(
    r"""
    ([A-Za-z]+)               # 英文單詞（連續字母算1）
    |([0-9])                 # 1個數字算1
    |([\u4E00-\u9FFF])       # 單箇中文漢字算1
    |(\S)                     # 其它非空白符號/標點算1
    """,
    re.VERBOSE,
)


def estimate_tokens(text: str) -> int:
    """估算token數量
    
    規則：
    - 1箇中文 = 1 token
    - 1個英文單詞 = 1 token
    - 1個數字 = 1 token
    - 1個符號 = 1 token
    - 空白不計
    
    Args:
        text: 待估算的文本
        
    Returns:
        估算的token數量
    """
    if not text:
        return 0
    try:
        return sum(1 for _ in _TOKEN_REGEX.finditer(text))
    except Exception:
        # 退化方案：按非空白字符計數
        return sum(1 for ch in text if not ch.isspace())


def calc_input_tokens(system_prompt: Optional[str], user_prompt: Optional[str]) -> int:
    """計算輸入token總數
    
    Args:
        system_prompt: 系統提示詞
        user_prompt: 用戶提示詞
        
    Returns:
        總token數
    """
    sys_part = system_prompt or ""
    usr_part = user_prompt or ""
    return int(round(0.6 * estimate_tokens(sys_part + usr_part)))
