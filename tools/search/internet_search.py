# 类型注解：增强代码提示和静态检查能力
import os
from typing import Any, Literal

# LangChain 工具装饰器：将普通函数转为 Agent 可调用的工具
from langchain_core.tools import tool
from tavily import TavilyClient

from dotenv import load_dotenv, find_dotenv  # 加载 .env 文件中的环境变量

# 自定义模块：工具调用埋点监控（需确保 api 模块可导入）
# 只要调用了工具就应该向前端反馈
from api.monitor import monitor

# ======================== 初始化配置 ========================
# 加载项目根目录的 .env 文件，读取环境变量（如 TAVILY_API_KEY）
load_dotenv(find_dotenv())

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


@tool
def internet_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False) -> dict:

    '''
    Internet Search 工具说明：基于 Tavily API 的互联网搜索功能。
    参数说明：
    - query: 搜索关键词或自然语言查询
    - topic: 搜索主题分类（general: 综合，news: 新闻，finance:
金融）
    - max_results: 返回的最大结果数量
    - include_raw_content: 是否包含原始内容（如网页摘要、链接等）
    返回值：
    - dict: 包含搜索结果和原始链接，便于最终回答引用来源
    '''


    # 1. 做好日志记录
    print(f"[Tool] Internet Search called with query: {query}, topic: {topic}, max_results: {max_results}")
    # 2. 向前端反馈工具调用事件
    monitor.report_tool(tool_name="Internet Search", args={"query": query, "topic": topic, "max_results": max_results, "include_raw_content": include_raw_content})
    # 3. 实际工具逻辑（调用 Tavily API）
    try:
        response: dict[str, Any] = tavily_client.search(
            query=query,
            topic=topic,
            max_results=max_results,
            include_answer=True,
            include_raw_content=include_raw_content,
        )

        # Tavily 原始结果字段较多，这里整理成 Agent 更容易引用的结构。
        # 重点保留 title、url、content，避免最终回答丢失原始链接。
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

        results = {
            "query": query,
            "answer": response.get("answer"),
            "sources": sources,
            "source_urls": [source["url"] for source in sources if source.get("url")],
        }

        print(f"[Tool] Internet Search results: {results}")
        return results
    except Exception as e:
        print(f"[Tool] Internet Search failed: {e}")
        return {"error": str(e)}
