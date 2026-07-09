"""Agent tools for installing and listing user-scoped skills."""

from typing import Any, Literal

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from agent.sandbox import daytona_sandbox_manager
from api.context import get_user_context
from api.monitor import monitor
from skills.installer import SkillInstallError, install_skill, list_installed_skills


@tool
def install_agent_skill(
    skill_url: str,
    target_agent: Literal["main", "database", "ragflow", "internet"],
    runtime: ToolRuntime,
    replace: bool = False,
) -> dict[str, Any]:
    """从 GitHub 下载 Skill，并分配给当前用户的指定智能体。

    只有当用户明确要求安装某个 Skill 地址时才能调用。安装完成后，可以继续调用对应
    子智能体；它将在新任务开始时通过 DeepAgents SkillsMiddleware 发现该 Skill。
    """
    monitor.report_tool(
        tool_name="安装 Agent Skill",
        args={
            "skill_url": skill_url,
            "target_agent": target_agent,
            "replace": replace,
        },
    )
    user_id = get_user_context() or "anonymous"
    try:
        result = install_skill(
            skill_url=skill_url,
            target_agent=target_agent,
            user_id=user_id,
            replace=replace,
        )
        configurable = (runtime.config or {}).get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            raise SkillInstallError("当前调用缺少 thread_id，无法同步到会话沙箱")
        daytona_sandbox_manager.upload_user_skill(
            thread_id=str(thread_id),
            user_id=user_id,
            target_agent=target_agent,
            skill_name=result["name"],
            local_directory=result["directory"],
        )
        result.pop("directory", None)
        result["available"] = True
        result["message"] = (
            "Skill 已安装并分配；子智能体可在后续任务中使用，"
            "分配给 main 时从下一轮用户请求开始生效"
        )
        return result
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
        }


@tool
def list_agent_skills() -> list[dict[str, str]]:
    """列出当前登录用户安装并分配给各智能体的外部 Skill。"""
    monitor.report_tool(tool_name="查看已安装 Agent Skill", args={})
    return list_installed_skills(get_user_context() or "anonymous")
