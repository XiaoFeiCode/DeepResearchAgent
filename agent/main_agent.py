"""主智能体任务编排入口。"""

from __future__ import annotations

import asyncio
import logging
import uuid

from agent.factory import get_main_agent
from agent.result import AgentRunResult
from agent.runtime import (
    build_workspace_instruction,
    prepare_session_environment,
    process_stream_chunk,
)
from agent.sandbox import REMOTE_WORKSPACE, daytona_sandbox_manager
from agent_memory import long_term_memory
from api.context import (
    get_result_metadata,
    reset_request_context,
    set_result_metadata_context,
    set_session_context,
    set_thread_context,
    set_user_context,
)
from api.monitor import monitor
from observability import agent_trace, get_span_identifiers, record_agent_result

logger = logging.getLogger(__name__)


async def run_deep_agent(
    task_query: str,
    thread_id: str | None = None,
    user_id: str = "anonymous",
) -> AgentRunResult:
    """在可观测根链路中执行一次主智能体任务。"""
    actual_thread_id = thread_id or str(uuid.uuid4())
    with agent_trace(
        task_query=task_query,
        thread_id=actual_thread_id,
        user_id=user_id,
    ) as span:
        result = await _execute_deep_agent(task_query, actual_thread_id, user_id)
        trace_id, span_id = get_span_identifiers(span)
        if trace_id and span_id:
            result.metadata["trace_id"] = trace_id
            result.metadata["span_id"] = span_id
        record_agent_result(span, result.content, result.metadata)
        return result


async def _recall_memory(task_query: str, user_id: str) -> str:
    """召回与当前问题相关的长期记忆，并转换为提示词片段。"""
    try:
        memories = await asyncio.to_thread(
            long_term_memory.search,
            user_id=user_id,
            query=task_query,
            limit=5,
        )
    except Exception as error:
        logger.warning("长期记忆召回不可用：%s", error)
        return ""

    if not memories:
        return ""

    memory_lines = [
        f"- [{item['memory_type']}] {item['content']}"
        for item in memories
    ]
    return (
        "\n\n【相关长期记忆】\n"
        + "\n".join(memory_lines)
        + "\n这些记忆仅作为历史上下文；若与当前要求冲突，以当前要求为准。"
    )

async def _execute_deep_agent(
    task_query: str,
    thread_id: str,
    user_id: str,
) -> AgentRunResult:
    """绑定会话上下文、沙箱和记忆，驱动 LangGraph 流式执行。"""
    logger.info("开始执行任务：thread_id=%s user_id=%s", thread_id, user_id)
    environment = prepare_session_environment(thread_id)

    thread_token = set_thread_context(thread_id)
    session_token = set_session_context(environment.directory_text)
    user_token = set_user_context(user_id)
    result_metadata_token = set_result_metadata_context()
    monitor.report_session_dir(environment.directory_text)

    config = {"configurable": {"thread_id": thread_id}}
    workspace_instruction = build_workspace_instruction(environment)

    try:
        memory_instruction = await _recall_memory(task_query, user_id)
        await asyncio.to_thread(
            daytona_sandbox_manager.upload_workspace,
            thread_id,
            environment.directory,
        )
        agent = await get_main_agent()
        final_result: str | None = None
        async for chunk in agent.astream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            task_query
                            + workspace_instruction
                            + memory_instruction
                            + f"\nDaytona 沙箱工作目录是 {REMOTE_WORKSPACE}。"
                            + "代码、命令、上传文件和临时文件必须在该目录中处理；"
                            + f"使用绝对路径，例如 {REMOTE_WORKSPACE}/report.md。"
                        ),
                    }
                ]
            },
            config=config,
        ):
            chunk_result = process_stream_chunk(chunk)
            if chunk_result:
                final_result = chunk_result

        return AgentRunResult(
            content=final_result or "Done",
            metadata=get_result_metadata(),
        )
    except Exception as error:
        logger.exception("主智能体任务执行失败")
        monitor.report_error(f"Execution failed: {error}")
        return AgentRunResult(content=f"Error: {error}")
    finally:
        try:
            await asyncio.to_thread(
                daytona_sandbox_manager.download_workspace,
                thread_id,
                environment.directory,
            )
        except Exception as error:
            logger.warning("同步 Daytona 工作目录失败：%s", error)
        finally:
            try:
                await asyncio.to_thread(daytona_sandbox_manager.release, thread_id)
            except Exception as error:
                logger.warning("释放 Daytona 沙箱失败：%s", error)

        reset_request_context(
            session_token,
            thread_token,
            user_token,
            result_metadata_token,
        )
