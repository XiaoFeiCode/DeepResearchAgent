from langchain_core.tools import tool

from api.monitor import monitor
from tools.ragflow.base import (
    _find_dataset,
    _format_dataset,
    _format_document,
    _get_id,
    _get_name,
    _list_all_documents,
    _resolve_file_paths,
    get_ragflow_client,
)


def _format_ragflow_error(action: str, error: Exception) -> str:
    message = str(error)
    if "lacks permission" in message:
        return (
            f"{action}失败: 当前 RAGFlow API Key 没有对应知识库操作权限。\n"
            f"原始错误: {message}\n"
            "处理建议: 请在 RAGFlow 中确认该 API Key 所属用户是否有创建/维护知识库权限，"
            "或者先在 RAGFlow 页面手动创建知识库后，再用本工具上传和解析文档。"
        )
    return f"{action}失败: {message}"


@tool
def inspect_ragflow_knowledge_base(dataset_name_or_id: str = "") -> str:
    """
    查看 RAGFlow 知识库状态。

    dataset_name_or_id 为空时列出全部知识库；不为空时查看指定知识库和其中的文档。
    """
    monitor.report_tool(
        tool_name="查看 RAGFlow 知识库状态工具",
        args={"dataset_name_or_id": dataset_name_or_id},
    )
    try:
        client = get_ragflow_client()

        if not dataset_name_or_id.strip():
            datasets = client.list_datasets(page=1, page_size=100)
            if not datasets:
                return "当前 RAGFlow 中没有知识库。"
            return "当前 RAGFlow 知识库列表:\n\n" + "\n\n".join(
                _format_dataset(dataset) for dataset in datasets
            )

        dataset = _find_dataset(client, dataset_name_or_id)
        if dataset is None:
            return f"未找到知识库: {dataset_name_or_id}"

        documents = _list_all_documents(dataset)
        lines = ["知识库信息:", _format_dataset(dataset)]
        if documents:
            lines.append("文档列表:")
            lines.extend(_format_document(document) for document in documents)
        else:
            lines.append("该知识库中还没有文档。")
        return "\n\n".join(lines)
    except Exception as e:
        return _format_ragflow_error("查看 RAGFlow 知识库", e)


@tool
def setup_ragflow_knowledge_base(
    dataset_name: str,
    description: str = "",
    file_paths: str = "",
    parse_after_upload: bool = True,
    embedding_model: str = "text-embedding-v2@Tongyi-Qianwen",
) -> str:
    """
    一站式创建或维护 RAGFlow 知识库。

    工作流:
    1. 按名称查找知识库。
    2. 如果知识库不存在，则创建知识库。
    3. 如果提供了 file_paths，则上传文件。
    4. 默认上传后触发解析。
    5. 返回知识库和文档状态，方便主智能体继续回答用户。

    file_paths 支持用逗号、分号或换行分隔多个文件路径。
    """
    monitor.report_tool(
        tool_name="配置 RAGFlow 知识库工具",
        args={
            "dataset_name": dataset_name,
            "description": description,
            "file_paths": file_paths,
            "parse_after_upload": parse_after_upload,
            "embedding_model": embedding_model,
        },
    )
    try:
        if not dataset_name.strip():
            return "知识库名称不能为空。"

        client = get_ragflow_client()
        dataset = _find_dataset(client, dataset_name)
        created = False

        if dataset is None:
            dataset = client.create_dataset(
                name=dataset_name.strip(),
                description=description or None,
                embedding_model=embedding_model or None,
            )
            created = True

        lines = [
            "RAGFlow 知识库工具执行完成。",
            "动作: " + ("新建知识库" if created else "使用已有知识库"),
            _format_dataset(dataset),
        ]

        if file_paths.strip():
            paths = _resolve_file_paths(file_paths)
            opened_files = []
            try:
                document_list = []
                for path in paths:
                    file_obj = path.open("rb")
                    opened_files.append(file_obj)
                    document_list.append({"display_name": path.name, "blob": file_obj})

                documents = dataset.upload_documents(document_list)
            finally:
                for file_obj in opened_files:
                    file_obj.close()

            lines.append("上传文档:")
            lines.extend(_format_document(document) for document in documents)

            document_ids = [_get_id(document) for document in documents if _get_id(document)]
            if parse_after_upload and document_ids:
                parse_status = dataset.parse_documents(document_ids)
                lines.append(f"解析状态: {parse_status}")

        documents = _list_all_documents(dataset)
        if documents:
            lines.append("当前知识库文档:")
            lines.extend(_format_document(document) for document in documents)
        else:
            lines.append(f"知识库“{_get_name(dataset)}”当前还没有文档。")

        return "\n\n".join(lines)
    except Exception as e:
        return _format_ragflow_error("执行 RAGFlow 知识库工具", e)


__all__ = ["inspect_ragflow_knowledge_base", "setup_ragflow_knowledge_base"]
