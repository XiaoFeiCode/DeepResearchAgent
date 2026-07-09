"""Embedding and reranking clients for vLLM pooling services."""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any

import httpx


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


class MemoryInference:
    """Select vLLM inference with explicit local fallback."""

    def __init__(self, dimension: int) -> None:
        self.embedding_provider = os.getenv(
            "MEMORY_EMBEDDING_PROVIDER",
            "vllm",
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
        self._vllm_embedding = VLLMEmbeddingClient()
        self._vllm_reranker = VLLMRerankerClient()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.embedding_provider != "vllm":
            return self._hash.embed(texts)
        try:
            vectors = self._vllm_embedding.embed(texts)
            if any(len(vector) != self._hash.dimension for vector in vectors):
                raise ValueError(
                    "vLLM embedding dimension does not match MEMORY_VECTOR_DIMENSION"
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
            reranked = self._vllm_reranker.rerank(
                query=query,
                candidates=candidates,
                top_n=top_n,
            )
            return reranked or candidates[:top_n]
        except Exception:
            return candidates[:top_n]
