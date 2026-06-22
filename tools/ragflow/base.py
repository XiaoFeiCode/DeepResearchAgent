from pathlib import Path
import sys
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from ragflow_sdk import RAGFlow

# 兼容直接运行:
#   uv run tools/ragflow/base.py
# 这种方式执行时，Python 只会把 tools/ragflow/ 加进 sys.path，
# 所以这里手动补项目根目录，保证能导入 ragflow.config 和 api.monitor。
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api.monitor import monitor
from ragflow.config import _load_ragflow_env


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    """兼容 SDK 返回 dict 或对象两种格式。"""
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _get_name(value: Any, default: str = "未知") -> str:
    return _get_value(value, "name", default) or default


def _get_id(value: Any, default: str = "") -> str:
    return _get_value(value, "id", default) or default


def _is_uuid(value: str) -> bool:
    """判断字符串是否是 UUID，避免把普通知识库名称传给 id 查询。"""
    try:
        UUID(value)
        return True
    except ValueError:
        return False


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


def _split_values(raw: str) -> list[str]:
    """把逗号、分号、换行分隔的参数统一拆成列表。"""
    if not raw:
        return []

    normalized = raw.replace("，", ",").replace("；", ";").replace("\n", ",").replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _resolve_file_paths(file_paths: str) -> list[Path]:
    """
    将用户传入的文件路径解析成实际 Path。

    支持:
    - 绝对路径
    - 相对当前命令目录的路径
    - 相对项目根目录的路径
    """
    paths = []
    for item in _split_values(file_paths):
        path = Path(item)
        candidates = [path]
        if not path.is_absolute():
            candidates.append(project_root / path)

        resolved = next((candidate for candidate in candidates if candidate.exists()), None)
        if resolved is None:
            raise FileNotFoundError(f"文件不存在: {item}")
        if not resolved.is_file():
            raise ValueError(f"不是有效文件: {resolved}")
        paths.append(resolved)

    if not paths:
        raise ValueError("请至少提供一个文件路径。")

    return paths


def get_ragflow_client() -> RAGFlow:
    """创建 RAGFlow SDK 客户端。"""
    api_key, base_url = _load_ragflow_env()
    if not api_key or not base_url:
        raise ValueError("RAGFLOW_API_KEY 或 RAGFLOW_API_URL 未配置，请检查 .env。")
    return RAGFlow(api_key=api_key, base_url=base_url)


def _find_dataset(client: RAGFlow, dataset_name_or_id: str):
    """按知识库 ID 或名称查找 DataSet。"""
    target = dataset_name_or_id.strip()
    if not target:
        raise ValueError("知识库名称或 ID 不能为空。")

    if _is_uuid(target):
        datasets = client.list_datasets(id=target, page=1, page_size=10)
        if datasets:
            return datasets[0]

    # RAGFlow 某些版本在 list_datasets(name=中文名称) 且未命中时会返回权限错误。
    # 所以名称查找改为列出当前用户可见知识库，再在本地按名称匹配。
    page = 1
    page_size = 100
    while True:
        datasets = client.list_datasets(page=page, page_size=page_size)
        for dataset in datasets:
            if _get_name(dataset) == target:
                return dataset

        if len(datasets) < page_size:
            break
        page += 1

    return None


def _format_dataset(dataset: Any) -> str:
    name = _get_name(dataset, "未知知识库")
    dataset_id = _get_id(dataset, "")
    description = _get_value(dataset, "description", "") or "无描述"
    doc_num = _get_value(dataset, "doc_num", None)
    chunk_num = _get_value(dataset, "chunk_num", None)

    extra = []
    if doc_num is not None:
        extra.append(f"文档数: {doc_num}")
    if chunk_num is not None:
        extra.append(f"切片数: {chunk_num}")
    extra_text = f"\n  {'; '.join(extra)}" if extra else ""

    return f"- 名称: {name}\n  ID: {dataset_id}\n  描述: {description}{extra_text}"


