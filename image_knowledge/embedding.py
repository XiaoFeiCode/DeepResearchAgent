"""DashScope qwen3-vl-embedding client for cross-modal retrieval."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import httpx

SUPPORTED_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def validate_image_bytes(filename: str, content: bytes) -> tuple[str, str]:
    """Validate image type, size and signature, returning suffix and MIME type."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_TYPES:
        raise ValueError("图片知识库仅支持 PNG、JPEG 和 WebP")
    if not content:
        raise ValueError("图片文件为空")

    max_mb = float(os.getenv("MULTIMODAL_IMAGE_MAX_MB", "10"))
    if len(content) > max_mb * 1024 * 1024:
        raise ValueError(f"图片超过 {max_mb:g} MB 限制")

    header = content[:16]
    signature_valid = {
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
        ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
    }[suffix]
    if not signature_valid:
        raise ValueError("图片内容与扩展名不匹配")
    return suffix, SUPPORTED_IMAGE_TYPES[suffix]


def image_data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class MultimodalEmbeddingClient:
    """Generate comparable text and image vectors through DashScope HTTP API."""

    def __init__(self) -> None:
        self.endpoint = os.getenv(
            "MULTIMODAL_EMBEDDING_BASE_URL",
            "https://dashscope.aliyuncs.com/api/v1/services/embeddings/"
            "multimodal-embedding/multimodal-embedding",
        )
        self.api_key = (
            os.getenv("MULTIMODAL_EMBEDDING_API_KEY")
            or os.getenv("VISION_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or ""
        )
        self.model = os.getenv("MULTIMODAL_EMBEDDING_MODEL", "qwen3-vl-embedding")
        self.dimension = int(os.getenv("MULTIMODAL_EMBEDDING_DIMENSION", "1024"))
        self.timeout = float(os.getenv("MULTIMODAL_EMBEDDING_TIMEOUT_SECONDS", "60"))
        self.instruct = os.getenv(
            "MULTIMODAL_EMBEDDING_INSTRUCT",
            "Retrieve semantically similar knowledge-base images for this query.",
        )

    def embed_text(self, text: str) -> list[float]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("文字检索内容不能为空")
        return self._embed([{"text": normalized}], enable_fusion=False)

    def embed_image(self, content: bytes, mime_type: str) -> list[float]:
        return self._embed(
            [{"image": image_data_url(content, mime_type)}],
            enable_fusion=False,
        )

    def embed_fused(
        self,
        *,
        text: str,
        image_content: bytes,
        mime_type: str,
    ) -> list[float]:
        contents: list[dict[str, str]] = []
        if text.strip():
            contents.append({"text": text.strip()})
        contents.append({"image": image_data_url(image_content, mime_type)})
        return self._embed(contents, enable_fusion=True)

    def _embed(
        self,
        contents: list[dict[str, str]],
        *,
        enable_fusion: bool,
    ) -> list[float]:
        if not self.api_key:
            raise ValueError(
                "未配置 MULTIMODAL_EMBEDDING_API_KEY、VISION_API_KEY "
                "或 DASHSCOPE_API_KEY"
            )

        parameters: dict[str, Any] = {
            "dimension": self.dimension,
            "instruct": self.instruct,
        }
        if enable_fusion:
            parameters["enable_fusion"] = True

        response = httpx.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": {"contents": contents},
                "parameters": parameters,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("output", {}).get("embeddings", [])
        if not embeddings:
            message = payload.get("message") or "多模态向量接口没有返回向量"
            raise RuntimeError(message)

        vector = embeddings[0].get("embedding")
        if not isinstance(vector, list) or len(vector) != self.dimension:
            raise RuntimeError(
                f"多模态向量维度不匹配，期望 {self.dimension}，"
                f"实际 {len(vector) if isinstance(vector, list) else 0}"
            )
        return [float(value) for value in vector]
