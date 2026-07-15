import asyncio
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.context import (
    add_result_images,
    get_session_context,
    get_user_context,
)
from api.monitor import monitor
from image_knowledge import image_knowledge_store
from tools.multimodal.image import _resolve_image_path


@tool
async def search_image_knowledge(
    query_text: Annotated[
        str,
        "用于文搜图的文字描述；图搜图时可留空或填写需要强调的视觉特征",
    ] = "",
    image_path: Annotated[
        str,
        "当前会话中的查询图片路径；纯文字检索时留空",
    ] = "",
    limit: Annotated[int, "返回相似图片数量，建议 3 到 8"] = 6,
) -> dict:
    """在用户自己的多模态图片知识库中执行文搜图、图搜图或图文融合检索。"""
    user_id = get_user_context()
    if not user_id:
        return {"error": "当前任务没有绑定用户，无法访问图片知识库"}

    image_content = None
    image_filename = "query.png"
    if image_path.strip():
        try:
            resolved = _resolve_image_path(image_path, get_session_context())
        except Exception as error:
            return {"error": f"查询图片读取失败: {error}"}
        image_content = resolved.read_bytes()
        image_filename = Path(resolved).name

    if not query_text.strip() and image_content is None:
        return {"error": "query_text 和 image_path 至少提供一个"}

    monitor.report_tool(
        tool_name="多模态图片知识库检索工具",
        args={
            "query_text": query_text,
            "image_path": image_path,
            "limit": limit,
        },
    )
    try:
        matches = await asyncio.to_thread(
            image_knowledge_store.search,
            user_id=user_id,
            query_text=query_text,
            image_content=image_content,
            image_filename=image_filename,
            limit=max(1, min(limit, 20)),
        )
    except Exception as error:
        return {"error": f"图片知识库检索失败: {error}"}

    display_matches = [
        {
            **match,
            "display_token": f"{{{{image:{match['id']}}}}}",
        }
        for match in matches
    ]
    add_result_images(display_matches)
    monitor.report_image_results(display_matches)
    return {
        "query_text": query_text,
        "query_image": image_filename if image_content is not None else None,
        "match_count": len(display_matches),
        "matches": display_matches,
        "rendering_instruction": (
            "在最终回答中讨论某张图片时，把该图片的 display_token 单独放在对应段落后。"
        ),
    }
