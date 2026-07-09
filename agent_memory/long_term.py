"""User-scoped long-term memory backed by Milvus."""

from __future__ import annotations

import json
import os
import threading
import uuid
import warnings
from datetime import datetime, timezone
from typing import Any

from dotenv import find_dotenv, load_dotenv

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
)

from pymilvus import DataType, MilvusClient  # noqa: E402

from agent_memory.inference import MemoryInference

load_dotenv(find_dotenv())


class LongTermMemory:
    """Store reusable user facts and retrieve them by vector similarity."""

    def __init__(self) -> None:
        self._client: MilvusClient | None = None
        self._inference: MemoryInference | None = None
        self._lock = threading.RLock()

    @property
    def collection_name(self) -> str:
        return os.getenv("MILVUS_MEMORY_COLLECTION", "agent_long_term_memory")

    @property
    def dimension(self) -> int:
        return int(os.getenv("MEMORY_VECTOR_DIMENSION", "512"))

    @property
    def inference(self) -> MemoryInference:
        if self._inference is None:
            self._inference = MemoryInference(self.dimension)
        return self._inference

    def initialize(self) -> None:
        with self._lock:
            if self._client is not None:
                return

            uri = os.getenv("MILVUS_URI", "http://127.0.0.1:19531")
            token = os.getenv("MILVUS_TOKEN")
            self._client = MilvusClient(uri=uri, token=token) if token else MilvusClient(uri=uri)

            if self._client.has_collection(self.collection_name):
                return

            schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
            schema.add_field("user_id", DataType.VARCHAR, max_length=128)
            schema.add_field("memory_type", DataType.VARCHAR, max_length=32)
            schema.add_field("content", DataType.VARCHAR, max_length=8192)
            schema.add_field("source_thread_id", DataType.VARCHAR, max_length=64)
            schema.add_field("created_at", DataType.VARCHAR, max_length=64)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.dimension)

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

    def save(
        self,
        *,
        user_id: str,
        content: str,
        memory_type: str,
        source_thread_id: str,
    ) -> dict[str, Any]:
        self.initialize()
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Memory content cannot be empty")
        if len(normalized_content) > 8000:
            raise ValueError("Memory content is too long")

        assert self._client is not None
        existing = self._client.query(
            collection_name=self.collection_name,
            filter=(
                f"user_id == {json.dumps(user_id, ensure_ascii=False)} and "
                f"content == {json.dumps(normalized_content, ensure_ascii=False)}"
            ),
            output_fields=[
                "id",
                "user_id",
                "memory_type",
                "content",
                "source_thread_id",
                "created_at",
            ],
            limit=1,
        )
        if existing:
            return existing[0]

        memory_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        record = {
            "id": memory_id,
            "user_id": user_id,
            "memory_type": memory_type,
            "content": normalized_content,
            "source_thread_id": source_thread_id,
            "created_at": created_at,
            "vector": self.inference.embed([normalized_content])[0],
        }
        self._client.insert(collection_name=self.collection_name, data=[record])
        self._client.flush(collection_name=self.collection_name)
        return {key: value for key, value in record.items() if key != "vector"}

    def delete(self, *, user_id: str, memory_id: str) -> None:
        """Delete one user-owned memory."""
        self.initialize()
        assert self._client is not None
        self._client.delete(
            collection_name=self.collection_name,
            filter=(
                f"id == {json.dumps(memory_id)} and "
                f"user_id == {json.dumps(user_id, ensure_ascii=False)}"
            ),
        )

    def search(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        assert self._client is not None

        filters = [f"user_id == {json.dumps(user_id, ensure_ascii=False)}"]
        if memory_type:
            filters.append(
                f"memory_type == {json.dumps(memory_type, ensure_ascii=False)}"
            )

        candidate_limit = max(limit * 4, 10)
        results = self._client.search(
            collection_name=self.collection_name,
            data=[self.inference.embed([query])[0]],
            filter=" and ".join(filters),
            limit=max(1, min(candidate_limit, 50)),
            output_fields=[
                "memory_type",
                "content",
                "source_thread_id",
                "created_at",
            ],
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        )
        threshold = float(os.getenv("MEMORY_MIN_SIMILARITY", "0.12"))
        memories: list[dict[str, Any]] = []
        for hit in results[0] if results else []:
            score = float(hit.get("distance", 0.0))
            if score < threshold:
                continue
            entity = hit.get("entity", {})
            memories.append(
                {
                    "id": hit.get("id"),
                    "score": round(score, 4),
                    **entity,
                }
            )
        return self.inference.rerank(
            query=query,
            candidates=memories,
            top_n=limit,
        )


long_term_memory = LongTermMemory()
