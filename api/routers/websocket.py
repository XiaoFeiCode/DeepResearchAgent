import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.monitor import manager
from api.security import require_websocket_token

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """建立会话级 WebSocket 连接并维持心跳。"""
    if not await require_websocket_token(websocket):
        return
    await manager.connect(websocket, thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "message": f"服务端已收到: {data}"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
    except Exception as error:
        logger.warning("WebSocket 连接异常：%s", error)
        manager.disconnect(websocket, thread_id)
