import asyncio
import unittest

from api.services.conversation_service import ConversationAccessError
from api.services.task_service import TaskService
from agent.result import AgentRunResult


class FakeConversationService:
    available = True

    def __init__(self):
        self.created = []
        self.messages = []

    def create_conversation(self, thread_id, user_id, title=None):
        self.created.append((thread_id, user_id, title))
        return {"id": thread_id}

    def add_message(self, thread_id, user_id, role, content, metadata=None):
        self.messages.append((thread_id, user_id, role, content, metadata))
        return {"id": len(self.messages)}


class TaskServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_persists_all_task_messages_for_the_current_user(self):
        conversation_service = FakeConversationService()

        async def runner(query, thread_id, user_id):
            return f"answer for {user_id}"

        service = TaskService(
            runner=runner,
            conversation_service=conversation_service,
        )
        thread_id = await service.start("question", "thread-1", user_id="alice")
        while service.active_count:
            await asyncio.sleep(0.01)

        self.assertEqual(thread_id, "thread-1")
        self.assertEqual(
            conversation_service.created,
            [("thread-1", "alice", None)],
        )
        self.assertEqual(
            conversation_service.messages,
            [
                ("thread-1", "alice", "user", "question", None),
                ("thread-1", "alice", "assistant", "answer for alice", None),
            ],
        )

    async def test_persists_structured_image_results(self):
        conversation_service = FakeConversationService()

        async def runner(query, thread_id, user_id):
            return AgentRunResult(
                content="找到一张相似图片",
                metadata={"images": [{"id": "image-1", "score": 0.91}]},
            )

        service = TaskService(
            runner=runner,
            conversation_service=conversation_service,
        )
        await service.start("查找相似图片", "thread-images", user_id="alice")
        while service.active_count:
            await asyncio.sleep(0.01)

        self.assertEqual(
            conversation_service.messages[-1],
            (
                "thread-images",
                "alice",
                "assistant",
                "找到一张相似图片",
                {"images": [{"id": "image-1", "score": 0.91}]},
            ),
        )

    async def test_rejects_a_thread_owned_by_another_user_before_running(self):
        class DeniedConversationService(FakeConversationService):
            def create_conversation(self, thread_id, user_id, title=None):
                raise ConversationAccessError("Conversation not found")

        runner_called = False

        async def runner(query, thread_id, user_id):
            nonlocal runner_called
            runner_called = True

        service = TaskService(
            runner=runner,
            conversation_service=DeniedConversationService(),
        )
        with self.assertRaises(ConversationAccessError):
            await service.start("question", "owned-thread", user_id="bob")
        self.assertFalse(runner_called)
        self.assertEqual(service.active_count, 0)


if __name__ == "__main__":
    unittest.main()
