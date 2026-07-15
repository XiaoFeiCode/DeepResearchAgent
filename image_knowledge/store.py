"""User-scoped image knowledge base backed by Milvus and local files."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymilvus import DataType, MilvusClient

from image_knowledge.embedding import (
    MultimodalEmbeddingClient,
    validate_image_bytes,
)


class ImageKnowledgeStore:
    def __init__(self, project_root: Path) -> None:
        self.storage_root = project_root / "runtime" / "image_knowledge"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._client: MilvusClient | None = None
        self._embedding: MultimodalEmbeddingClient | None = None
        self._lock = threading.RLock()

    @property
    def collection_name(self) -> str:
        return os.getenv(
            "MILVUS_IMAGE_COLLECTION",
            "multimodal_image_knowledge",
        )

    @property
    def dimension(self) -> int:
        return int(os.getenv("MULTIMODAL_EMBEDDING_DIMENSION", "1024"))

    @property
    def embedding(self) -> MultimodalEmbeddingClient:
        if self._embedding is None:
            self._embedding = MultimodalEmbeddingClient()
        return self._embedding

    def initialize(self) -> None:
        with self._lock:
            if self._client is not None:
                return

            uri = os.getenv("MILVUS_URI", "http://127.0.0.1:19531")
            token = os.getenv("MILVUS_TOKEN")
            self._client = (
                MilvusClient(uri=uri, token=token)
                if token
                else MilvusClient(uri=uri)
            )
            if self._client.has_collection(self.collection_name):
                return

            schema = MilvusClient.create_schema(
                auto_id=False,
                enable_dynamic_field=False,
            )
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
            schema.add_field("user_id", DataType.VARCHAR, max_length=128)
            schema.add_field("filename", DataType.VARCHAR, max_length=512)
            schema.add_field("description", DataType.VARCHAR, max_length=4096)
            schema.add_field("storage_path", DataType.VARCHAR, max_length=1024)
            schema.add_field("content_type", DataType.VARCHAR, max_length=64)
            schema.add_field("created_at", DataType.VARCHAR, max_length=64)
            schema.add_field(
                "vector",
                DataType.FLOAT_VECTOR,
                dim=self.dimension,
            )

            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(
                field_name="vector",
                index_type="HNSW",
                metric_type="COSINE",
                params={"M": 16, "efConstruction": 128},
            )
            self._client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
            )

    def add_image(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        description: str = "",
    ) -> dict[str, Any]:
        suffix, content_type = validate_image_bytes(filename, content)
        normalized_description = description.strip()[:4000]
        vector = self.embedding.embed_image(content, content_type)
        self.initialize()
        assert self._client is not None

        image_id = uuid.uuid4().hex
        user_dir = self.storage_root / self._user_storage_key(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        storage_path = user_dir / f"{image_id}{suffix}"
        storage_path.write_bytes(content)
        created_at = datetime.now(timezone.utc).isoformat()
        record = {
            "id": image_id,
            "user_id": user_id,
            "filename": Path(filename).name[:500],
            "description": normalized_description,
            "storage_path": str(storage_path.resolve()),
            "content_type": content_type,
            "created_at": created_at,
            "vector": vector,
        }
        try:
            self._client.insert(
                collection_name=self.collection_name,
                data=[record],
            )
            self._client.flush(collection_name=self.collection_name)
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise
        return self._public_payload(record)

    def list_images(self, *, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        assert self._client is not None
        records = self._client.query(
            collection_name=self.collection_name,
            filter=f"user_id == {json.dumps(user_id, ensure_ascii=False)}",
            output_fields=self._output_fields(),
            limit=max(1, min(limit, 200)),
        )
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return [self._public_payload(record) for record in records]

    def search(
        self,
        *,
        user_id: str,
        query_text: str = "",
        image_content: bytes | None = None,
        image_filename: str = "query.png",
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        normalized_query = query_text.strip()
        if image_content is not None:
            _, mime_type = validate_image_bytes(image_filename, image_content)
            if normalized_query:
                vector = self.embedding.embed_fused(
                    text=normalized_query,
                    image_content=image_content,
                    mime_type=mime_type,
                )
            else:
                vector = self.embedding.embed_image(image_content, mime_type)
        elif normalized_query:
            vector = self.embedding.embed_text(normalized_query)
        else:
            raise ValueError("文字和查询图片不能同时为空")

        self.initialize()
        assert self._client is not None
        result = self._client.search(
            collection_name=self.collection_name,
            data=[vector],
            filter=f"user_id == {json.dumps(user_id, ensure_ascii=False)}",
            limit=max(1, min(limit, 20)),
            output_fields=self._output_fields(),
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        )

        threshold = float(os.getenv("MULTIMODAL_SEARCH_MIN_SIMILARITY", "0.2"))
        matches: list[dict[str, Any]] = []
        for hit in result[0] if result else []:
            score = float(hit.get("distance", 0.0))
            if score < threshold:
                continue
            payload = self._public_payload(hit.get("entity", {}))
            payload["id"] = str(hit.get("id") or payload.get("id") or "")
            payload["score"] = round(score, 4)
            matches.append(payload)
        return matches

    def delete_image(self, *, user_id: str, image_id: str) -> None:
        record = self.get_image(user_id=user_id, image_id=image_id)
        self.initialize()
        assert self._client is not None
        self._client.delete(
            collection_name=self.collection_name,
            filter=(
                f"id == {json.dumps(image_id)} and "
                f"user_id == {json.dumps(user_id, ensure_ascii=False)}"
            ),
        )
        Path(record["storage_path"]).unlink(missing_ok=True)

    def get_image(self, *, user_id: str, image_id: str) -> dict[str, Any]:
        self.initialize()
        assert self._client is not None
        records = self._client.query(
            collection_name=self.collection_name,
            filter=(
                f"id == {json.dumps(image_id)} and "
                f"user_id == {json.dumps(user_id, ensure_ascii=False)}"
            ),
            output_fields=self._output_fields(),
            limit=1,
        )
        if not records:
            raise FileNotFoundError("图片不存在")
        path = Path(records[0]["storage_path"]).resolve()
        if not path.is_relative_to(self.storage_root.resolve()) or not path.is_file():
            raise FileNotFoundError("图片文件不存在")
        return records[0]

    @staticmethod
    def _user_storage_key(user_id: str) -> str:
        return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _output_fields() -> list[str]:
        return [
            "id",
            "filename",
            "description",
            "storage_path",
            "content_type",
            "created_at",
        ]

    @staticmethod
    def _public_payload(record: dict[str, Any]) -> dict[str, Any]:
        image_id = str(record.get("id") or "")
        return {
            "id": image_id,
            "filename": record.get("filename", ""),
            "description": record.get("description", ""),
            "content_type": record.get("content_type", ""),
            "created_at": record.get("created_at", ""),
            "content_url": f"/api/image-knowledge/images/{image_id}/content",
        }
