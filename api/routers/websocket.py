from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.monitor import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """建立会话级 WebSocket 连接并维持心跳。"""
    await manager.connect(websocket, thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "message": f"服务端已收到: {data}"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
    except Exception as error:
        print(f"[WebSocket] 连接异常: {error}")
        manager.disconnect(websocket, thread_id)
