import asyncio
import datetime
import logging
from concurrent.futures import Future
from typing import Any

from fastapi import WebSocket

from api.context import get_thread_context

logger = logging.getLogger(__name__)


class ToolMonitor:
    """
    Agent 执行事件上报器。

    它不直接保存 WebSocket 连接，只负责把“工具调用、子智能体调用、
    最终结果、工作目录”等事件包装成统一 payload，然后交给
    ConnectionManager 按 thread_id 推送给前端。
    """

    def __init__(self) -> None:
        self.websocket_manager: ConnectionManager | None = None

    def set_websocket_manager(self, manager: "ConnectionManager | None") -> None:
        """绑定 WebSocket 管理器；服务关闭时传 None 解除绑定。"""
        self.websocket_manager = manager

    def _emit(
        self,
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """包装事件并发送到当前 thread_id 对应的前端。"""
        payload = {
            "type": "monitor_event",
            "event": event_type,
            "message": message,
            "data": data or {},
            "timestamp": datetime.datetime.now().isoformat(),
        }

        thread_id = get_thread_context()
        if self.websocket_manager and thread_id:
            self.websocket_manager.publish(thread_id, payload)

        logger.info("执行事件：type=%s message=%s", event_type, message)

    def report_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> None:
        """报告工具开始执行。"""
        self._emit(
            "tool_start",
            f"开始执行工具: {tool_name}",
            {"tool_name": tool_name, "args": args or {}},
        )

    def report_assistant(
        self,
        assistant_name: str,
        args: dict[str, Any] | None = None,
    ) -> None:
        """报告正在调用子智能体。"""
        self._emit(
            "assistant_call",
            f"正在调用助手: {assistant_name}",
            {"assistant_name": assistant_name, "args": args or {}},
        )

    def report_task_result(self, result: str) -> None:
        """报告任务最终结果。"""
        self._emit("task_result", "任务执行完成", {"result": result})

    def report_error(self, message: str) -> None:
        """报告任务执行异常。"""
        self._emit("error", message)

    def report_image_results(self, images: list[dict[str, Any]]) -> None:
        """报告多模态图片检索结果，供前端显示缩略图。"""
        self._emit(
            "image_search_result",
            f"检索到 {len(images)} 张相似图片",
            {"images": images},
        )

    def report_session_dir(self, path: str) -> None:
        """报告当前任务工作目录。"""
        self._emit("session_created", f"工作目录已创建: {path}", {"path": path})


class ConnectionManager:
    """
    WebSocket 连接管理器。

    核心职责只有三个：
    1. 记录每个 thread_id 对应的 WebSocket。
    2. 接收 monitor 传来的事件 payload。
    3. 把 payload 推送给对应 thread_id 的前端连接。
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._send_tasks: set[asyncio.Task] = set()
        self._threadsafe_futures: set[Future] = set()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """在 FastAPI lifespan 中绑定服务事件循环。"""
        self.loop = loop
        monitor.set_websocket_manager(self)
        logger.info("WebSocket 管理器已绑定事件循环：%s", id(loop))

    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        """接收前端 WebSocket 连接，并按 thread_id 保存。"""
        await websocket.accept()
        self.active_connections[thread_id] = websocket
        logger.info("WebSocket 客户端已连接：thread_id=%s", thread_id)

    def disconnect(self, websocket: WebSocket, thread_id: str) -> None:
        """断开连接；只删除当前 websocket，避免覆盖新连接。"""
        current = self.active_connections.get(thread_id)
        if current is websocket:
            del self.active_connections[thread_id]
        logger.info("WebSocket 客户端已断开：thread_id=%s", thread_id)

    def publish(self, thread_id: str, message: dict[str, Any]) -> None:
        """
        向某个 thread_id 对应的前端发送事件。

        如果当前代码就在 FastAPI 事件循环里，直接 create_task；
        如果来自同步线程，则用 run_coroutine_threadsafe 投递回服务事件循环。
        """
        if self.loop is None or thread_id not in self.active_connections:
            return

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is self.loop:
            self.schedule_send(message, thread_id)
        else:
            self.schedule_threadsafe(message, thread_id)

    def schedule_send(self, message: dict[str, Any], thread_id: str) -> None:
        """在服务事件循环中创建并登记发送任务。"""
        task = asyncio.create_task(
            self.send_to_thread(message, thread_id),
            name=f"websocket-send-{thread_id}",
        )
        self._send_tasks.add(task)
        task.add_done_callback(self._finish_send_task)

    def schedule_threadsafe(self, message: dict[str, Any], thread_id: str) -> None:
        """从同步线程把发送协程投递到服务事件循环。"""
        if self.loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self.send_to_thread(message, thread_id),
            self.loop,
        )
        self._threadsafe_futures.add(future)
        future.add_done_callback(self._finish_threadsafe_future)

    async def send_to_thread(self, message: dict[str, Any], thread_id: str) -> None:
        """真正执行 WebSocket JSON 发送。"""
        websocket = self.active_connections.get(thread_id)
        if websocket is not None:
            await websocket.send_json(message)

    async def shutdown(self) -> None:
        """关闭连接、取消未完成发送任务，并解除 monitor 绑定。"""
        connections = list(self.active_connections.values())
        if connections:
            await asyncio.gather(
                *(websocket.close(code=1001) for websocket in connections),
                return_exceptions=True,
            )

        pending = [task for task in self._send_tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        for future in list(self._threadsafe_futures):
            future.cancel()

        self._send_tasks.clear()
        self._threadsafe_futures.clear()
        self.active_connections.clear()
        self.loop = None
        monitor.set_websocket_manager(None)

    def _finish_send_task(self, task: asyncio.Task) -> None:
        self._send_tasks.discard(task)
        if task.cancelled():
            return
        try:
            error = task.exception()
        except Exception as error:
            logger.warning("WebSocket 发送任务检查失败：%s", error)
            return
        if error is not None:
            logger.warning("WebSocket 发送失败：%s", error)

    def _finish_threadsafe_future(self, future: Future) -> None:
        self._threadsafe_futures.discard(future)
        if future.cancelled():
            return
        try:
            error = future.exception()
        except Exception as error:
            logger.warning("跨线程 WebSocket 任务检查失败：%s", error)
            return
        if error is not None:
            logger.warning("跨线程 WebSocket 发送失败：%s", error)


monitor = ToolMonitor()
manager = ConnectionManager()
