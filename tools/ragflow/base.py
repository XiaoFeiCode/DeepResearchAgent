from pathlib import Path
from typing import Any
from uuid import UUID

import requests

from langchain_core.tools import tool
from ragflow_sdk import RAGFlow

from api.monitor import monitor
from tools.ragflow.config import PROJECT_ROOT, load_ragflow_env


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
            candidates.append(PROJECT_ROOT / path)

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
    api_key, base_url = load_ragflow_env()
    return RAGFlow(api_key=api_key, base_url=base_url)


def _chat_api_data(response: requests.Response, action: str) -> Any:
    """兼容新版 RAGFlow 聊天接口的响应结构。"""
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(f"{action}返回非 JSON 响应（HTTP {response.status_code}）") from error
    if response.status_code >= 400 or payload.get("code", 0) != 0:
        raise RuntimeError(f"{action}失败: {payload.get('message') or payload}")
    return payload.get("data")


def _list_chat_payloads(client: RAGFlow, name: str = "") -> list[dict[str, Any]]:
    """读取 RAGFlow 助手列表，兼容 data 为列表或 data.chats 的版本差异。"""
    response = requests.get(
        f"{client.api_url}/chats",
        headers=client.authorization_header,
        params={"page": 1, "page_size": 100, "name": name or None},
        timeout=30,
    )
    data = _chat_api_data(response, "获取 RAGFlow 助手列表")
    chats = data.get("chats", []) if isinstance(data, dict) else data
    if not isinstance(chats, list):
        raise RuntimeError("RAGFlow 助手列表返回格式异常")
    return [chat for chat in chats if isinstance(chat, dict)]


def _ask_chat(client: RAGFlow, chat: dict[str, Any], question: str) -> str:
    """创建临时会话提问，并在结束后清理会话。"""
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        raise RuntimeError("RAGFlow 助手缺少 ID")
    session_id = ""
    try:
        created = requests.post(
            f"{client.api_url}/chats/{chat_id}/sessions",
            headers=client.authorization_header,
            json={"name": "omniresearch-temp"},
            timeout=30,
        )
        session = _chat_api_data(created, "创建 RAGFlow 临时会话")
        if not isinstance(session, dict):
            raise RuntimeError("RAGFlow 临时会话返回格式异常")
        session_id = str(session.get("id") or "")
        if not session_id:
            raise RuntimeError("RAGFlow 临时会话缺少 ID")
        completed = requests.post(
            f"{client.api_url}/chats/{chat_id}/completions",
            headers=client.authorization_header,
            json={"question": question, "stream": False, "session_id": session_id},
            timeout=180,
        )
        data = _chat_api_data(completed, "向 RAGFlow 助手提问")
        answer = (data.get("answer") or data.get("content")) if isinstance(data, dict) else data
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("RAGFlow 助手没有返回可用答案")
        return answer.strip()
    finally:
        if session_id:
            requests.delete(
                f"{client.api_url}/chats/{chat_id}/sessions",
                headers=client.authorization_header,
                json={"ids": [session_id]},
                timeout=30,
            )

def _list_all_documents(dataset: Any) -> list[Any]:
    """按新版 RAGFlow SDK 的单页上限分页获取知识库全部文档。"""
    page = 1
    page_size = 100
    documents: list[Any] = []
    while True:
        batch = dataset.list_documents(page=page, page_size=page_size)
        documents.extend(batch)
        if len(batch) < page_size:
            return documents
        page += 1

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

    all_docs = _list_all_documents(dataset)
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

        documents = _list_all_documents(dataset)
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
    """列出当前 API Key 可访问的 RAGFlow 助手及其关联知识库。"""
    monitor.report_tool(tool_name="获取 RAGFlow 助手列表工具")
    try:
        assistants = _list_chat_payloads(get_ragflow_client())
        if not assistants:
            return "当前没有可用的 RAGFlow 助手。"
        result_lines = []
        for assistant in assistants:
            name = str(assistant.get("name") or "未知助手")
            description = str(assistant.get("description") or "无描述")
            datasets = assistant.get("kb_names") or assistant.get("dataset_ids") or []
            dataset_text = ", ".join(str(item) for item in datasets) or "无关联知识库"
            result_lines.append(
                f"助手名称: {name}\n助手描述: {description}\n关联知识库: {dataset_text}"
            )
        return "\n\n".join(result_lines)
    except Exception as error:
        return f"获取助手列表失败: {error}"

@tool
def create_ask_delete(assistant_name: str, question: str) -> str:
    """向指定 RAGFlow 助手提问，并在回答后删除临时会话。"""
    monitor.report_tool(
        tool_name="向 RAGFlow 助手提问工具",
        args={"assistant_name": assistant_name, "question": question},
    )
    try:
        assistants = _list_chat_payloads(get_ragflow_client())
        chat = next((item for item in assistants if item.get("name") == assistant_name), None)
        if chat is None:
            return f"未找到助手: {assistant_name}"
        return _ask_chat(get_ragflow_client(), chat, question)
    except Exception as error:
        return f"提问助手失败: {error}"
