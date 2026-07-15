import asyncio
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.responses import FileResponse

from api.security import AuthenticatedUser, check_rbac
from api.services import ImageKnowledgeService

router = APIRouter(prefix="/api/image-knowledge", tags=["image-knowledge"])


def _service(request: Request) -> ImageKnowledgeService:
    return request.app.state.image_knowledge_service


@router.get("/images")
async def list_images(
    request: Request,
    limit: int = 100,
    current_user: AuthenticatedUser = Security(
        check_rbac,
        scopes=["image_knowledge"],
    ),
):
    try:
        images = await asyncio.to_thread(
            _service(request).store.list_images,
            user_id=current_user.username,
            limit=limit,
        )
        return {"images": images}
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/images/upload")
async def upload_images(
    request: Request,
    files: list[UploadFile] = File(...),
    description: str = Form(""),
    current_user: AuthenticatedUser = Security(
        check_rbac,
        scopes=["image_knowledge"],
    ),
):
    try:
        images = await asyncio.to_thread(
            _service(request).upload_images,
            user_id=current_user.username,
            files=files,
            description=description,
        )
        return {"status": "indexed", "images": images}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/search")
async def search_images(
    request: Request,
    query: str = Form(""),
    file: UploadFile | None = File(None),
    limit: int = Form(6),
    current_user: AuthenticatedUser = Security(
        check_rbac,
        scopes=["image_knowledge"],
    ),
):
    try:
        images = await asyncio.to_thread(
            _service(request).search,
            user_id=current_user.username,
            query=query,
            file=file,
            limit=max(1, min(limit, 20)),
        )
        return {"images": images}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/images/{image_id}/content")
async def get_image_content(
    image_id: str,
    request: Request,
    current_user: AuthenticatedUser = Security(
        check_rbac,
        scopes=["image_knowledge"],
    ),
):
    try:
        record = await asyncio.to_thread(
            _service(request).store.get_image,
            user_id=current_user.username,
            image_id=image_id,
        )
        return FileResponse(
            Path(record["storage_path"]),
            media_type=record["content_type"],
            filename=record["filename"],
            content_disposition_type="inline",
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.delete("/images/{image_id}")
async def delete_image(
    image_id: str,
    request: Request,
    current_user: AuthenticatedUser = Security(
        check_rbac,
        scopes=["image_knowledge"],
    ),
):
    try:
        await asyncio.to_thread(
            _service(request).store.delete_image,
            user_id=current_user.username,
            image_id=image_id,
        )
        return {"status": "deleted", "image_id": image_id}
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
