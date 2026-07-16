"""基于 Tavily 的互联网搜索工具。"""

import logging
from typing import Any, Literal

from langchain_core.tools import tool
from tavily import TavilyClient

from api.monitor import monitor
from core.settings import get_settings

logger = logging.getLogger(__name__)
tavily_client = TavilyClient(api_key=get_settings().tavily_api_key)


@tool
def internet_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False,
) -> dict[str, Any]:
    """搜索互联网并返回便于智能体引用的摘要和原始链接。"""
    logger.info(
        "开始互联网搜索：query=%s topic=%s max_results=%s",
        query,
        topic,
        max_results,
    )
    monitor.report_tool(
        tool_name="Internet Search",
        args={
            "query": query,
            "topic": topic,
            "max_results": max_results,
            "include_raw_content": include_raw_content,
        },
    )

    try:
        response: dict[str, Any] = tavily_client.search(
            query=query,
            topic=topic,
            max_results=max_results,
            include_answer=True,
            include_raw_content=include_raw_content,
        )
    except Exception as error:
        logger.warning("互联网搜索失败：%s", error)
        return {"error": str(error)}

    sources = []
    for item in response.get("results", []):
        source = {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "score": item.get("score"),
            "published_date": item.get("published_date"),
        }
        if include_raw_content:
            source["raw_content"] = item.get("raw_content")
        sources.append(source)

    return {
        "query": query,
        "answer": response.get("answer"),
        "sources": sources,
        "source_urls": [source["url"] for source in sources if source.get("url")],
    }
