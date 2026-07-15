import asyncio
from typing import Annotated

from langchain_core.tools import tool

from api.context import add_result_images
from api.monitor import monitor


@tool
async def search_ragflow_document_images(
    query: Annotated[str, "用于检索图片的文字描述，可包含主题、图表标题、界面元素或 OCR 文字"],
    dataset_name_or_id: Annotated[str, "目标 RAGFlow 知识库名称或 ID"],
    document_name_or_id: Annotated[str, "可选，限定到某个文档名称或 ID"] = "",
    limit: Annotated[int, "返回图片数量，建议 3 到 8"] = 8,
) -> dict:
    """检索 RAGFlow 文档解析出的真实图片，并把可展示结果推送到前端。"""
    monitor.report_tool(
        tool_name="检索 RAGFlow 文档图片工具",
        args={
            "query": query,
            "dataset_name_or_id": dataset_name_or_id,
            "document_name_or_id": document_name_or_id,
            "limit": limit,
        },
    )
    try:
        # 延迟导入，避免 tools -> api.services -> agent -> tools 的启动期循环依赖。
        from api.services.ragflow_service import RagflowService

        result = await asyncio.to_thread(
            RagflowService().search_images,
            query,
            dataset_name_or_id,
            document_name_or_id,
            limit,
        )
    except Exception as error:
        return {"error": f"检索 RAGFlow 文档图片失败: {error}"}

    matches = [
        {
            **match,
            "display_token": f"{{{{image:{match['id']}}}}}",
        }
        for match in result["matches"]
    ]
    result["matches"] = matches
    result["rendering_instruction"] = (
        "在最终回答中讨论某张图片时，把该图片的 display_token 单独放在对应段落后。"
    )
    add_result_images(matches)
    monitor.report_image_results(matches)
    return result
