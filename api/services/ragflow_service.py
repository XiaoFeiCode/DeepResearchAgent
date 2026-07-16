import hashlib
import re
from pathlib import Path
from urllib.parse import quote

import requests
from fastapi import UploadFile

from tools.ragflow.base import (
    _find_dataset,
    _find_documents,
    _get_id,
    _get_name,
    _get_value,
    _list_all_documents,
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


_SAFE_IMAGE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_RAGFLOW_IMAGE_BYTES = 20 * 1024 * 1024
_FIGURE_CAPTION = re.compile(r"(?:^|\s)(?:fig(?:ure)?\.?\s*\d+[a-z]?|图\s*\d+[a-z]?)", re.IGNORECASE)


def _response_data(response: requests.Response, action: str):
    """校验 RAGFlow HTTP 响应，并返回 data 字段。"""
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(
            f"{action}返回了非 JSON 响应（HTTP {response.status_code}）"
        ) from error

    if response.status_code >= 400:
        raise RuntimeError(f"{action}失败（HTTP {response.status_code}）: {payload}")
    if payload.get("code", 0) != 0:
        raise RuntimeError(f"{action}失败: {payload.get('message') or payload}")
    return payload.get("data") or {}


def _page_number(chunk: dict) -> int | None:
    positions = chunk.get("positions") or []
    if positions and isinstance(positions[0], (list, tuple)) and positions[0]:
        try:
            return int(positions[0][0])
        except (TypeError, ValueError):
            return None
    return None


def _detect_image_content_type(content: bytes, fallback: str = "") -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if fallback.startswith("image/"):
        return fallback.split(";", 1)[0]
    raise RuntimeError("RAGFlow 返回的内容不是受支持的图片格式")


def _is_visual_chunk(chunk: dict) -> bool:
    """识别 RAGFlow 多模态解析生成的图片 Chunk，排除普通正文版面截图。"""
    content = str(chunk.get("content") or "").strip()
    normalized = content.lower()
    return (
        "analysis of the image" in normalized
        or "visual type" in normalized
        or bool(_FIGURE_CAPTION.search(content))
    )


def _caption_priority(chunk: dict) -> int:
    """同一原图可能对应视觉描述和图注两个 Chunk，优先保留图注。"""
    content = str(chunk.get("content") or "")
    if _FIGURE_CAPTION.search(content) and "analysis of the image" not in content.lower():
        return 2
    return 1 if _is_visual_chunk(chunk) else 0


def _list_document_chunks(client, dataset_id: str, document_id: str) -> list[dict]:
    """按新版 RAGFlow 的每页上限分页读取文档 Chunk。"""
    chunks: list[dict] = []
    page = 1
    page_size = 100
    while True:
        response = requests.get(
            f"{client.api_url}/datasets/{dataset_id}/documents/{document_id}/chunks",
            headers=client.authorization_header,
            params={"page": page, "page_size": page_size},
            timeout=60,
        )
        data = _response_data(response, "读取 RAGFlow 文档 Chunk")
        batch = data.get("chunks", [])
        if not isinstance(batch, list):
            raise RuntimeError("RAGFlow 文档 Chunk 返回格式异常")
        chunks.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < page_size:
            return chunks
        page += 1

def _fetch_ragflow_image(client, image_id: str) -> tuple[bytes, str]:
    """读取 RAGFlow 文档解析出的原始图片，并兼容新旧服务端路由。"""
    encoded_image_id = quote(image_id, safe="")
    api_url = client.api_url.rstrip("/")
    api_root = api_url.removesuffix("/api/v1")
    image_urls = [
        # RAGFlow 0.22+ 使用复数 documents/images 路由。
        f"{api_url}/documents/images/{encoded_image_id}",
        # 兼容部分旧版本的图片读取路径。
        f"{api_root}/v1/document/image/{encoded_image_id}",
    ]

    response = None
    for image_url in image_urls:
        candidate = requests.get(
            image_url,
            headers=client.authorization_header,
            timeout=30,
        )
        if candidate.status_code < 400:
            response = candidate
            break
        response = candidate

    if response is None or response.status_code >= 400:
        status_code = response.status_code if response is not None else "unknown"
        raise LookupError(f"RAGFlow 图片不存在（HTTP {status_code}）")
    if not response.content:
        raise LookupError("RAGFlow 返回了空图片")
    if len(response.content) > _MAX_RAGFLOW_IMAGE_BYTES:
        raise ValueError("RAGFlow 图片超过 20 MB 限制")
    return response.content, _detect_image_content_type(
        response.content,
        response.headers.get("content-type", ""),
    )

class RagflowService:
    """封装 RAGFlow SDK 的同步调用，路由层负责放入线程池执行。"""

    def list_datasets(self) -> list[dict]:
        datasets = get_ragflow_client().list_datasets(page=1, page_size=100)
        return [dataset_payload(dataset) for dataset in datasets]

    def create_dataset(self, name: str, description: str = "") -> dict:
        """创建 RAGFlow 知识库，嵌入模型沿用租户已配置的默认模型。"""
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("知识库名称不能为空")
        dataset = get_ragflow_client().create_dataset(
            name=normalized_name,
            description=description.strip() or None,
        )
        return dataset_payload(dataset)
    def list_documents(self, dataset_name_or_id: str) -> dict:
        dataset = self._require_dataset(dataset_name_or_id)
        documents = _list_all_documents(dataset)
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
        """?? RAGFlow ???????????????????????"""
        dataset = self._require_dataset(dataset_name_or_id)
        documents, missing = _find_documents(dataset, names_or_ids)
        if not documents:
            raise LookupError(f"未找到文档: {', '.join(missing)}")

        document_ids = [_get_id(document) for document in documents if _get_id(document)]
        client = get_ragflow_client()
        response = requests.post(
            f"{client.api_url}/datasets/{_get_id(dataset)}/documents/parse",
            headers=client.authorization_header,
            json={"document_ids": document_ids},
            timeout=30,
        )
        return {
            "status": "parse_submitted",
            "parse_status": _response_data(response, "提交 RAGFlow 文档解析"),
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

    def search_images(
        self,
        query: str,
        dataset_name_or_id: str,
        document_name_or_id: str = "",
        limit: int = 8,
    ) -> dict:
        """检索 RAGFlow 原始 Chunk，保留 SDK 未暴露的 image_id。"""
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("图片检索问题不能为空")

        dataset = self._require_dataset(dataset_name_or_id)
        documents = _list_all_documents(dataset)
        document_by_id = {_get_id(item): item for item in documents}
        document_ids: list[str] = []

        if document_name_or_id.strip():
            matched, missing = _find_documents(dataset, document_name_or_id)
            if not matched:
                raise LookupError(f"未找到文档: {', '.join(missing)}")
            document_ids = [_get_id(item) for item in matched if _get_id(item)]

        client = get_ragflow_client()
        response = requests.post(
            f"{client.api_url}/retrieval",
            headers=client.authorization_header,
            json={
                "question": normalized_query,
                "dataset_ids": [_get_id(dataset)],
                "document_ids": document_ids,
                "page": 1,
                "page_size": max(1, min(int(limit), 20)) * 3,
                "similarity_threshold": 0.1,
                "vector_similarity_weight": 0.3,
                "top_k": 64,
                "rerank_id": None,
                "keyword": False,
                "cross_languages": None,
                "metadata_condition": None,
                "use_kg": False,
                "toc_enhance": False,
            },
            timeout=60,
        )
        try:
            data = _response_data(response, "RAGFlow 图片检索")
        except RuntimeError:
            # 已经限定文档时仍可直接扫描其多模态 Chunk；部分旧版 RAGFlow
            # 会对过短或纯指令式检索词触发内部 AssertionError。
            data = {"chunks": []}

        retrieval_chunks = data.get("chunks", [])
        similarity_by_chunk_id = {
            str(chunk.get("id") or ""): float(chunk.get("similarity") or 0)
            for chunk in retrieval_chunks
        }

        # Retrieval API 会同时命中普通正文 Chunk 和视觉 Chunk。普通正文的 image_id
        # 只是版面裁剪图；要返回论文插图，需要从目标文档的原始 Chunk 中筛选视觉描述/图注。
        scan_document_ids = document_ids or list(
            dict.fromkeys(
                str(chunk.get("document_id") or "")
                for chunk in retrieval_chunks
                if chunk.get("document_id")
            )
        )[:5]
        if not scan_document_ids:
            scan_document_ids = [_get_id(item) for item in documents[:5] if _get_id(item)]
        visual_chunks: list[dict] = []
        for document_id in scan_document_ids:
            for chunk in _list_document_chunks(
                client,
                _get_id(dataset),
                document_id,
            ):
                if not chunk.get("image_id") or not _is_visual_chunk(chunk):
                    continue
                enriched = dict(chunk)
                enriched["similarity"] = similarity_by_chunk_id.get(str(chunk.get("id") or ""))
                visual_chunks.append(enriched)

        candidate_chunks = visual_chunks or retrieval_chunks

        # 多模态解析通常会为同一张图生成“视觉分析”和“图注”两个 Chunk，
        # image_id 虽不同但图片字节相同，因此按内容哈希去重。
        deduplicated: dict[str, dict] = {}
        for chunk in candidate_chunks:
            image_id = str(chunk.get("image_id") or "").strip()
            if not image_id:
                continue
            try:
                image_content, _ = _fetch_ragflow_image(client, image_id)
                fingerprint = hashlib.sha256(image_content).hexdigest()
            except Exception:
                fingerprint = image_id

            existing = deduplicated.get(fingerprint)
            if existing is None or (
                _caption_priority(chunk), float(chunk.get("similarity") or 0)
            ) > (
                _caption_priority(existing), float(existing.get("similarity") or 0)
            ):
                deduplicated[fingerprint] = chunk

        ranked_chunks = sorted(
            deduplicated.values(),
            key=lambda chunk: (
                -float(chunk.get("similarity") or 0),
                _page_number(chunk) or 0,
            ),
        )

        matches = []
        seen_image_ids: set[str] = set()
        for chunk in ranked_chunks:
            image_id = str(chunk.get("image_id") or "").strip()
            if not image_id or image_id in seen_image_ids:
                continue

            document_id = str(chunk.get("document_id") or "")
            document = document_by_id.get(document_id)
            document_name = _get_name(document, "未知文档") if document else "未知文档"
            match = {
                "id": f"ragflow:{image_id}",
                "image_id": image_id,
                "filename": document_name,
                "description": str(chunk.get("content") or "").strip(),
                "document_id": document_id,
                "document_name": document_name,
                "page": _page_number(chunk),
                "source": "ragflow",
                "content_url": f"/api/ragflow/images/{quote(image_id, safe='')}",
            }
            if chunk.get("similarity") is not None:
                match["score"] = float(chunk["similarity"])
            matches.append(match)
            seen_image_ids.add(image_id)
            if len(matches) >= max(1, min(int(limit), 20)):
                break

        return {
            "dataset": dataset_payload(dataset),
            "query": normalized_query,
            "match_count": len(matches),
            "matches": matches,
        }

    def get_image(self, image_id: str) -> tuple[bytes, str]:
        """从 RAGFlow 的文档图片接口读取图片，避免向前端暴露 API Key。"""
        normalized_id = image_id.strip()
        if not normalized_id or not _SAFE_IMAGE_ID.fullmatch(normalized_id):
            raise ValueError("无效的 RAGFlow 图片 ID")

        return _fetch_ragflow_image(get_ragflow_client(), normalized_id)

    @staticmethod
    def _require_dataset(dataset_name_or_id: str):
        dataset = _find_dataset(get_ragflow_client(), dataset_name_or_id)
        if dataset is None:
            raise LookupError(f"未找到知识库: {dataset_name_or_id}")
        return dataset
