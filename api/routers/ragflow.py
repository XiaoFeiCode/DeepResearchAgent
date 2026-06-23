from fastapi import APIRouter, File, Form, Request, Security, UploadFile
from fastapi.concurrency import run_in_threadpool

from api.schemas import RagflowDocumentRequest
from api.security import check_rbac
from api.services import RagflowService
from tools.ragflow.base import _format_ragflow_error

router = APIRouter(prefix="/api/ragflow", tags=["ragflow"])


def _service(request: Request) -> RagflowService:
    return request.app.state.ragflow_service


@router.get("/datasets")
async def list_ragflow_datasets(request: Request, _current_user=Security(check_rbac, scopes=["ragflow"])):
    try:
        datasets = await run_in_threadpool(_service(request).list_datasets)
        return {"datasets": datasets}
    except Exception as error:
        return {"error": f"获取 RAGFlow 知识库失败: {error}"}


@router.get("/documents")
async def list_ragflow_documents(
    dataset_name_or_id: str,
    request: Request,
    _current_user=Security(check_rbac, scopes=["ragflow"]),
):
    try:
        return await run_in_threadpool(
            _service(request).list_documents,
            dataset_name_or_id,
        )
    except Exception as error:
        return {"error": f"获取 RAGFlow 文档失败: {error}"}


@router.post("/documents/upload")
async def upload_ragflow_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    dataset_name_or_id: str = Form(...),
    parse_after_upload: bool = Form(True),
    _current_user=Security(check_rbac, scopes=["ragflow"]),
):
    try:
        return await run_in_threadpool(
            _service(request).upload_documents,
            dataset_name_or_id,
            files,
            parse_after_upload,
        )
    except Exception as error:
        return {"error": _format_ragflow_error("上传 RAGFlow 文档", error)}


@router.post("/documents/parse")
async def parse_ragflow_documents(
    payload: RagflowDocumentRequest,
    request: Request,
    _current_user=Security(check_rbac, scopes=["ragflow"]),
):
    try:
        return await run_in_threadpool(
            _service(request).parse_documents,
            payload.dataset_name_or_id,
            payload.document_names_or_ids,
        )
    except Exception as error:
        return {"error": f"解析 RAGFlow 文档失败: {error}"}


@router.post("/documents/delete")
async def delete_ragflow_documents(
    payload: RagflowDocumentRequest,
    request: Request,
    _current_user=Security(check_rbac, scopes=["ragflow"]),
):
    try:
        return await run_in_threadpool(
            _service(request).delete_documents,
            payload.dataset_name_or_id,
            payload.document_names_or_ids,
        )
    except Exception as error:
        return {"error": f"删除 RAGFlow 文档失败: {error}"}
