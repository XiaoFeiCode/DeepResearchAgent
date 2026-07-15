from fastapi import APIRouter, HTTPException, Request, Security

from api.schemas import TaskRequest
from api.security import AuthenticatedUser, check_rbac
from api.services import ConversationAccessError, TaskService

router = APIRouter(prefix="/api", tags=["task"])


@router.post("/task")
async def run_task(
    payload: TaskRequest,
    request: Request,
    current_user: AuthenticatedUser = Security(check_rbac, scopes=["task"]),
):
    """登记后台 Agent 任务并立即返回会话 ID。"""
    task_service: TaskService = request.app.state.task_service
    try:
        thread_id = await task_service.start(
            payload.query,
            payload.thread_id,
            user_id=current_user.username,
        )
    except ConversationAccessError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error
    return {"status": "started", "thread_id": thread_id}
