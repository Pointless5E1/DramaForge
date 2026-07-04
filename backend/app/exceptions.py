"""業務異常定義

服務層拋出這些異常，API 層負責轉換爲 HTTP 響應。
"""


class BusinessException(Exception):
    """業務異常
    
    Args:
        message: 錯誤消息
        status_code: HTTP 狀態碼（404/400/409等）
    """
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
