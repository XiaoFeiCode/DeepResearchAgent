from pathlib import Path
from typing import Any

from ragflow_sdk import RAGFlow

try:
    from ragflow.config import _load_ragflow_env
except ImportError:
    from config import _load_ragflow_env


def get_ragflow_client() -> RAGFlow:
    """创建 RAGFlow 客户端。"""
    api_key, base_url = _load_ragflow_env()
    if not api_key or not base_url:
        raise ValueError("请先配置 RAGFLOW_API_KEY 和 RAGFLOW_API_URL。")
    return RAGFlow(api_key=api_key, base_url=base_url)


def create_dataset():
    """创建一个演示知识库。"""
    ragflow = get_ragflow_client()
    dataset = ragflow.create_dataset(
        name="demo_dataset",
        description="这是一个演示用的知识库，包含一些示例数据。",
        embedding_model="text-embedding-v2@Tongyi-Qianwen",
    )

    print(dataset)
    print(dataset.id)
    return dataset


def _normalize_file_paths(file_path: str | Path | list[str | Path]) -> list[Path]:
    """把单个文件路径或文件路径列表统一转换成 Path 列表。"""
    if isinstance(file_path, (str, Path)):
        paths = [Path(file_path)]
    else:
        paths = [Path(path) for path in file_path]

    if not paths:
        raise ValueError("请至少传入一个要上传的文件路径。")

    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"不是有效文件: {path}")

    return paths


# 上传知识库文件
def upload_file(
    dataset_id: str,
    file_path: str | Path | list[str | Path],
    parse_after_upload: bool = True,
) -> dict[str, Any]:
    """
    上传一个或多个文件到指定 RAGFlow 知识库。

    Args:
        dataset_id: RAGFlow 知识库 ID。
        file_path: 单个文件路径，或文件路径列表。
        parse_after_upload: 上传后是否自动触发文档解析。只有解析完成后，知识库检索才可用。

    Returns:
        dict: 上传成功的文档信息，以及可选的解析状态。
    """
    ragflow = get_ragflow_client()

    # 1. 查询知识库列表，找到对应 ID 的知识库。
    datasets = ragflow.list_datasets(id=dataset_id, page=1, page_size=10)
    if not datasets:
        raise ValueError(f"未找到知识库: {dataset_id}")
    dataset = datasets[0]

    # 2. 校验并整理文件路径。
    paths = _normalize_file_paths(file_path)

    # 3. RAGFlow SDK 要求上传格式为:
    #    {"display_name": 文件名, "blob": 二进制文件对象}
    opened_files = []
    try:
        document_list = []
        for path in paths:
            file_obj = path.open("rb")
            opened_files.append(file_obj)
            document_list.append({
                "display_name": path.name,
                "blob": file_obj,
            })

        # 4. 上传文件。返回值是 Document 对象列表。
        documents = dataset.upload_documents(document_list)
        # 返回值
        #         [
        #     Document(id="xxx1", name="a.docx"),
        #     Document(id="xxx2", name="b.pdf"),
        # ]
    finally:
        # 5. 无论上传成功还是失败，都关闭本地文件句柄。
        for file_obj in opened_files:
            file_obj.close()

    document_ids = [doc.id for doc in documents]
    result: dict[str, Any] = {
        "dataset_id": dataset.id,
        "uploaded_documents": [
            {
                "id": doc.id,
                "name": getattr(doc, "name", None),
            }
            for doc in documents
        ],
    }

    # 6. 上传后触发解析。parse_documents 会阻塞等待解析结束，并返回每个文档的状态。
    if parse_after_upload and document_ids:
        result["parse_status"] = dataset.parse_documents(document_ids)

    return result


if __name__ == "__main__":
    dataset_id = "b07c158267ea11f1b361dadf18279b3a"
    file_path = "./中华人民共和国刑法.docx"
    print(upload_file(dataset_id, file_path))
