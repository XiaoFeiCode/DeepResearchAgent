import unittest

from opentelemetry.trace import StatusCode

from observability.tracing import agent_trace, record_agent_result


class _FakeSpan:
    def __init__(self):
        self.attributes = {}
        self.status = None

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, status):
        self.status = status


class ObservabilityTests(unittest.TestCase):
    def test_agent_trace_is_noop_when_disabled(self):
        with agent_trace(task_query="test", thread_id="thread-1", user_id="user-1") as span:
            self.assertIsNone(span)

    def test_error_result_marks_span_as_failed(self):
        span = _FakeSpan()

        record_agent_result(span, "Error: failed", {"files": []})

        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["deepagent.result.metadata_count"], 1)


if __name__ == "__main__":
    unittest.main()
