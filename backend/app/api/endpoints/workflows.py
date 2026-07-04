from typing import List, Optional, Dict, Any
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from datetime import datetime
from loguru import logger

from app.db.session import get_session
from app.db.models import Workflow, WorkflowRun
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowRead,
    WorkflowRunRead,
    RunRequest,
    CancelResponse,
    RunStatus,
    NodeTypesResponse,
)
from app.schemas.workflow_agent import WorkflowPatchRequest, WorkflowPatchResponse
from app.services.workflow.patcher import (
    compute_code_revision,
    execute_patch_with_validation,
    parse_workflow_code_to_result,
)


def _clean_dollar_prefix(value: Any) -> Any:
    """遞歸清理值中的 $ 前綴
    
    $ 前綴是後端內部用來標記變量引用的，前端不需要知道。
    在返回給前端時，需要去掉 $ 前綴。
    
    Args:
        value: 任意值（字符串、列表、字典等）
        
    Returns:
        清理後的值
    """
    if isinstance(value, str):
        # 去掉 $ 前綴（變量引用）
        if value.startswith('$'):
            # 處理 ${expression} 格式
            if value.startswith('${') and value.endswith('}'):
                return value[2:-1]  # 去掉 ${ 和 }
            else:
                return value[1:]  # 去掉 $
        return value
    elif isinstance(value, list):
        # 遞歸處理列表
        return [_clean_dollar_prefix(item) for item in value]
    elif isinstance(value, dict):
        # 遞歸處理字典
        return {
            _clean_dollar_prefix(k): _clean_dollar_prefix(v)
            for k, v in value.items()
        }
    else:
        # 其他類型保持不變
        return value
from app.services.workflow import (
    get_node_types,
    get_all_node_metadata,
    RunManager
)
from app.services.workflow.engine.runtime import workflow_runtime


router = APIRouter()


@router.get("/nodes/types", response_model=NodeTypesResponse)
def get_node_types_api():
    """獲取所有已註冊的工作流節點類型（含完整元數據）
    
    用於前端動態生成節點庫和屬性面板。
    包含了基於 Pydantic 生成的 JSON Schema。
    """
    all_metadata = get_all_node_metadata()
    
    node_info = []
    for meta in all_metadata:
        node_info.append({
            "type": meta.type,
            "category": meta.category,
            "label": meta.label,
            "description": meta.description,
            "documentation": meta.documentation,  # 添加完整文檔
            "input_schema": meta.input_schema,
            "output_schema": meta.output_schema
        })
    
    return {"node_types": node_info}





@router.get("/workflow-node-types/categories")
def get_node_categories():
    """獲取節點分類列表"""
    all_metadata = get_all_node_metadata()
    categories = {}

    for meta in all_metadata:
        if meta.category not in categories:
            categories[meta.category] = []
        categories[meta.category].append({
            'type': meta.type,
            'label': meta.label,
            'description': meta.description
        })

    return {'categories': categories}


@router.get("/nodes/{node_type}/metadata")
def get_node_metadata_api(node_type: str):
    """獲取單個節點的完整元數據

    Args:
        node_type: 節點類型，如 "Novel.Load" 或 "Card.BatchUpsert"

    Returns:
        節點的完整元數據，包括：
        - type: 節點類型
        - category: 分類
        - label: 顯示名稱
        - description: 描述
        - input_schema: 輸入字段的 JSON Schema（從 input_model 生成）
        - output_schema: 輸出字段的 JSON Schema（從 output_model 生成）
        - outputs: 輸出字段列表（從 output_schema 提取）
    """
    from app.services.workflow.registry import get_node_metadata as get_registry_metadata
    
    # 從註冊表獲取節點元數據
    registry_meta = get_registry_metadata(node_type)
    if not registry_meta:
        raise HTTPException(status_code=404, detail=f"節點類型不存在: {node_type}")
    
    # 從 output_schema 提取輸出字段列表
    outputs = []
    if registry_meta.output_schema and "properties" in registry_meta.output_schema:
        for field_name, field_def in registry_meta.output_schema["properties"].items():
            outputs.append({
                "name": field_name,
                "type": field_def.get("type", "any"),
                "description": field_def.get("description", "")
            })
    
    # 返回元數據
    metadata = {
        "type": registry_meta.type,
        "category": registry_meta.category,
        "label": registry_meta.label,
        "description": registry_meta.description,
        "documentation": registry_meta.documentation,  # 添加完整文檔
        "input_schema": registry_meta.input_schema,
        "output_schema": registry_meta.output_schema,
        "outputs": outputs  # 添加輸出字段列表
    }
    
    return metadata