def _format_document(document: Any) -> str:
    name = _get_name(document, "未知文档")
    doc_id = _get_id(document, "")
    run = _get_value(document, "run", None)
    progress = _get_value(document, "progress", None)
    chunk_count = _get_value(document, "chunk_count", None)
    token_count = _get_value(document, "token_count", None)

    details = []
    if run is not None:
        details.append(f"解析状态: {run}")
    if progress is not None:
        details.append(f"进度: {progress}")
    if chunk_count is not None:
        details.append(f"切片数: {chunk_count}")
    if token_count is not None:
        details.append(f"Token数: {token_count}")
    detail_text = f"\n  {'; '.join(details)}" if details else ""

    return f"- 文档: {name}\n  ID: {doc_id}{detail_text}"


def _find_documents(dataset: Any, names_or_ids: str) -> tuple[list[Any], list[str]]:
    """按文档 ID 或名称查找文档。"""
    targets = _split_values(names_or_ids)
    if not targets:
        raise ValueError("请提供文档名称或 ID。")

    all_docs = dataset.list_documents(page=1, page_size=1000)
    matched = []
    missing = []

    for target in targets:
        found = None
        for doc in all_docs:
            if target in {_get_id(doc), _get_name(doc)}:
                found = doc
                break
        if found is None:
            missing.append(target)
        else:
            matched.append(found)

    return matched, missing


@tool
def list_ragflow_datasets() -> str:
    """列出 RAGFlow 中所有知识库。"""
    monitor.report_tool(tool_name="列出 RAGFlow 知识库工具")

    try:
        client = get_ragflow_client()
        datasets = client.list_datasets(page=1, page_size=100)
        if not datasets:
            return "当前没有可用的 RAGFlow 知识库。"
        return "\n\n".join(_format_dataset(dataset) for dataset in datasets)
    except Exception as e:
        return f"列出 RAGFlow 知识库失败: {e}"


@tool
def create_ragflow_dataset(
    name: str,
    description: str = "",
    embedding_model: str = "text-embedding-v2@Tongyi-Qianwen",
) -> str:
    """创建一个新的 RAGFlow 知识库。"""
    monitor.report_tool(
        tool_name="创建 RAGFlow 知识库工具",
        args={"name": name, "description": description, "embedding_model": embedding_model},
    )

    try:
        client = get_ragflow_client()
        existing = _find_dataset(client, name)
        if existing is not None:
            return f"知识库已存在:\n{_format_dataset(existing)}"

        dataset = client.create_dataset(
            name=name,
            description=description or None,
            embedding_model=embedding_model or None,
        )
        return f"知识库创建成功:\n{_format_dataset(dataset)}"
    except Exception as e:
        return _format_ragflow_error("创建 RAGFlow 知识库", e)


@tool
def list_ragflow_documents(dataset_name_or_id: str) -> str:
    """列出指定 RAGFlow 知识库中的文档。"""
    monitor.report_tool(
        tool_name="列出 RAGFlow 文档工具",
        args={"dataset_name_or_id": dataset_name_or_id},
    )

    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, dataset_name_or_id)
        if dataset is None:
            return f"未找到知识库: {dataset_name_or_id}"

        documents = dataset.list_documents(page=1, page_size=1000)
        if not documents:
            return f"知识库“{_get_name(dataset)}”中没有文档。"

        return f"知识库: {_get_name(dataset)}\n" + "\n\n".join(
            _format_document(document) for document in documents
        )
    except Exception as e:
        return f"列出 RAGFlow 文档失败: {e}"


@tool
def upload_ragflow_documents(
    dataset_name_or_id: str,
    file_paths: str,
    parse_after_upload: bool = True,
) -> str:
    """
    上传一个或多个文件到指定 RAGFlow 知识库。

    file_paths 支持用逗号、分号或换行分隔多个文件路径。
    """
    monitor.report_tool(
        tool_name="上传 RAGFlow 文档工具",
        args={
            "dataset_name_or_id": dataset_name_or_id,
            "file_paths": file_paths,
            "parse_after_upload": parse_after_upload,
        },
    )

    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, dataset_name_or_id)
        if dataset is None:
            return f"未找到知识库: {dataset_name_or_id}"

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

        document_ids = [_get_id(document) for document in documents]
        lines = [
            f"上传成功，知识库: {_get_name(dataset)}",
            "上传文档:",
            *[_format_document(document) for document in documents],
        ]

        if parse_after_upload and document_ids:
            parse_status = dataset.parse_documents(document_ids)
            lines.append(f"解析状态: {parse_status}")

        return "\n\n".join(lines)
    except Exception as e:
        return f"上传 RAGFlow 文档失败: {e}"


