"""用于跨模态检索的百炼 qwen3-vl-embedding 客户端。"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from core.settings import get_settings

SUPPORTED_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def validate_image_bytes(filename: str, content: bytes) -> tuple[str, str]:
    """校验上传类型、大小和文件签名，并返回后缀与 MIME 类型。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_TYPES:
        raise ValueError("图片知识库仅支持 PNG、JPEG 和 WebP")
    if not content:
        raise ValueError("图片文件为空")

    max_mb = get_settings().multimodal_image_max_mb
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


def prepare_image_for_embedding(
    filename: str,
    content: bytes,
) -> tuple[bytes, str, str]:
    """校验上传图片，并把大图压缩为适合云端 API 的 JPEG。"""
    suffix, mime_type = validate_image_bytes(filename, content)
    settings = get_settings()
    target_mb = settings.multimodal_embedding_image_max_mb
    target_bytes = max(64 * 1024, int(target_mb * 1024 * 1024))
    if len(content) <= target_bytes:
        return content, suffix, mime_type

    try:
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            max_pixels = settings.multimodal_image_max_pixels
            if image.width * image.height > max_pixels:
                raise ValueError(f"图片像素过大，最多允许 {max_pixels:,} 像素")

            if image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            ):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")

            max_side = settings.multimodal_image_max_side
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            for _ in range(8):
                for quality in (90, 82, 74, 66):
                    output = io.BytesIO()
                    image.save(
                        output,
                        format="JPEG",
                        quality=quality,
                        optimize=True,
                        progressive=True,
                    )
                    optimized = output.getvalue()
                    if len(optimized) <= target_bytes:
                        return optimized, ".jpg", "image/jpeg"

                next_size = (
                    max(10, int(image.width * 0.8)),
                    max(10, int(image.height * 0.8)),
                )
                if next_size == image.size:
                    break
                image = image.resize(next_size, Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("图片文件损坏或无法解码") from error

    raise ValueError(f"图片自动压缩后仍超过 {target_mb:g} MB，请降低分辨率后重试")


def image_data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class MultimodalEmbeddingClient:
    """通过百炼 HTTP API 生成可直接比较的文本和图片向量。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.endpoint = settings.multimodal_embedding_base_url
        self.api_key = settings.require_multimodal_embedding_api_key()
        self.model = settings.multimodal_embedding_model
        self.dimension = settings.multimodal_embedding_dimension
        self.timeout = settings.multimodal_embedding_timeout_seconds
        self.instruct = settings.multimodal_embedding_instruct

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
