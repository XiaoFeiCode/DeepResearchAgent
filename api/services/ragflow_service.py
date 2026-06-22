from pathlib import Path

from fastapi import UploadFile

from tools.ragflow.base import (
    _find_dataset,
    _find_documents,
    _get_id,
    _get_name,
    _get_value,
    get_ragflow_client,
)


def dataset_payload(dataset) -> dict:
    return {
        "id": _get_id(dataset),
        "name": _get_name(dataset, "未知知识库"),
        "description": _get_value(dataset, "description", "") or "",
        "doc_num": _get_value(dataset, "doc_num", 0),
        "chunk_num": _get_value(dataset, "chunk_num", 0),
        "language": _get_value(dataset, "language", ""),
        "parser_id": _get_value(dataset, "parser_id", ""),
    }


def document_payload(document) -> dict:
    return {
        "id": _get_id(document),
        "name": _get_name(document, "未知文档"),
        "run": _get_value(document, "run", None),
        "progress": _get_value(document, "progress", None),
        "chunk_count": _get_value(document, "chunk_count", None),
        "token_count": _get_value(document, "token_count", None),
        "create_date": _get_value(document, "create_date", ""),
        "update_date": _get_value(document, "update_date", ""),
    }


class RagflowService:
    """封装 RAGFlow SDK 的同步调用，路由层负责放入线程池执行。"""

    def list_datasets(self) -> list[dict]:
        datasets = get_ragflow_client().list_datasets(page=1, page_size=100)
        return [dataset_payload(dataset) for dataset in datasets]

    def list_documents(self, dataset_name_or_id: str) -> dict:
        dataset = self._require_dataset(dataset_name_or_id)
        documents = dataset.list_documents(page=1, page_size=1000)
        return {
            "dataset": dataset_payload(dataset),
            "documents": [document_payload(document) for document in documents],
        }

    def upload_documents(
        self,
        dataset_name_or_id: str,
        files: list[UploadFile],
        parse_after_upload: bool,
    ) -> dict:
        dataset = self._require_dataset(dataset_name_or_id)
        documents = dataset.upload_documents(
            [
                {"display_name": Path(upload.filename or "upload").name, "blob": upload.file}
                for upload in files
            ]
        )
        document_ids = [_get_id(document) for document in documents if _get_id(document)]
        parse_status = None
        if parse_after_upload and document_ids:
            parse_status = dataset.parse_documents(document_ids)

        return {
            "status": "uploaded",
            "dataset": dataset_payload(dataset),
            "documents": [document_payload(document) for document in documents],
            "parse_status": parse_status,
        }

    def parse_documents(self, dataset_name_or_id: str, names_or_ids: str) -> dict:
        dataset = self._require_dataset(dataset_name_or_id)
        documents, missing = _find_documents(dataset, names_or_ids)
        if not documents:
            raise LookupError(f"未找到文档: {', '.join(missing)}")

        document_ids = [_get_id(document) for document in documents if _get_id(document)]
        return {
            "status": "parsed",
            "parse_status": dataset.parse_documents(document_ids),
            "missing": missing,
        }

    def delete_documents(self, dataset_name_or_id: str, names_or_ids: str) -> dict:
        dataset = self._require_dataset(dataset_name_or_id)
        documents, missing = _find_documents(dataset, names_or_ids)
        if not documents:
            raise LookupError(f"未找到文档: {', '.join(missing)}")

        document_ids = [_get_id(document) for document in documents if _get_id(document)]
        dataset.delete_documents(ids=document_ids)
        return {
            "status": "deleted",
            "deleted": [document_payload(document) for document in documents],
            "missing": missing,
        }

    @staticmethod
    def _require_dataset(dataset_name_or_id: str):
        dataset = _find_dataset(get_ragflow_client(), dataset_name_or_id)
        if dataset is None:
            raise LookupError(f"未找到知识库: {dataset_name_or_id}")
        return dataset