@tool
def parse_ragflow_documents(dataset_name_or_id: str, document_names_or_ids: str) -> str:
    """重新解析指定 RAGFlow 知识库中的一个或多个文档。"""
    monitor.report_tool(
        tool_name="解析 RAGFlow 文档工具",
        args={"dataset_name_or_id": dataset_name_or_id, "document_names_or_ids": document_names_or_ids},
    )

    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, dataset_name_or_id)
        if dataset is None:
            return f"未找到知识库: {dataset_name_or_id}"

        documents, missing = _find_documents(dataset, document_names_or_ids)
        if not documents:
            return f"未找到要解析的文档: {', '.join(missing)}"

        document_ids = [_get_id(document) for document in documents]
        status = dataset.parse_documents(document_ids)
        result = [f"解析完成，知识库: {_get_name(dataset)}", f"解析状态: {status}"]
        if missing:
            result.append(f"未找到的文档: {', '.join(missing)}")
        return "\n".join(result)
    except Exception as e:
        return f"解析 RAGFlow 文档失败: {e}"


@tool
def delete_ragflow_documents(dataset_name_or_id: str, document_names_or_ids: str) -> str:
    """删除指定 RAGFlow 知识库中的一个或多个文档。"""
    monitor.report_tool(
        tool_name="删除 RAGFlow 文档工具",
        args={"dataset_name_or_id": dataset_name_or_id, "document_names_or_ids": document_names_or_ids},
    )

    try:
        client = get_ragflow_client()
        dataset = _find_dataset(client, dataset_name_or_id)
        if dataset is None:
            return f"未找到知识库: {dataset_name_or_id}"

        documents, missing = _find_documents(dataset, document_names_or_ids)
        if not documents:
            return f"未找到要删除的文档: {', '.join(missing)}"

        document_ids = [_get_id(document) for document in documents]
        dataset.delete_documents(ids=document_ids)

        result = [
            f"删除成功，知识库: {_get_name(dataset)}",
            f"已删除文档: {', '.join(_get_name(document) for document in documents)}",
        ]
        if missing:
            result.append(f"未找到的文档: {', '.join(missing)}")
        return "\n".join(result)
    except Exception as e:
        return f"删除 RAGFlow 文档失败: {e}"


@tool
def get_assistant_list() -> str:
    """获取 RAGFlow 中的所有聊天助手信息。"""
    monitor.report_tool(tool_name="获取 RAGFlow 助手列表工具")

    try:
        client = get_ragflow_client()
        assistants = client.list_chats()
        if not assistants:
            return "当前没有可用的 RAGFlow 助手。"

        result_lines = []
        for assistant in assistants:
            name = _get_name(assistant, "未知助手")
            description = _get_value(assistant, "description", "") or "无描述"
            datasets = _get_value(assistant, "datasets", None)
            dataset_ids = _get_value(assistant, "dataset_ids", None)

            if datasets:
                dataset_text = ", ".join(_get_name(dataset, "未知知识库") for dataset in datasets)
            elif dataset_ids:
                dataset_text = ", ".join(dataset_ids)
            else:
                dataset_text = "无关联知识库"

            result_lines.append(
                f"助手名称: {name}\n"
                f"助手描述: {description}\n"
                f"关联知识库: {dataset_text}"
            )

        return "\n\n".join(result_lines)
    except Exception as e:
        return f"获取助手列表失败: {e}"


@tool
def create_ask_delete(assistant_name: str, question: str) -> str:
    """向指定 RAGFlow 助手提问，并在回答后删除临时会话。"""
    monitor.report_tool(
        tool_name="向 RAGFlow 助手提问工具",
        args={"assistant_name": assistant_name, "question": question},
    )

    try:
        client = get_ragflow_client()
        chats = client.list_chats(name=assistant_name)
        if not chats:
            return f"未找到助手: {assistant_name}"

        chat = chats[0]
        session = chat.create_session(name="temp_session")
        try:
            stream = session.ask(question=question, stream=True)
            answer = ""
            for response in stream:
                answer = _get_value(response, "content", str(response))
        finally:
            chat.delete_sessions(ids=[session.id])

        return answer
    except Exception as e:
        return f"提问助手失败: {e}"


if __name__ == "__main__":
    print(list_ragflow_datasets.invoke({}))
    print()
    print(get_assistant_list.invoke({}))
