"""Embedding and reranking clients for cloud APIs and local vLLM services."""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any

import httpx


def _required_api_key(*names: str) -> str:
    """Return the first configured API key without duplicating secrets in .env."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    joined = ", ".join(names)
    raise ValueError(f"Missing API key. Configure one of: {joined}")


class HashEmbedding:
    """Deterministic local fallback used when the vLLM service is unavailable."""

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
    """OpenAI-compatible `/v1/embeddings` client served by vLLM."""

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "VLLM_EMBEDDING_BASE_URL",
            "http://127.0.0.1:8001/v1",
        ).rstrip("/")
        self.model = os.getenv(
            "VLLM_EMBEDDING_MODEL",
            "BAAI/bge-small-zh-v1.5",
        )
        self.api_key = os.getenv("VLLM_EMBEDDING_API_KEY", "local-vllm")
        self.timeout = float(os.getenv("VLLM_INFERENCE_TIMEOUT_SECONDS", "30"))

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
    """Cohere-compatible `/v1/rerank` client served by vLLM."""

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "VLLM_RERANKER_BASE_URL",
            "http://127.0.0.1:8002/v1",
        ).rstrip("/")
        self.model = os.getenv(
            "VLLM_RERANKER_MODEL",
            "BAAI/bge-reranker-base",
        )
        self.api_key = os.getenv("VLLM_RERANKER_API_KEY", "local-vllm")
        self.timeout = float(os.getenv("VLLM_INFERENCE_TIMEOUT_SECONDS", "30"))

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
    """OpenAI-compatible cloud embedding client, defaulting to Alibaba Bailian."""

    def __init__(self, dimension: int) -> None:
        self.base_url = os.getenv(
            "MEMORY_EMBEDDING_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).rstrip("/")
        self.model = os.getenv("MEMORY_EMBEDDING_MODEL", "text-embedding-v4")
        self.dimension = dimension
        self.timeout = float(os.getenv("MEMORY_INFERENCE_TIMEOUT_SECONDS", "30"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        api_key = _required_api_key(
            "MEMORY_EMBEDDING_API_KEY",
            "DASHSCOPE_API_KEY",
            "VISION_API_KEY",
        )
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
    """Alibaba Bailian text rerank API client."""

    def __init__(self) -> None:
        self.endpoint = os.getenv(
            "MEMORY_RERANKER_ENDPOINT",
            (
                "https://dashscope.aliyuncs.com/api/v1/services/rerank/"
                "text-rerank/text-rerank"
            ),
        )
        self.model = os.getenv("MEMORY_RERANKER_MODEL", "gte-rerank-v2")
        self.timeout = float(os.getenv("MEMORY_INFERENCE_TIMEOUT_SECONDS", "30"))

    def rerank(
        self,
        *,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        api_key = _required_api_key(
            "MEMORY_RERANKER_API_KEY",
            "DASHSCOPE_API_KEY",
            "VISION_API_KEY",
        )
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
    """Select cloud API, vLLM, or hash inference through environment settings."""

    def __init__(self, dimension: int) -> None:
        self.embedding_provider = os.getenv(
            "MEMORY_EMBEDDING_PROVIDER",
            "api",
        ).lower()
        self.reranker_provider = os.getenv(
            "MEMORY_RERANKER_PROVIDER",
            self.embedding_provider,
        ).lower()
        self.reranker_enabled = os.getenv(
            "MEMORY_RERANKER_ENABLED",
            "true",
        ).lower() not in {"0", "false", "no", "off"}
        self.allow_fallback = os.getenv(
            "MEMORY_ALLOW_HASH_FALLBACK",
            "false",
        ).lower() not in {"0", "false", "no", "off"}
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
