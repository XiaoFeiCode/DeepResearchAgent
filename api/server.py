# ruff: noqa: E402

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agent.factory import close_main_agent_resources
from api.monitor import manager
from api.rate_limit import rate_limit_middleware
from api.routers import (
    auth_router,
    conversations_router,
    files_router,
    ragflow_router,
    task_router,
    websocket_router,
)
from api.services import (
    AuthService,
    ConversationService,
    FileService,
    RagflowService,
    TaskService,
)
from observability import initialize_tracing, shutdown_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化共享服务，并在退出时有序回收后台任务和 Agent 资源。"""
    manager.set_loop(asyncio.get_running_loop())
    initialize_tracing()
    auth_service = AuthService()
    await asyncio.to_thread(auth_service.initialize)
    conversation_service = ConversationService()
    await asyncio.to_thread(conversation_service.initialize)
    app.state.auth_service = auth_service
    app.state.conversation_service = conversation_service
    app.state.task_service = TaskService(conversation_service=conversation_service)
    app.state.file_service = FileService(project_root)
    app.state.ragflow_service = RagflowService()

    try:
        yield
    finally:
        await app.state.task_service.shutdown()
        await close_main_agent_resources()
        await manager.shutdown()
        await asyncio.to_thread(shutdown_tracing)


def create_app() -> FastAPI:
    app = FastAPI(title="OmniResearch API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(rate_limit_middleware)
    app.include_router(auth_router)
    app.include_router(task_router)
    app.include_router(conversations_router)
    app.include_router(files_router)
    app.include_router(ragflow_router)
    app.include_router(websocket_router)
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
