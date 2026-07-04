from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.workflow_context import init_workflow_context, get_triggered_run_ids

class WorkflowHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. 初始化上下文（確保每個請求都有獨立的列表）
        init_workflow_context()
        
        # 2.處理請求
        response = await call_next(request)
        
        # 3. 檢查上下文並注入 Header
        run_ids = get_triggered_run_ids()
        if run_ids:
            # 如果已有該 Header（極少見），追加
            existing = response.headers.get("X-Workflows-Started")
            if existing:
                new_ids = f"{existing},{','.join(map(str, run_ids))}"
                response.headers["X-Workflows-Started"] = new_ids
            else:
                response.headers["X-Workflows-Started"] = ",".join(map(str, run_ids))
                
        return response