@router.get("/workflows", response_model=List[WorkflowRead])
def list_workflows(session: Session = Depends(get_session)):
    return session.exec(select(Workflow)).all()


@router.post("/workflows", response_model=WorkflowRead)
def create_workflow(payload: WorkflowCreate, session: Session = Depends(get_session)):
    wf = Workflow(**payload.model_dump())
    session.add(wf)
    session.commit()
    session.refresh(wf)
    
    # 同步觸發器緩存（優化性能）
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(wf, session)
    
    session.commit()
    
    return wf


@router.get("/workflows/project-templates")
def get_project_templates(session: Session = Depends(get_session)):
    """獲取項目創建模板列表
    
    返回所有包含 Trigger.ProjectCreated 觸發器的工作流，
    以及它們的模板標識（template 參數）。
    
    前端可以根據這些信息渲染項目創建對話框的模板選擇下拉框。
    """
    # 查詢所有激活的工作流
    stmt = select(Workflow).where(Workflow.is_active == True)
    workflows = session.exec(stmt).all()
    
    templates = []
    
    for wf in workflows:
        if not wf.triggers_cache:
            continue
        
        # 查找項目創建觸發器
        for trigger in wf.triggers_cache:
            if trigger.get("event") == "project.created":
                # 提取 template 參數
                match = trigger.get("match") or {}
                template_id = match.get("template")
                
                templates.append({
                    "workflow_id": wf.id,
                    "workflow_name": wf.name,
                    "template": template_id,  # 模板標識（如 "snowflake"）
                    "description": wf.description
                })
    
    logger.info(f"[API] 找到 {len(templates)} 個項目創建模板")
    return {"templates": templates}


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(workflow_id: int, payload: WorkflowUpdate, session: Session = Depends(get_session)):
    """更新工作流"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(wf, k, v)
    
    wf.updated_at = datetime.utcnow()
    session.add(wf)
    session.commit()
    session.refresh(wf)
    
    # 同步觸發器緩存（新方式 - 優化性能）
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(wf, session)
    session.commit()
    
    return wf


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int, session: Session = Depends(get_session)):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    session.delete(wf)
    session.commit()
    return {"ok": True}


@router.get("/workflows/runs/{run_id}", response_model=WorkflowRunRead)
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/workflows/{workflow_id}/runs", response_model=List[WorkflowRunRead])
def list_workflow_runs(
    workflow_id: int,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """獲取指定工作流的運行列表
    
    Args:
        workflow_id: 工作流 ID
        limit: 返回數量限制（默認 50）
        offset: 偏移量（默認 0）
        status: 過濾狀態（可選）：running, paused, succeeded, failed, cancelled
    
    Returns:
        運行列表，按創建時間倒序
    """
    from sqlmodel import select, desc
    
    stmt = select(WorkflowRun).where(
        WorkflowRun.workflow_id == workflow_id
    )
    
    # 添加狀態篩選
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    
    stmt = stmt.order_by(
        desc(WorkflowRun.created_at)
    ).limit(limit).offset(offset)
    
    runs = session.exec(stmt).all()
    return runs


@router.get("/runs", response_model=List[WorkflowRunRead])
def list_all_runs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """獲取所有工作流的運行列表
    
    Args:
        limit: 返回數量限制（默認 50）
        offset: 偏移量（默認 0）
        status: 過濾狀態（可選）：running, paused, succeeded, failed, cancelled
    
    Returns:
        運行列表，按創建時間倒序
    """
    from sqlmodel import select, desc
    import logging
    logger = logging.getLogger(__name__)
    
    stmt = select(WorkflowRun).order_by(desc(WorkflowRun.created_at))
    
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    
    stmt = stmt.limit(limit).offset(offset)
    
    runs = session.exec(stmt).all()
    
    # 調試：打印第一個運行的時間
    if runs:
        logger.info(f"[list_all_runs] 第一個運行: id={runs[0].id}, created_at={runs[0].created_at}, type={type(runs[0].created_at)}")
    
    return runs


@router.post("/workflows/{workflow_id}/validate")
def validate_workflow_endpoint(workflow_id: int, session: Session = Depends(get_session)):
    """驗證工作流定義（完整靜態檢查）
    
    檢查內容：
    - 語法錯誤
    - 節點類型錯誤
    - 字段訪問錯誤
    - 表達式語法錯誤
    - 類型不匹配
    - Expression 節點特殊規則
    """
    from app.services.workflow.validator import validate_workflow
    
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    code = wf.definition_code or ""
    
    if not code:
        return {
            "is_valid": False,
            "errors": [{
                "line": 0,
                "variable": "",
                "error_type": "syntax",
                "message": "工作流缺少代碼內容",
                "suggestion": None
            }],
            "warnings": []
        }
    
    # 執行完整校驗
    result = validate_workflow(code, session=session)
    
    return result.to_dict()


@router.post("/workflows/runs/{run_id}/cancel", response_model=CancelResponse)
async def cancel_run(run_id: int, session: Session = Depends(get_session)):
    """取消運行中的工作流"""
    run_manager = RunManager(session)
    ok = await run_manager.cancel_run(run_id)
    return CancelResponse(ok=ok, message="cancelled" if ok else "not running")


@router.post("/workflows/runs/{run_id}/pause")
async def pause_run(run_id: int, session: Session = Depends(get_session)):
    """暫停運行中的工作流
    
    通過共享運行時請求暫停，並更新數據庫狀態。
    """
    logger.info(f"[API] 收到暫停請求: run_id={run_id}")
    
    # 獲取運行記錄
    run = session.get(WorkflowRun, run_id)
    if not run:
        logger.warning(f"[API] 運行不存在: run_id={run_id}")
        raise HTTPException(status_code=404, detail="Run not found")
    
    if run.status == "paused":
        logger.info(f"[API] 運行已處於暫停狀態: run_id={run_id}")
        return {"ok": True, "message": "paused"}

    # 檢查狀態
    if run.status not in ["running", "queued"]:
        logger.warning(f"[API] 運行狀態不是 running 或 queued: run_id={run_id}, status={run.status}")
        raise HTTPException(status_code=400, detail=f"無法暫停狀態爲 {run.status} 的運行")
    
    if not workflow_runtime.request_pause(run_id):
        logger.warning(f"[API] 未找到進程內執行器，仍將運行標記爲暫停: run_id={run_id}")
    
    # 更新狀態爲暫停
    run.status = "paused"
    session.add(run)
    session.commit()
    
    logger.info(f"[API] 暫停成功: run_id={run_id}")
    return {"ok": True, "message": "paused"}


@router.post("/workflows/runs/{run_id}/resume")
async def resume_run(run_id: int, session: Session = Depends(get_session)):
    """恢復暫停的工作流
    
    如果服務器重啓，會重新啓動運行並自動恢復狀態。
    """
    run_manager = RunManager(session)
    ok = await run_manager.resume_run(run_id)
    if not ok:
        raise HTTPException(status_code=400, detail="無法恢復運行（運行不存在或狀態不是暫停）")
    return {"ok": True, "message": "resumed"}


@router.get("/workflows/{workflow_id}/execute-stream")
async def execute_code_workflow_stream(
    workflow_id: int,
    resume: bool = False,
    run_id: Optional[int] = None,
    session: Session = Depends(get_session)
):
    """執行代碼式工作流（流式SSE推送）

    實時推送執行事件，同時創建 run 記錄並保存狀態（支持暫停/恢復）。
    
    Args:
        workflow_id: 工作流 ID
        resume: 是否恢復執行（默認 False，從頭開始）
        run_id: 恢復執行時的 run ID（resume=True 時必須提供）
    """
    import json
    from app.services.workflow.parser.marker_parser import WorkflowParser
    from app.services.workflow.engine.async_executor import AsyncExecutor
    from app.services.workflow.engine.state_manager import StateManager
    from app.services.workflow.registry import NodeRegistry

    # 獲取工作流
    workflow = session.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not workflow.is_active:
        raise HTTPException(status_code=400, detail="Workflow is not active")

    code = workflow.definition_code or ""
    if not code:
        raise HTTPException(status_code=400, detail="Workflow code is empty")

    # 處理 run 記錄
    run_manager = RunManager(session)
    
    if resume:
        # 恢復執行：必須提供 run_id
        if not run_id:
            raise HTTPException(status_code=400, detail="resume=True 時必須提供 run_id")
        
        run = session.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        
        if run.workflow_id != workflow_id:
            raise HTTPException(status_code=400, detail="Run 不屬於該工作流")
        
        workflow_runtime.request_resume(run_id)
        logger.info(f"[CodeWorkflow] 準備恢復運行: run_id={run_id}, workflow_id={workflow_id}")
    else:
        # 新建執行：使用 RunManager 創建（帶冪等性保護）
        # 生成冪等鍵：基於工作流ID和時間窗口（5秒）
        from datetime import datetime
        time_window = int(datetime.utcnow().timestamp() / 5)  # 5秒時間窗口
        idempotency_key = f"manual_exec:{workflow_id}:{time_window}"
        
        run = run_manager.create_run(
            workflow_id=workflow_id,
            idempotency_key=idempotency_key
        )
        run_id = run.id
        
        # 如果是複用的運行記錄，檢查狀態
        if run.status == "running":
            logger.warning(f"[CodeWorkflow] 複用現有運行記錄（冪等性保護）: run_id={run_id}, workflow_id={workflow_id}")
        else:
            logger.info(f"[CodeWorkflow] 創建運行記錄: run_id={run_id}, workflow_id={workflow_id}")

    async def event_stream():
        """流式推送執行事件"""
        executor = None
        state_manager = StateManager(session)
        try:
            workflow_runtime.register_task(run_id)

            slot_status = await workflow_runtime.acquire_slot(run_id)
            if slot_status == "cancelled":
                state_manager.update_run_status(run_id, "cancelled")
                yield f"data: {json.dumps({'type': 'cancelled', 'message': '工作流已取消'}, ensure_ascii=False)}\n\n"
                return
            if slot_status == "paused":
                state_manager.update_run_status(run_id, "paused")
                yield f"data: {json.dumps({'type': 'paused', 'message': '工作流已暫停'}, ensure_ascii=False)}\n\n"
                return

            state_manager.update_run_status(run_id, "running")

            # 解析代碼
            from app.services.workflow.parser.marker_parser import WorkflowParser
            parser = WorkflowParser()
            plan = parser.parse(code)

            logger.info(f"[CodeWorkflow] 開始流式執行: run_id={run_id}, 語句數={len(plan.statements)}, resume={resume}")

            # 創建狀態管理器和執行器
            # 如果不是恢復執行，清理舊狀態
            if not resume:
                from app.services.workflow.engine.execution_state import ExecutionState
                exec_state = ExecutionState(run_id)
                exec_state.clear_node_states(session)
            
            executor = AsyncExecutor(
                session=session,
                state_manager=state_manager,
                run_id=run_id
            )
            
            # 保存執行器引用（用於暫停）
            workflow_runtime.register_executor(run_id, executor)
            logger.info(f"[CodeWorkflow] 執行器已註冊: run_id={run_id}")

            # 推送 run_id（讓前端知道當前運行的 ID）
            yield f"data: {json.dumps({'type': 'run_started', 'run_id': run_id}, ensure_ascii=False)}\n\n"

            # 流式執行
            async for event in executor.execute_stream(plan, initial_context={}):
                # 檢查是否已暫停（優先檢查）
                if executor.is_paused or workflow_runtime.is_pause_requested(run_id):
                    logger.info(f"[CodeWorkflow] 檢測到暫停狀態，停止執行: run_id={run_id}")
                    state_manager.update_run_status(run_id, "paused")
                    # 推送暫停事件
                    yield f"data: {json.dumps({'type': 'paused', 'message': '工作流已暫停'}, ensure_ascii=False)}\n\n"
                    return  # 停止生成器
                
                # 構造SSE事件
                event_data = {
                    "type": event.type,
                    "statement": {
                        "variable": event.statement.variable,
                        "code": event.statement.code or f"{event.statement.variable} = {event.statement.node_type or 'expression'}(...)",
                        "line": event.statement.line_number,
                        "description": getattr(event.statement, 'description', '') or "",
                    }
                }

                if event.type == "start":
                    event_data["message"] = event.message or f"開始執行: {event.statement.variable}"
                elif event.type == "progress":
                    event_data["percent"] = event.percent
                    event_data["message"] = event.message
                elif event.type == "complete":
                    event_data["result"] = event.result
                    # 檢查是否是恢復的節點
                    if event.message and "[已恢復]" in event.message:
                        event_data["resumed"] = True
                elif event.type == "error":
                    event_data["error"] = event.error

                # 推送事件
                try:
                    yield f"data: {json.dumps(event_data, ensure_ascii=False, default=str)}\n\n"
                except Exception as e:
                    # 如果推送失敗（客戶端斷開），停止執行
                    logger.warning(f"[CodeWorkflow] 推送事件失敗（客戶端可能斷開）: {e}")
                    executor.pause()  # 標記爲暫停
                    return

            # 更新 run 狀態爲成功
            state_manager.update_run_status(run_id, "succeeded")

            # 推送完成事件
            yield f"data: {json.dumps({'type': 'end', 'message': '工作流執行完成'}, ensure_ascii=False)}\n\n"

            logger.info(f"[CodeWorkflow] 流式執行完成: run_id={run_id}")

        except asyncio.CancelledError:
            is_cancelled = workflow_runtime.is_cancel_requested(run_id)
            status = "cancelled" if is_cancelled else "paused"
            reason = "取消" if is_cancelled else "客戶端斷開連接，暫停執行"
            logger.info(f"[CodeWorkflow] {reason}: run_id={run_id}")
            try:
                state_manager.update_run_status(run_id, status)
            except:
                pass
            raise  # 重新拋出以正確關閉連接
            
        except Exception as e:
            logger.exception(f"[CodeWorkflow] 流式執行失敗: run_id={run_id}")
            
            # 更新 run 狀態爲失敗
            try:
                state_manager = StateManager(session)
                state_manager.update_run_status(run_id, "failed")
            except:
                pass
            
            error_data = {
                "type": "error",
                "error": str(e),
                "message": "工作流執行失敗"
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        
        finally:
            if executor is not None:
                workflow_runtime.unregister_executor(run_id, executor)
            workflow_runtime.finish_run(
                run_id,
                keep_pause=workflow_runtime.is_pause_requested(run_id)
            )
            logger.info(f"[CodeWorkflow] 運行時狀態已清理: run_id={run_id}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete("/workflows/runs/{run_id}")
def delete_run(run_id: int, session: Session = Depends(get_session)):
    """刪除運行記錄
    
    刪除指定的運行記錄及其相關的節點狀態。
    """
    # 獲取運行記錄
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # 檢查狀態：不允許刪除正在運行的記錄
    if run.status == "running":
        raise HTTPException(status_code=400, detail="無法刪除正在運行的記錄，請先暫停或取消")
    
    # 刪除相關的節點狀態
    from app.db.models import NodeExecutionState
    stmt = select(NodeExecutionState).where(NodeExecutionState.run_id == run_id)
    node_states = session.exec(stmt).all()
    for node_state in node_states:
        session.delete(node_state)
    
    # 刪除運行記錄
    session.delete(run)
    session.commit()
    
    logger.info(f"[API] 運行記錄已刪除: run_id={run_id}")
    return {"ok": True, "message": "deleted"}


@router.get("/workflows/runs/{run_id}/status", response_model=RunStatus)
def get_run_status(run_id: int, session: Session = Depends(get_session)):
    """獲取運行狀態（包含節點狀態）"""
    run_manager = RunManager(session)
    status = run_manager.get_run_status(run_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return status


@router.get("/workflows/templates")
def list_templates(session: Session = Depends(get_session)):
    """獲取工作流模板列表"""
    stmt = select(Workflow).where(Workflow.is_template == True)
    templates = session.exec(stmt).all()
    return {"templates": templates}


@router.post("/workflows/from-template/{template_id}", response_model=WorkflowRead)
def create_from_template(
    template_id: int,
    name: str,
    session: Session = Depends(get_session)
):
    """從模板創建工作流"""
    template = session.get(Workflow, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    if not template.is_template:
        raise HTTPException(status_code=400, detail="不是模板")
    
    new_workflow = Workflow(
        name=name,
        description=f"基於模板「{template.name}」創建",
        definition_code=template.definition_code,
        dsl_version=template.dsl_version,
        is_template=False
    )
    
    session.add(new_workflow)
    session.commit()
    session.refresh(new_workflow)
    
    # 同步觸發器緩存
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(new_workflow, session)
    session.commit()
    
    return new_workflow


# ============================================================
# 代碼式工作流 API
# ============================================================

@router.post("/workflows/parse")
def parse_workflow_code(payload: Dict[str, Any]):
    """解析工作流代碼（驗證語法）
    
    Args:
        payload: 包含 code 字段的字典（註釋標記 DSL）
        
    Returns:
        解析結果
    """
    code = payload.get("code", "")
    if not code:
        return {"success": False, "errors": ["代碼不能爲空"]}

    parsed = parse_workflow_code_to_result(code)
    if not parsed.get("ok"):
        error = str(parsed.get("error") or "parse_failed")
        logger.error(f"代碼解析失敗: {error}")
        return {
            "success": False,
            "errors": [error],
        }

    statements = []
    for stmt in parsed.get("statements", []):
        variable = stmt.get("variable")
        cleaned_config = _clean_dollar_prefix(stmt.get("config"))
        statements.append({
            "variable": variable,
            "code": stmt.get("code") or (f"{variable} = ..." if variable else "..."),
            "line": stmt.get("line"),
            "node_type": stmt.get("node_type"),
            "config": cleaned_config,
            "is_async": bool(stmt.get("is_async")),
            "disabled": bool(stmt.get("disabled")),
            "description": stmt.get("description", "") or "",
        })

    return {
        "success": True,
        "statements": statements,
    }


@router.post("/workflows/rename-variable")
def rename_variable(payload: Dict[str, Any]):
    """重命名變量並更新所有引用
    
    Args:
        payload: 包含 code, old_name, new_name 的字典
        
    Returns:
        重命名結果
    """
    from app.services.workflow.parser.marker_renamer import rename_variable as marker_rename
    
    code = payload.get("code", "")
    old_name = payload.get("old_name", "")
    new_name = payload.get("new_name", "")
    
    logger.info(f"[重命名] 開始重命名變量: {old_name} -> {new_name}")
    
    if not code or not old_name or not new_name:
        return {"success": False, "error": "缺少必要參數"}
    
    try:
        # 使用註釋標記 DSL 重命名器
        new_code = marker_rename(code, old_name, new_name)
        
        logger.info(f"[重命名] 新代碼:\n{new_code}")
        
        return {
            "success": True,
            "new_code": new_code
        }
    except Exception as e:
        logger.error(f"變量重命名失敗: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/workflows/code", response_model=WorkflowRead)
def save_code_workflow(payload: Dict[str, Any], session: Session = Depends(get_session)):
    """保存代碼式工作流"""
    name = payload.get("name")
    code = payload.get("code")

    if not name or not code:
        raise HTTPException(status_code=400, detail="name和code不能爲空")

    # 創建工作流，將代碼存儲在 definition_code 字段
    wf = Workflow(
        name=name,
        description="代碼式工作流",
        definition_code=code,
        dsl_version=2
    )

    session.add(wf)
    session.commit()
    session.refresh(wf)
    
    # 同步觸發器緩存
    from app.services.workflow.trigger_extractor import sync_triggers_cache
    sync_triggers_cache(wf, session)
    session.commit()

    return wf


@router.get("/workflows/{workflow_id}/code")
def get_code_workflow(workflow_id: int, session: Session = Depends(get_session)):
    """獲取代碼式工作流"""
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # 代碼式工作流使用 definition_code 字段
    return {
        "id": wf.id,
        "name": wf.name,
        "code": wf.definition_code or "",
        "revision": compute_code_revision(wf.definition_code or ""),
        "keep_run_history": wf.keep_run_history or False
    }


@router.post("/workflows/{workflow_id}/patch", response_model=WorkflowPatchResponse)
def patch_workflow_code(
    workflow_id: int,
    payload: WorkflowPatchRequest,
    session: Session = Depends(get_session),
):
    wf = session.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    old_code = wf.definition_code or ""
    current_revision = compute_code_revision(old_code)
    if payload.base_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "revision_mismatch",
                "message": "代碼已更新，請刷新後重試",
                "current_revision": current_revision,
            },
        )

    try:
        execution = execute_patch_with_validation(old_code, payload.patch_ops, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    new_code = execution.new_code
    changed_nodes = execution.changed_nodes
    applied_ops = execution.applied_ops
    parse_result = execution.parse_result
    validation = execution.validation
    diff = execution.diff

    if payload.dry_run:
        return WorkflowPatchResponse(
            success=bool(parse_result.get("ok")) and bool(validation.get("is_valid")),
            workflow_id=workflow_id,
            base_revision=current_revision,
            new_revision=compute_code_revision(new_code),
            applied_ops=applied_ops,
            changed_nodes=changed_nodes,
            diff=diff,
            new_code=new_code,
            parse_result=parse_result,
            validation=validation,
            error=parse_result.get("error") if not parse_result.get("ok") else None,
        )

    if not parse_result.get("ok"):
        return WorkflowPatchResponse(
            success=False,
            workflow_id=workflow_id,
            base_revision=current_revision,
            applied_ops=applied_ops,
            changed_nodes=changed_nodes,
            diff=diff,
            new_code=new_code,
            parse_result=parse_result,
            validation=validation,
            error=str(parse_result.get("error") or "parse_failed"),
        )

    if not validation.get("is_valid"):
        return WorkflowPatchResponse(
            success=False,
            workflow_id=workflow_id,
            base_revision=current_revision,
            applied_ops=applied_ops,
            changed_nodes=changed_nodes,
            diff=diff,
            new_code=new_code,
            parse_result=parse_result,
            validation=validation,
            error="validate_failed",
        )

    wf.definition_code = new_code
    wf.updated_at = datetime.utcnow()
    session.add(wf)
    session.commit()
    session.refresh(wf)

    from app.services.workflow.trigger_extractor import sync_triggers_cache

    sync_triggers_cache(wf, session)
    session.commit()

    return WorkflowPatchResponse(
        success=True,
        workflow_id=workflow_id,
        base_revision=current_revision,
        new_revision=compute_code_revision(wf.definition_code or ""),
        applied_ops=applied_ops,
        changed_nodes=changed_nodes,
        diff=diff,
        new_code=wf.definition_code or "",
        parse_result=parse_result,
        validation=validation,
    )
