import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.sandbox import DaytonaSandboxManager


class DaytonaSandboxRuntimeTests(unittest.TestCase):
    def test_new_sandbox_is_ephemeral_and_labeled(self):
        manager = DaytonaSandboxManager()
        client = Mock()
        sandbox = Mock()
        client.create.return_value = sandbox
        backend = Mock()
        backend.execute.return_value = SimpleNamespace(exit_code=0, output="")

        with (
            patch.object(manager, "_get_client", return_value=client),
            patch("agent.sandbox.DaytonaSandbox", return_value=backend),
            patch.object(manager, "_upload_project_skills"),
        ):
            self.assertIs(manager.get_backend("thread-1234567890"), backend)

        params = client.create.call_args.args[0]
        self.assertTrue(params.ephemeral)
        self.assertEqual(params.labels["project"], "deep-agent-project")
        self.assertEqual(params.labels["thread_id"], "thread-1234567890")

    def test_release_removes_and_deletes_thread_sandbox(self):
        manager = DaytonaSandboxManager()
        client = Mock()
        sandbox = Mock()
        manager._client = client
        manager._sandboxes["thread-1"] = sandbox
        manager._backends["thread-1"] = Mock()

        manager.release("thread-1")

        client.delete.assert_called_once_with(sandbox)
        self.assertNotIn("thread-1", manager._sandboxes)
        self.assertNotIn("thread-1", manager._backends)

    def test_release_unknown_thread_is_a_noop(self):
        manager = DaytonaSandboxManager()
        manager._client = Mock()

        manager.release("missing-thread")

        manager._client.delete.assert_not_called()

    def test_backend_uses_runtime_config_when_available(self):
        manager = DaytonaSandboxManager()
        runtime = SimpleNamespace(config={"configurable": {"thread_id": "thread-old"}})

        with patch.object(manager, "get_backend", return_value="backend") as get_backend:
            self.assertEqual(manager.backend_for_runtime(runtime), "backend")

        get_backend.assert_called_once_with("thread-old")

    def test_backend_falls_back_to_langgraph_config(self):
        manager = DaytonaSandboxManager()
        runtime = SimpleNamespace()

        with (
            patch(
                "agent.sandbox.get_config",
                return_value={"configurable": {"thread_id": "thread-new"}},
            ),
            patch.object(manager, "get_backend", return_value="backend") as get_backend,
        ):
            self.assertEqual(manager.backend_for_runtime(runtime), "backend")

        get_backend.assert_called_once_with("thread-new")

    def test_backend_falls_back_to_request_context(self):
        manager = DaytonaSandboxManager()
        runtime = SimpleNamespace(config={"configurable": {}})

        with (
            patch("agent.sandbox.get_thread_context", return_value="thread-context"),
            patch.object(manager, "get_backend", return_value="backend") as get_backend,
        ):
            self.assertEqual(manager.backend_for_runtime(runtime), "backend")

        get_backend.assert_called_once_with("thread-context")


if __name__ == "__main__":
    unittest.main()
