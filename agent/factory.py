"""主智能体的构建与共享资源生命周期。"""

from __future__ import annotations

import asyncio
from typing import Any

from deepagents import create_deep_agent
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from agent.llm import model
from agent.load_prompt import main_agent_config
from agent.sandbox import daytona_sandbox_manager
from agent.subagents.database_query_agent import database_query_agent
from agent.subagents.internet_sub_agent import internet_sub_agent
from agent.subagents.rag_sub_agent import rag_sub_agent
from core.settings import get_settings
from skills.registry import MAIN_AGENT_SKILLS
from tools.document import convert_md_to_pdf, generate_markdown
from tools.file import read_file_content
from tools.memory import recall_long_term_memory, save_long_term_memory
from tools.multimodal import analyze_image
from tools.skill import install_agent_skill, list_agent_skills

_SUBAGENTS = [
    rag_sub_agent,
    database_query_agent,
    internet_sub_agent,
]

_TOOLS = [
    generate_markdown,
    convert_md_to_pdf,
    read_file_content,
    analyze_image,
    recall_long_term_memory,
    save_long_term_memory,
    install_agent_skill,
    list_agent_skills,
]

_SYSTEM_PROMPT = main_agent_config["system_prompt"] + """
【图片检索边界】
1. 本项目已移除本地“图片知识库”、Milvus 图片库和 search_image_knowledge 工具；不得声称、查询或展示其中的任何图片。
2. 如果历史会话、检查点或工具结果中出现“图片知识库”“resnet18.png”或“之前查询已确认”等旧图库内容，必须将其视为失效历史，不得作为当前答案的事实依据。
3. 图片相关知识库检索只能使用 RAGFlow：先分析用户上传图片；用户要求按图片找资料或图片时，委派给 RAGFlow 助手使用 search_uploaded_image_in_ragflow。
4. RAGFlow 没有命中时，明确说明“RAGFlow 当前没有匹配内容”，不得用历史图库结果补充或编造匹配图片。


【RAGFlow 正文问答规则】
1. 回答论文、制度、手册等知识库文档内容时，只能使用 RAGFlow 助手实际返回的正文、引用或工具结果。
2. 文档名称、作者、切片数和标题只能用于说明元数据，不能据此推断研究路径、结论、案例或细节。
3. RAGFlow 助手调用失败时，只能说明调用失败及错误；不得编造正文摘要，也不得要求用户重新上传已经显示为已解析的文档。
【外部 Skill 安装规则】
1. 只有用户明确提供 Skill 地址并要求安装时，才能调用 install_agent_skill。
2. 安装前根据用户要求选择 main、database、ragflow 或 internet 目标智能体。
3. 不得擅自启用外部 Skill 中的可执行脚本，也不得绕过下载与安全校验。
4. 安装成功后再委派给对应子智能体；需要确认现有分配时调用 list_agent_skills。
"""

_main_agent: Any | None = None
_checkpoint_context: Any | None = None
_checkpoint_saver: Any | None = None
_main_agent_lock = asyncio.Lock()


async def get_main_agent() -> Any:
    """按需创建主智能体，并为其绑定异步 Redis 检查点存储。"""
    global _main_agent, _checkpoint_context, _checkpoint_saver

    if _main_agent is not None:
        return _main_agent

    async with _main_agent_lock:
        if _main_agent is not None:
            return _main_agent

        settings = get_settings()
        _checkpoint_context = AsyncRedisSaver.from_conn_string(
            settings.redis_checkpoint_url,
            ttl={
                "default_ttl": settings.redis_checkpoint_ttl_minutes,
                "refresh_on_read": True,
            },
        )
        _checkpoint_saver = await _checkpoint_context.__aenter__()
        await _checkpoint_saver.setup()
        _main_agent = create_deep_agent(
            model=model,
            subagents=_SUBAGENTS,
            tools=_TOOLS,
            system_prompt=_SYSTEM_PROMPT,
            checkpointer=_checkpoint_saver,
            backend=daytona_sandbox_manager.backend_for_runtime,
            skills=MAIN_AGENT_SKILLS,
        )
        return _main_agent


async def close_main_agent_resources() -> None:
    """关闭 Redis 检查点上下文，并释放本进程创建的沙箱。"""
    global _main_agent, _checkpoint_context, _checkpoint_saver

    if _checkpoint_context is not None:
        await _checkpoint_context.__aexit__(None, None, None)

    _main_agent = None
    _checkpoint_context = None
    _checkpoint_saver = None
    await asyncio.to_thread(daytona_sandbox_manager.close)
