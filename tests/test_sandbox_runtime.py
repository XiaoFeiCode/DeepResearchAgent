import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.sandbox import DaytonaSandboxManager


class DaytonaSandboxRuntimeTests(unittest.TestCase):
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
