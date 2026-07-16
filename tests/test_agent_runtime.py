import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agent.runtime.session import (
    build_workspace_instruction,
    prepare_session_environment,
)
from agent.runtime.stream import process_stream_chunk


class AgentSessionRuntimeTests(unittest.TestCase):
    def test_prepares_session_directory_and_uploaded_files(self):
        with tempfile.TemporaryDirectory() as temporary_root:
            project_root = Path(temporary_root)
            upload_directory = project_root / "updated" / "session_thread-1"
            upload_directory.mkdir(parents=True)
            (upload_directory / "资料.txt").write_text("内容", encoding="utf-8")

            environment = prepare_session_environment(
                "thread-1",
                project_root=project_root,
            )

            self.assertTrue((environment.directory / "资料.txt").exists())
            self.assertEqual(environment.relative_directory, "output/session_thread-1")
            self.assertIn("资料.txt", environment.uploaded_files_prompt)
            self.assertIn(
                "output/session_thread-1",
                build_workspace_instruction(environment),
            )


class AgentStreamRuntimeTests(unittest.TestCase):
    def test_reports_subagent_dispatch(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "task",
                    "args": {
                        "subagent_type": "网络搜索助手",
                        "description": "查询资料",
                    },
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )

        with patch("agent.runtime.stream.monitor.report_assistant") as report:
            result = process_stream_chunk({"agent": {"messages": [message]}})

        self.assertIsNone(result)
        report.assert_called_once_with("网络搜索助手", {"desc": "查询资料"})

    def test_returns_and_reports_final_answer(self):
        message = AIMessage(content="最终答案")

        with patch("agent.runtime.stream.monitor.report_task_result") as report:
            result = process_stream_chunk({"agent": {"messages": [message]}})

        self.assertEqual(result, "最终答案")
        report.assert_called_once_with("最终答案")
