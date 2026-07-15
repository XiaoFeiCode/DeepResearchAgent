import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from agent.main_agent import run_deep_agent
from agent.result import AgentRunResult
from api.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


class TaskService:
    """创建并跟踪 Agent 后台任务，确保服务退出时能够完整回收。"""

    def __init__(
        self,
        runner: Callable[[str, str, str], Awaitable[object]] = run_deep_agent,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self._runner = runner
        self._conversation_service = conversation_service
        self._tasks: set[asyncio.Task] = set()

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    async def start(
        self,
        query: str,
        thread_id: str | None = None,
        user_id: str = "anonymous",
        user_metadata: dict | None = None,
    ) -> str:
        task_thread_id = thread_id or str(uuid.uuid4())
        service = self._conversation_service
        if service is not None and service.available:
            await asyncio.to_thread(
                service.create_conversation,
                task_thread_id,
                user_id,
            )
        task = asyncio.create_task(
            self._run_and_persist(
                query,
                task_thread_id,
                user_id,
                user_metadata,
            ),
            name=f"agent-task-{task_thread_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task_thread_id

    async def _run_and_persist(
        self,
        query: str,
        thread_id: str,
        user_id: str,
        user_metadata: dict | None = None,
    ):
        await self._save_message(
            thread_id,
            user_id,
            "user",
            query,
            metadata=user_metadata,
        )
        result = await self._runner(query, thread_id, user_id)
        content = result.content if isinstance(result, AgentRunResult) else result
        metadata = result.metadata if isinstance(result, AgentRunResult) else None
        if isinstance(content, str) and content and content != "Done":
            role = "system" if content.startswith("Error:") else "assistant"
            await self._save_message(
                thread_id,
                user_id,
                role,
                content,
                metadata=metadata,
            )
        return result

    async def _save_message(
        self,
        thread_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        service = self._conversation_service
        if service is None or not service.available:
            return
        try:
            await asyncio.to_thread(
                service.add_message,
                thread_id,
                user_id,
                role,
                content,
                metadata,
            )
        except Exception:
            logger.exception("Failed to persist %s message for thread %s", role, thread_id)

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return

        try:
            error = task.exception()
        except asyncio.CancelledError:
            return

        if error is not None:
            logger.error(
                "Agent background task failed",
                exc_info=(type(error), error, error.__traceback__),
            )

    async def shutdown(self) -> None:
        """取消并等待所有尚未完成的任务，避免事件循环关闭后留下协程。"""
        pending = [task for task in self._tasks if not task.done()]
        for task in pending:
            task.cancel()

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        self._tasks.clear()
