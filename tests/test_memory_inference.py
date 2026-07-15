from __future__ import annotations

from typing import Any

from agent_memory.inference import (
    APIEmbeddingClient,
    APIRerankerClient,
    MemoryInference,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_api_embedding_uses_configured_dimension(monkeypatch) -> None:
    request: dict[str, Any] = {}
    monkeypatch.setenv("VISION_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "text-embedding-v4")

    def fake_post(url, *, headers, json, timeout):
        request.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            }
        )

    monkeypatch.setattr("agent_memory.inference.httpx.post", fake_post)
    vectors = APIEmbeddingClient(dimension=2).embed(["第一条", "第二条"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert request["json"]["dimensions"] == 2
    assert request["headers"]["Authorization"] == "Bearer test-key"


def test_api_reranker_maps_scores_to_candidates(monkeypatch) -> None:
    monkeypatch.setenv("VISION_API_KEY", "test-key")

    def fake_post(url, *, headers, json, timeout):
        return FakeResponse(
            {
                "output": {
                    "results": [
                        {"index": 1, "relevance_score": 0.91},
                        {"index": 0, "relevance_score": 0.42},
                    ]
                }
            }
        )

    monkeypatch.setattr("agent_memory.inference.httpx.post", fake_post)
    candidates = [{"content": "A"}, {"content": "B"}]
    result = APIRerankerClient().rerank(
        query="B",
        candidates=candidates,
        top_n=2,
    )

    assert [item["content"] for item in result] == ["B", "A"]
    assert result[0]["rerank_score"] == 0.91


def test_memory_inference_selects_api_provider(monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_EMBEDDING_PROVIDER", "api")
    inference = MemoryInference(dimension=2)
    monkeypatch.setattr(inference._api_embedding, "embed", lambda texts: [[0.2, 0.8]])

    assert inference.embed(["测试"]) == [[0.2, 0.8]]
