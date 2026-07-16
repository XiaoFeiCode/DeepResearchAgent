"""把 DeepAgents 与 LangChain 链路导出到 OTLP 兼容后端。"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from openinference.instrumentation import (
    TraceConfig,
    using_metadata,
    using_session,
    using_user,
)
from openinference.instrumentation.langchain import LangChainInstrumentor
from openinference.semconv.resource import ResourceAttributes as OpenInferenceResourceAttributes
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

from core.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class _TracingState:
    provider: TracerProvider
    instrumentor: LangChainInstrumentor
    capture_content: bool


_state: _TracingState | None = None
_state_lock = threading.Lock()


def initialize_tracing() -> bool:
    """初始化进程级 OTLP 导出器和 LangChain 插桩器。"""
    global _state

    settings = get_settings()
    if not settings.phoenix_tracing_enabled:
        logger.info("Phoenix tracing is disabled")
        return False

    with _state_lock:
        if _state is not None:
            return True

        endpoint = settings.phoenix_collector_endpoint
        project_name = settings.phoenix_project_name
        capture_content = settings.phoenix_capture_content
        timeout = settings.phoenix_export_timeout_seconds

        resource = Resource.create(
            {
                "service.name": "omniresearch-api",
                "service.version": "0.1.0",
                "deployment.environment.name": settings.app_environment,
                OpenInferenceResourceAttributes.PROJECT_NAME: project_name,
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, timeout=timeout)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        instrumentor = LangChainInstrumentor()
        instrumentor.instrument(
            tracer_provider=provider,
            config=TraceConfig(
                hide_inputs=not capture_content,
                hide_outputs=not capture_content,
                hide_input_images=not capture_content,
            ),
        )
        _state = _TracingState(
            provider=provider,
            instrumentor=instrumentor,
            capture_content=capture_content,
        )
        logger.info(
            "Phoenix tracing initialized: endpoint=%s project=%s capture_content=%s",
            endpoint,
            project_name,
            capture_content,
        )
        return True


def shutdown_tracing() -> None:
    """FastAPI 进程退出前刷新尚未导出的 Span。"""
    global _state

    with _state_lock:
        state = _state
        _state = None

    if state is None:
        return

    try:
        state.instrumentor.uninstrument()
    except Exception:
        logger.exception("Failed to remove LangChain tracing instrumentation")

    try:
        state.provider.force_flush(timeout_millis=5000)
        state.provider.shutdown()
    except Exception:
        logger.exception("Failed to flush Phoenix traces")


@contextmanager
def agent_trace(
    *,
    task_query: str,
    thread_id: str,
    user_id: str,
) -> Iterator[Span | None]:
    """创建包含模型、工具和图调用的 Agent 根 Span。"""
    state = _state
    if state is None:
        yield None
        return

    attributes: dict[str, Any] = {
        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
        "deepagent.thread_id": thread_id,
        "deepagent.user_id": user_id,
    }
    if state.capture_content:
        attributes[SpanAttributes.INPUT_VALUE] = task_query
        attributes[SpanAttributes.INPUT_MIME_TYPE] = "text/plain"

    tracer = state.provider.get_tracer("deep-agent.runtime")
    metadata = {
        "thread_id": thread_id,
        "user_id": user_id,
        "runtime": "deepagents",
    }
    with using_session(thread_id), using_user(user_id), using_metadata(metadata):
        with tracer.start_as_current_span(
            "deep_agent.run",
            attributes=attributes,
        ) as span:
            try:
                yield span
            except BaseException as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)[:500]))
                raise


def record_agent_result(
    span: Span | None,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """把最终结果和状态附加到 Agent 根 Span。"""
    if span is None:
        return

    state = _state
    if state is not None and state.capture_content:
        span.set_attribute(SpanAttributes.OUTPUT_VALUE, content)
        span.set_attribute(SpanAttributes.OUTPUT_MIME_TYPE, "text/plain")

    result_metadata = metadata or {}
    span.set_attribute("deepagent.result.metadata_count", len(result_metadata))
    if result_metadata:
        span.set_attribute(
            "deepagent.result.metadata",
            json.dumps(result_metadata, ensure_ascii=False, default=str)[:10000],
        )

    if content.startswith("Error:"):
        span.set_status(Status(StatusCode.ERROR, content[:500]))
    else:
        span.set_status(Status(StatusCode.OK))


def get_span_identifiers(span: Span | None) -> tuple[str | None, str | None]:
    """返回 Phoenix 可识别的 Trace ID 和 Span ID。"""
    if span is None:
        return None, None
    context = span.get_span_context()
    if not context.is_valid:
        return None, None
    return f"{context.trace_id:032x}", f"{context.span_id:016x}"
