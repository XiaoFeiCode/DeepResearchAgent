"""云端 API 与本地 vLLM 的向量化和重排客户端。"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import httpx

from core.settings import get_settings


class HashEmbedding:
    """vLLM 不可用时使用的确定性本地降级实现。"""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", " ", text.lower().strip())
        compact = normalized.replace(" ", "")
        tokens = re.findall(r"[\w]+", normalized, flags=re.UNICODE)
        for size in (1, 2, 3):
            tokens.extend(
                compact[index : index + size]
                for index in range(max(0, len(compact) - size + 1))
            )

        vector = [0.0] * self.dimension
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            vector[index] += 1.0 if value & 1 else -1.0

        norm = math.sqrt(sum(value * value for value in vector))
        return vector if norm == 0 else [value / norm for value in vector]


class VLLMEmbeddingClient:
    """调用 vLLM OpenAI 兼容 `/v1/embeddings` 接口的客户端。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.vllm_embedding_base_url
        self.model = settings.vllm_embedding_model
        self.api_key = settings.vllm_embedding_api_key
        self.timeout = settings.vllm_inference_timeout_seconds

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


class VLLMRerankerClient:
    """调用 vLLM Cohere 兼容 `/v1/rerank` 接口的客户端。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.vllm_reranker_base_url
        self.model = settings.vllm_reranker_model
        self.api_key = settings.vllm_reranker_api_key
        self.timeout = settings.vllm_inference_timeout_seconds

    def rerank(
        self,
        *,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        response = httpx.post(
            f"{self.base_url}/rerank",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "query": query,
                "documents": [item["content"] for item in candidates],
                "top_n": min(top_n, len(candidates)),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        reranked: list[dict[str, Any]] = []
        for result in response.json().get("results", []):
            index = int(result["index"])
            if not 0 <= index < len(candidates):
                continue
            item = dict(candidates[index])
            item["rerank_score"] = round(
                float(result.get("relevance_score", result.get("score", 0.0))),
                4,
            )
            reranked.append(item)
        return reranked


class APIEmbeddingClient:
    """OpenAI 兼容云端向量客户端，默认使用阿里云百炼。"""

    def __init__(self, dimension: int) -> None:
        settings = get_settings()
        self.base_url = settings.memory_embedding_base_url
        self.model = settings.memory_embedding_model
        self.dimension = dimension
        self.timeout = settings.memory_inference_timeout_seconds

    def embed(self, texts: list[str]) -> list[list[float]]:
        api_key = get_settings().memory_embedding_api_key_value()
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": self.model,
                "input": texts,
                "dimensions": self.dimension,
                "encoding_format": "float",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


class APIRerankerClient:
    """阿里云百炼文本重排 API 客户端。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.endpoint = settings.memory_reranker_endpoint
        self.model = settings.memory_reranker_model
        self.timeout = settings.memory_inference_timeout_seconds

    def rerank(
        self,
        *,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        api_key = get_settings().memory_reranker_api_key_value()
        response = httpx.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": self.model,
                "input": {
                    "query": query,
                    "documents": [item["content"] for item in candidates],
                },
                "parameters": {
                    "return_documents": False,
                    "top_n": min(top_n, len(candidates)),
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        reranked: list[dict[str, Any]] = []
        for result in response.json().get("output", {}).get("results", []):
            index = int(result["index"])
            if not 0 <= index < len(candidates):
                continue
            item = dict(candidates[index])
            item["rerank_score"] = round(
                float(result.get("relevance_score", result.get("score", 0.0))),
                4,
            )
            reranked.append(item)
        return reranked


class MemoryInference:
    """根据统一配置选择云端 API、vLLM 或哈希降级推理。"""

    def __init__(self, dimension: int) -> None:
        settings = get_settings()
        self.embedding_provider = settings.memory_embedding_provider
        self.reranker_provider = (
            settings.memory_reranker_provider or self.embedding_provider
        )
        self.reranker_enabled = settings.memory_reranker_enabled
        self.allow_fallback = settings.memory_allow_hash_fallback
        self._hash = HashEmbedding(dimension)
        self._api_embedding = APIEmbeddingClient(dimension)
        self._api_reranker = APIRerankerClient()
        self._vllm_embedding = VLLMEmbeddingClient()
        self._vllm_reranker = VLLMRerankerClient()

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            if self.embedding_provider == "api":
                vectors = self._api_embedding.embed(texts)
            elif self.embedding_provider == "vllm":
                vectors = self._vllm_embedding.embed(texts)
            elif self.embedding_provider == "hash":
                vectors = self._hash.embed(texts)
            else:
                raise ValueError(
                    "MEMORY_EMBEDDING_PROVIDER must be api, vllm, or hash"
                )
            if any(len(vector) != self._hash.dimension for vector in vectors):
                raise ValueError(
                    "Embedding dimension does not match MEMORY_VECTOR_DIMENSION"
                )
            return vectors
        except Exception:
            if not self.allow_fallback:
                raise
            return self._hash.embed(texts)

    def rerank(
        self,
        *,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        if not self.reranker_enabled:
            return candidates[:top_n]
        try:
            if self.reranker_provider == "api":
                client = self._api_reranker
            elif self.reranker_provider == "vllm":
                client = self._vllm_reranker
            elif self.reranker_provider in {"none", "off", "disabled"}:
                return candidates[:top_n]
            else:
                raise ValueError(
                    "MEMORY_RERANKER_PROVIDER must be api, vllm, or none"
                )
            reranked = client.rerank(
                query=query,
                candidates=candidates,
                top_n=top_n,
            )
            return reranked or candidates[:top_n]
        except Exception:
            return candidates[:top_n]
