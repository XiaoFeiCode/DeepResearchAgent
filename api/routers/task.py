from fastapi import APIRouter, Request

from api.schemas import TaskRequest
from api.services import TaskService

router = APIRouter(prefix="/api", tags=["task"])


@router.post("/task")
async def run_task(payload: TaskRequest, request: Request):
    """登记后台 Agent 任务并立即返回会话 ID。"""
    task_service: TaskService = request.app.state.task_service
    thread_id = task_service.start(payload.query, payload.thread_id)
    return {"status": "started", "thread_id": thread_id}
