"""调用真实 OmniResearch Agent 并生成可重复评分的运行记录。"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.capture import capture_execution
from evaluation.dataset import write_jsonl
from evaluation.models import EvaluationCase, EvaluationRun


DEFAULT_CONTEXT_TOOLS = {
    "task",
    "internet_search",
    "list_sql_tables",
    "get_table_data",
    "execute_sql_query",
    "create_ask_delete",
    "inspect_ragflow_knowledge_base",
    "list_ragflow_datasets",
    "list_ragflow_documents",
    "search_ragflow_document_images",
    "search_uploaded_image_in_ragflow",
    "read_file_content",
    "recall_long_term_memory",
}


def _context_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, default=str)


def extract_retrieved_contexts(
    case: EvaluationCase,
    tool_calls: list[dict[str, Any]],
) -> list[str]:
    allowed = set(case.context_tools) if case.context_tools else set(DEFAULT_CONTEXT_TOOLS)
    # 子智能体内部工具结果由 DeepAgents 的 task 工具汇总回父图，始终作为上下文载体。
    allowed.add("task")
    contexts: list[str] = []
    for call in tool_calls:
        if call.get("name") not in allowed or call.get("output") in (None, ""):
            continue
        text = _context_text(call["output"])
        if text and text not in contexts:
            contexts.append(text)
    return contexts


async def collect_case(case: EvaluationCase, *, user_id: str) -> EvaluationRun:
    """使用独立 thread_id 执行一条用例，防止历史会话影响评测结果。"""
    # 延迟导入，确保只校验数据集时不会初始化模型、Redis 或 Daytona。
    from agent.main_agent import run_deep_agent

    thread_id = f"eval-{case.id}-{uuid.uuid4().hex[:10]}"
    started_at = datetime.now().astimezone()
    started = time.perf_counter()
    with capture_execution() as capture:
        result = await run_deep_agent(case.query, thread_id=thread_id, user_id=user_id)

    duration_ms = (time.perf_counter() - started) * 1000
    captured = capture.to_dict()
    metadata = dict(result.metadata)
    tool_calls = captured["tool_calls"]
    return EvaluationRun(
        case=case,
        thread_id=thread_id,
        user_id=user_id,
        response=result.content,
        status="error" if result.content.startswith("Error:") else "success",
        started_at=started_at,
        duration_ms=duration_ms,
        trace_id=metadata.pop("trace_id", None),
        span_id=metadata.pop("span_id", None),
        metadata=metadata,
        events=captured["events"],
        tool_calls=tool_calls,
        reported_tools=captured["reported_tools"],
        subagents=captured["subagents"],
        retrieved_contexts=extract_retrieved_contexts(case, tool_calls),
    )


async def collect_cases(
    cases: list[EvaluationCase],
    *,
    user_id: str,
    output_path: Path,
) -> list[EvaluationRun]:
    """顺序执行用例；默认不并发，避免压垮模型、数据库和沙箱服务。"""
    from agent.factory import close_main_agent_resources
    from observability import initialize_tracing, shutdown_tracing

    initialize_tracing()
    runs: list[EvaluationRun] = []
    try:
        for index, case in enumerate(cases, 1):
            print(f"[{index}/{len(cases)}] 执行评测用例: {case.id}")
            run = await collect_case(case, user_id=user_id)
            runs.append(run)
            # 每条用例完成后立即落盘，异常中断时仍能保留已完成结果。
            write_jsonl(
                output_path,
                [item.model_dump(mode="json") for item in runs],
            )
    finally:
        await close_main_agent_resources()
        shutdown_tracing()
    return runs


__all__ = ["collect_case", "collect_cases", "extract_retrieved_contexts"]
