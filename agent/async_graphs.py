"""供 LangGraph 部署的 DeepAgents 原生异步子智能体图。"""

import shutil

from deepagents import AsyncSubAgent, FilesystemPermission, create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend

from agent.llm import model
from agent.load_prompt import main_agent_config
from agent.subagents.database_query_agent import database_query_agent
from agent.subagents.internet_sub_agent import internet_sub_agent
from agent.subagents.rag_sub_agent import rag_sub_agent
from skills.registry import PROJECT_ROOT, SKILL_ASSIGNMENTS


def _prepare_worker_skill_source(target_agent: str):
    """为异步 Worker 构建隔离、只读的本地 Skill 源。"""
    source_root = PROJECT_ROOT / "runtime" / "async_skill_sources" / target_agent
    if source_root.exists():
        shutil.rmtree(source_root)
    source_root.mkdir(parents=True)

    project_skills = PROJECT_ROOT / "skills"
    for skill_name in SKILL_ASSIGNMENTS[target_agent]:
        shutil.copytree(
            project_skills / skill_name,
            source_root / skill_name,
        )

    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(
                root_dir=source_root,
                virtual_mode=True,
            )
        },
    )
    return backend


def _build_worker(spec: dict, target_agent: str):
    """把内联子智能体配置转换为支持 Skill 的可部署图。"""
    return create_deep_agent(
        model=spec.get("model", model),
        tools=spec.get("tools", []),
        system_prompt=spec["system_prompt"],
        backend=_prepare_worker_skill_source(target_agent),
        skills=["/skills/"],
        permissions=[
            FilesystemPermission(
                operations=["write"],
                paths=["/skills/**"],
                mode="deny",
            )
        ],
        name=spec["name"],
    )


# 这些 Worker 在 langgraph.json 中独立注册，每次异步运行都使用自己的线程和状态，
# 不与 Supervisor 共享上下文。
internet_research_graph = _build_worker(internet_sub_agent, "internet")
ragflow_research_graph = _build_worker(rag_sub_agent, "ragflow")
database_research_graph = _build_worker(database_query_agent, "database")


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
