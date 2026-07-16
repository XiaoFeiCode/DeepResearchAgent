import asyncio

from fastapi import APIRouter, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.responses import FileResponse

from api.security import AuthenticatedUser, check_rbac
from api.services import ConversationAccessError, ConversationService, FileService

router = APIRouter(prefix="/api", tags=["files"])


def _service(request: Request) -> FileService:
    return request.app.state.file_service


@router.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    thread_id: str = Form(...),
    _current_user=Security(check_rbac, scopes=["files"]),
):
    saved_files = await asyncio.to_thread(_service(request).save_uploads, files, thread_id)
    return {"status": "uploaded", "files": saved_files}


@router.get("/uploads/{thread_id}/{filename}")
async def get_uploaded_file(
    thread_id: str,
    filename: str,
    request: Request,
    current_user: AuthenticatedUser = Security(check_rbac, scopes=["files"]),
):
    """校验会话归属后返回已持久化的聊天附件。"""
    conversation_service: ConversationService = request.app.state.conversation_service
    if not conversation_service.available:
        raise HTTPException(status_code=503, detail="会话存储不可用")
    try:
        await asyncio.to_thread(
            conversation_service.list_messages,
            thread_id,
            current_user.username,
        )
        file_path = _service(request).resolve_upload(thread_id, filename)
        return FileResponse(file_path, filename=file_path.name)
    except ConversationAccessError as error:
        raise HTTPException(status_code=404, detail="附件不存在") from error
    except (FileNotFoundError, PermissionError, ValueError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/download")
async def download_file(path: str, request: Request, _current_user=Security(check_rbac, scopes=["files"])):
    try:
        file_path = _service(request).resolve_download(path)
        return FileResponse(file_path, filename=file_path.name)
    except (FileNotFoundError, PermissionError, ValueError) as error:
        return {"error": str(error)}


@router.get("/files")
async def list_files(path: str, request: Request, _current_user=Security(check_rbac, scopes=["files"])):
    try:
        files = await asyncio.to_thread(_service(request).list_files, path)
        return {"files": files}
    except (FileNotFoundError, PermissionError, ValueError) as error:
        return {"error": str(error)}
    except OSError as error:
        return {"error": f"读取文件列表失败: {error}"}
