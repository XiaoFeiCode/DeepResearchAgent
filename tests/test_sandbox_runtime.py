import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from deepagents.backends import FilesystemBackend

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
        self.assertEqual(params.labels["project"], "omniresearch")
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

    def test_daytona_creation_retries_after_remote_disconnect(self):
        manager = DaytonaSandboxManager()
        client = Mock()
        sandbox = Mock()
        client.create.side_effect = [ConnectionError("remote disconnected"), sandbox]
        backend = Mock()
        backend.execute.return_value = SimpleNamespace(exit_code=0, output="")

        with (
            patch.object(manager, "_get_client", return_value=client),
            patch("agent.sandbox.DaytonaSandbox", return_value=backend),
            patch.object(manager, "_upload_project_skills"),
            patch("agent.sandbox.time.sleep") as sleep,
            patch.dict(
                "os.environ",
                {"DAYTONA_CREATE_RETRIES": "2", "DAYTONA_RETRY_DELAY_SECONDS": "0"},
            ),
        ):
            self.assertIs(manager.get_backend("thread-retry"), backend)

        self.assertEqual(client.create.call_count, 2)
        sleep.assert_called_once_with(0.0)

    def test_daytona_outage_uses_file_only_backend_and_syncs_workspace(self):
        manager = DaytonaSandboxManager()

        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            session_dir = temp_root / "session"
            session_dir.mkdir()
            (session_dir / "input.txt").write_text("input", encoding="utf-8")

            with (
                patch.object(
                    manager,
                    "_create_daytona_backend",
                    side_effect=ConnectionError("remote disconnected"),
                ),
                patch.object(manager, "_upload_project_skills"),
                patch("agent.sandbox.LOCAL_FALLBACK_ROOT", temp_root / "fallback"),
            ):
                backend = manager.upload_workspace("thread-fallback", session_dir)
                self.assertIsInstance(backend, FilesystemBackend)
                self.assertFalse(hasattr(backend, "execute"))

                remote_input = (
                    manager._local_roots["thread-fallback"]
                    / "home"
                    / "daytona"
                    / "workspace"
                    / "input.txt"
                )
                self.assertEqual(remote_input.read_text(encoding="utf-8"), "input")

                backend.upload_files(
                    [("/home/daytona/workspace/result.txt", b"result")]
                )
                manager.download_workspace("thread-fallback", session_dir)
                self.assertEqual(
                    (session_dir / "result.txt").read_text(encoding="utf-8"),
                    "result",
                )

                local_root = manager._local_roots["thread-fallback"]
                manager.release("thread-fallback")
                self.assertFalse(local_root.exists())

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
