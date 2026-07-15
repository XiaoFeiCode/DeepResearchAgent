import asyncio

from fastapi import APIRouter, HTTPException, Request, Security

from api.schemas import ConversationCreateRequest
from api.security import AuthenticatedUser, check_rbac
from api.services import ConversationAccessError, ConversationService

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
    current_user: AuthenticatedUser = Security(check_rbac, scopes=["conversations"]),
):
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)
    try:
        conversation = await asyncio.to_thread(
            service.create_conversation,
            payload.thread_id,
            current_user.username,
            payload.title,
        )
    except ConversationAccessError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error
    return {"conversation": conversation}


@router.get("")
async def list_conversations(
    request: Request,
    limit: int = 50,
    current_user: AuthenticatedUser = Security(check_rbac, scopes=["conversations"]),
):
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)
    conversations = await asyncio.to_thread(
        service.list_conversations,
        current_user.username,
        min(max(limit, 1), 100),
    )
    return {"conversations": conversations}


@router.get("/{thread_id}/messages")
async def list_conversation_messages(
    thread_id: str,
    request: Request,
    current_user: AuthenticatedUser = Security(check_rbac, scopes=["conversations"]),
):
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)
    try:
        messages = await asyncio.to_thread(
            service.list_messages,
            thread_id,
            current_user.username,
        )
    except ConversationAccessError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error
    return {"thread_id": thread_id, "messages": messages}
