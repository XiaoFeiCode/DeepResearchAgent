from typing import Annotated, Literal

from langchain_core.tools import tool

from agent_memory import long_term_memory
from api.context import get_thread_context, get_user_context
from api.monitor import monitor

MemoryType = Literal["preference", "rule", "strategy", "template", "conclusion"]


@tool
def recall_long_term_memory(
    query: Annotated[str, "要从历史经验中检索的自然语言问题"],
    memory_type: Annotated[MemoryType | None, "可选的长期记忆类型"] = None,
    limit: Annotated[int, "最多返回的记忆数量"] = 5,
) -> list[dict]:
    """检索当前用户跨会话保存的长期规则、偏好、策略、模板和结论。"""
    user_id = get_user_context()
    if not user_id:
        return []
    monitor.report_tool(
        tool_name="长期记忆检索工具",
        args={"query": query, "memory_type": memory_type, "limit": limit},
    )
    return long_term_memory.search(
        user_id=user_id,
        query=query,
        memory_type=memory_type,
        limit=limit,
    )


@tool
def save_long_term_memory(
    content: Annotated[str, "值得在后续会话复用的稳定事实或经验"],
    memory_type: Annotated[MemoryType, "长期记忆类型"],
) -> dict:
    """保存当前用户可跨会话复用的非敏感长期记忆。"""
    user_id = get_user_context()
    if not user_id:
        return {"error": "当前任务没有用户身份，无法保存长期记忆"}
    monitor.report_tool(
        tool_name="长期记忆保存工具",
        args={"memory_type": memory_type},
    )
    return long_term_memory.save(
        user_id=user_id,
        content=content,
        memory_type=memory_type,
        source_thread_id=get_thread_context() or "",
    )
