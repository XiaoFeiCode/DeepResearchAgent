import asyncio
from typing import Annotated

from langchain_core.tools import tool

from api.context import add_result_images
from api.monitor import monitor
from tools.multimodal.image import analyze_image_file


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


@tool
async def search_uploaded_image_in_ragflow(
    image_path: Annotated[str, "当前会话中上传图片的文件名或路径"],
    user_query: Annotated[str, "用户希望基于图片检索的具体问题"],
    dataset_name_or_id: Annotated[str, "目标 RAGFlow 知识库名称或 ID"],
    document_name_or_id: Annotated[str, "可选，限定到某个文档名称或 ID"] = "",
    limit: Annotated[int, "返回图片数量，建议 3 到 8"] = 8,
) -> dict:
    """先理解上传图片，再将视觉描述与用户问题合并检索 RAGFlow 文档图片。"""
    monitor.report_tool(
        tool_name="基于上传图片检索 RAGFlow 文档图片工具",
        args={
            "image_path": image_path,
            "user_query": user_query,
            "dataset_name_or_id": dataset_name_or_id,
            "document_name_or_id": document_name_or_id,
            "limit": limit,
        },
    )
    try:
        image_understanding = await analyze_image_file(
            image_path,
            "请提取图片主体、场景、视觉元素、OCR 文字和适合检索的关键词。",
        )
        retrieval_query = (
            f"用户问题：{user_query.strip()}\n"
            f"上传图片理解：{image_understanding}"
        )
        from api.services.ragflow_service import RagflowService

        result = await asyncio.to_thread(
            RagflowService().search_images,
            retrieval_query,
            dataset_name_or_id,
            document_name_or_id,
            limit,
        )
    except Exception as error:
        return {"error": f"基于上传图片检索 RAGFlow 文档图片失败: {error}"}

    matches = [
        {**match, "display_token": f"{{{{image:{match['id']}}}}}"}
        for match in result["matches"]
    ]
    result.update(
        {
            "image_understanding": image_understanding,
            "retrieval_query": retrieval_query,
            "matches": matches,
            "rendering_instruction": "在最终回答中，将每张命中图片的 display_token 放在对应说明段落之后。",
        }
    )
    add_result_images(matches)
    monitor.report_image_results(matches)
    return result