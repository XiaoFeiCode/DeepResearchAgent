import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from evaluation.capture import (
    capture_execution,
    record_monitor_payload,
    record_stream_messages,
)
from evaluation.code_metrics import score_code_metrics
from evaluation.collector import extract_retrieved_contexts
from evaluation.dataset import load_cases, write_jsonl
from evaluation.models import EvaluationCase, EvaluationRun, ExpectedToolCall
from evaluation.report import write_report


class EvaluationCaptureTests(unittest.TestCase):
    def test_captures_tool_call_and_output_without_leaking_context(self):
        ai_message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "internet_search",
                    "args": {"query": "Python TaskGroup"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )
        tool_message = ToolMessage(
            content="官方文档内容",
            tool_call_id="call-1",
            name="internet_search",
        )

        with capture_execution() as capture:
            record_stream_messages([ai_message])
            record_stream_messages([ai_message, tool_message])
            record_monitor_payload(
                {
                    "event": "tool_start",
                    "data": {
                        "tool_name": "Internet Search",
                        "tool_key": "internet_search",
                        "args": {"query": "Python TaskGroup"},
                    },
                }
            )

        self.assertEqual(len(capture.tool_calls), 1)
        self.assertEqual(capture.tool_calls[0].name, "internet_search")
        self.assertEqual(capture.tool_calls[0].output, "官方文档内容")
        self.assertEqual(capture.reported_tools()[0]["name"], "internet_search")

        # 退出采集上下文后再次记录不应修改已完成结果。
        record_stream_messages([ToolMessage(content="其他", tool_call_id="call-2")])
        self.assertEqual(len(capture.tool_calls), 1)


class EvaluationDatasetTests(unittest.TestCase):
    def test_loads_enabled_cases_and_rejects_duplicate_ids(self):
        first = EvaluationCase(id="case-1", query="问题一")
        disabled = EvaluationCase(id="case-2", query="问题二", enabled=False)
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "cases.jsonl"
            write_jsonl(
                path,
                [first.model_dump(mode="json"), disabled.model_dump(mode="json")],
            )
            self.assertEqual([item.id for item in load_cases(path)], ["case-1"])

            write_jsonl(
                path,
                [first.model_dump(mode="json"), first.model_dump(mode="json")],
            )
            with self.assertRaisesRegex(ValueError, "重复用例 ID"):
                load_cases(path)

    def test_subagent_task_output_is_always_kept_as_retrieval_context(self):
        case = EvaluationCase(
            id="rag-case",
            query="查询知识库",
            context_tools=["create_ask_delete"],
        )
        contexts = extract_retrieved_contexts(
            case,
            [
                {
                    "name": "task",
                    "output": "子智能体根据知识库返回的完整内容",
                }
            ],
        )
        self.assertEqual(contexts, ["子智能体根据知识库返回的完整内容"])


class EvaluationCodeMetricTests(unittest.TestCase):
    def test_scores_business_tools_subagent_and_answer_terms(self):
        case = EvaluationCase(
            id="database-case",
            query="查询库存",
            expected_tools=[
                ExpectedToolCall(name="list_sql_tables"),
                ExpectedToolCall(name="execute_sql_query"),
            ],
            expected_subagents=["数据库查询助手"],
            required_answer_terms=["有货", "有效期"],
        )
        run = EvaluationRun(
            case=case,
            thread_id="thread-1",
            user_id="evaluation",
            response="当前有货，并已列出有效期。",
            status="success",
            started_at="2026-07-16T10:00:00+08:00",
            duration_ms=100,
            tool_calls=[
                {"id": "1", "name": "task", "args": {}, "output": None},
                {"id": "2", "name": "list_sql_tables", "args": {}, "output": "表"},
                {"id": "3", "name": "execute_sql_query", "args": {}, "output": "数据"},
            ],
            reported_tools=[
                {"id": "r1", "name": "list_sql_tables", "args": {}},
                {"id": "r2", "name": "execute_sql_query", "args": {}},
            ],
            subagents=["数据库查询助手"],
        )

        scores = {item.metric: item.score for item in score_code_metrics(run)}
        self.assertEqual(scores["execution_success"], 1.0)
        self.assertEqual(scores["tool_call_f1_code"], 1.0)
        self.assertEqual(scores["subagent_routing_f1"], 1.0)
        self.assertEqual(scores["required_term_coverage"], 1.0)

    def test_writes_machine_readable_and_markdown_reports(self):
        case = EvaluationCase(id="report-case", query="测试报告")
        run = EvaluationRun(
            case=case,
            thread_id="thread-report",
            user_id="evaluation",
            response="完成",
            status="success",
            started_at="2026-07-16T10:00:00+08:00",
            duration_ms=50,
        )
        scores = score_code_metrics(run)

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            scores_path, summary_path, report_path = write_report(
                output_directory,
                [run],
                scores,
            )

            self.assertTrue(scores_path.is_file())
            self.assertTrue(summary_path.is_file())
            self.assertIn("execution_success", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
