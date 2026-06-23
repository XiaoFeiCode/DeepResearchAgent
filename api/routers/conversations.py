import asyncio

from fastapi import APIRouter, HTTPException, Request, Security

from api.schemas import ConversationCreateRequest
from api.security import check_rbac
from api.services import ConversationService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _service(request: Request) -> ConversationService:
    return request.app.state.conversation_service


def _unavailable_error(service: ConversationService) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=service.initialization_error or "MySQL conversation memory is unavailable",
    )


@router.post("")
async def create_conversation(
    payload: ConversationCreateRequest,
    request: Request,
    _current_user=Security(check_rbac, scopes=["conversations"]),
):
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)
    conversation = await asyncio.to_thread(
        service.create_conversation,
        payload.thread_id,
        payload.title,
    )
    return {"conversation": conversation}


@router.get("")
async def list_conversations(
    request: Request,
    limit: int = 50,
    _current_user=Security(check_rbac, scopes=["conversations"]),
):
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)
    conversations = await asyncio.to_thread(service.list_conversations, min(max(limit, 1), 100))
    return {"conversations": conversations}


@router.get("/{thread_id}/messages")
async def list_conversation_messages(
    thread_id: str,
    request: Request,
    _current_user=Security(check_rbac, scopes=["conversations"]),
):
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)
    messages = await asyncio.to_thread(service.list_messages, thread_id)
    return {"thread_id": thread_id, "messages": messages}
