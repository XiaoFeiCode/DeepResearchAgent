import asyncio

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from api.services import FileService

router = APIRouter(prefix="/api", tags=["files"])


def _service(request: Request) -> FileService:
    return request.app.state.file_service


@router.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    thread_id: str = Form(...),
):
    saved_files = await asyncio.to_thread(_service(request).save_uploads, files, thread_id)
    return {"status": "uploaded", "files": saved_files}


@router.get("/download")
async def download_file(path: str, request: Request):
    try:
        file_path = _service(request).resolve_download(path)
        return FileResponse(file_path, filename=file_path.name)
    except (FileNotFoundError, PermissionError, ValueError) as error:
        return {"error": str(error)}


@router.get("/files")
async def list_files(path: str, request: Request):
    try:
        files = await asyncio.to_thread(_service(request).list_files, path)
        return {"files": files}
    except (FileNotFoundError, PermissionError, ValueError) as error:
        return {"error": str(error)}
    except OSError as error:
        return {"error": f"读取文件列表失败: {error}"}
