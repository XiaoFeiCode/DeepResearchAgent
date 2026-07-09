"""LangGraph deployment graphs for native DeepAgents async subagents."""

from deepagents import AsyncSubAgent, create_deep_agent

from agent.llm import model
from agent.load_prompt import main_agent_config
from agent.subagents.database_query_agent import database_query_agent
from agent.subagents.internet_sub_agent import internet_sub_agent
from agent.subagents.rag_sub_agent import rag_sub_agent


def _build_worker(spec: dict):
    """Turn an existing inline subagent specification into a deployable graph."""
    return create_deep_agent(
        model=spec.get("model", model),
        tools=spec.get("tools", []),
        system_prompt=spec["system_prompt"],
        name=spec["name"],
    )


# These workers are registered independently in langgraph.json. Each async run
# receives its own thread and state instead of sharing the supervisor context.
internet_research_graph = _build_worker(internet_sub_agent)
ragflow_research_graph = _build_worker(rag_sub_agent)
database_research_graph = _build_worker(database_query_agent)


async_subagents = [
    AsyncSubAgent(
        name="internet-researcher",
        description=(
            "执行需要多轮公开网络搜索、来源核验和信息综合的长期研究任务。"
            "适合可以在后台独立完成的调研工作。"
        ),
        graph_id="internet-researcher",
    ),
    AsyncSubAgent(
        name="ragflow-researcher",
        description=(
            "执行 RAGFlow 知识库检索、文档比较和知识库答案整理任务。"
            "适合耗时较长的企业知识研究。"
        ),
        graph_id="ragflow-researcher",
    ),
    AsyncSubAgent(
        name="database-researcher",
        description=(
            "执行 MySQL 表结构检查、只读查询和多表数据分析任务。"
            "适合可独立运行的数据调查。"
        ),
        graph_id="database-researcher",
    ),
]


async_supervisor_graph = create_deep_agent(
    model=model,
    subagents=async_subagents,
    system_prompt=main_agent_config["system_prompt"]
    + """

【异步子智能体规则】
1. 对耗时较长且可独立执行的研究任务，使用 start_async_task 启动后台子智能体。
2. 启动后立即向用户返回完整 task_id，不得马上轮询任务状态。
3. 仅在用户询问进度时调用 check_async_task 或 list_async_tasks。
4. 用户补充要求时调用 update_async_task；用户要求停止时调用 cancel_async_task。
5. 异步任务成功后，读取结果并向用户给出完整、可追溯的综合回答。
""",
    name="async-supervisor",
)


__all__ = [
    "async_supervisor_graph",
    "database_research_graph",
    "internet_research_graph",
    "ragflow_research_graph",
]
