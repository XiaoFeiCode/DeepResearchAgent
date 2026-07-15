import asyncio

from fastapi import APIRouter, HTTPException, Request, Security

from api.schemas import TaskRequest
from api.security import AuthenticatedUser, check_rbac
from api.services import ConversationAccessError, FileService, TaskService

router = APIRouter(prefix="/api", tags=["task"])


@router.post("/task")
async def run_task(
    payload: TaskRequest,
    request: Request,
    current_user: AuthenticatedUser = Security(check_rbac, scopes=["task"]),
):
    """登记后台 Agent 任务并立即返回会话 ID。"""
    task_service: TaskService = request.app.state.task_service
    if payload.attachment_names and not payload.thread_id:
        raise HTTPException(status_code=400, detail="上传附件必须绑定会话 ID")
    file_service: FileService = request.app.state.file_service
    try:
        attachments = await asyncio.to_thread(
            file_service.describe_uploads,
            payload.thread_id or "",
            payload.attachment_names,
        ) if payload.attachment_names else []
        thread_id = await task_service.start(
            payload.query,
            payload.thread_id,
            user_id=current_user.username,
            user_metadata={"attachments": attachments} if attachments else None,
        )
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ConversationAccessError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error
    return {"status": "started", "thread_id": thread_id}
