import io
import os
import unittest
from unittest.mock import patch

from PIL import Image

from image_knowledge.embedding import (
    MultimodalEmbeddingClient,
    prepare_image_for_embedding,
    validate_image_bytes,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-image"


class FakeResponse:
    def __init__(self, vector):
        self.vector = vector

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "output": {
                "embeddings": [
                    {"index": 0, "embedding": self.vector, "type": "vl"}
                ]
            }
        }


class ImageKnowledgeTests(unittest.TestCase):
    def test_validates_supported_image_signature(self):
        suffix, mime_type = validate_image_bytes("sample.png", PNG_BYTES)
        self.assertEqual(suffix, ".png")
        self.assertEqual(mime_type, "image/png")

    def test_rejects_disguised_image(self):
        with self.assertRaisesRegex(ValueError, "扩展名不匹配"):
            validate_image_bytes("sample.png", b"plain text")

    def test_compresses_large_image_for_embedding(self):
        image = Image.effect_noise((1024, 1024), 120).convert("RGB")
        source = io.BytesIO()
        image.save(source, format="PNG")

        with patch.dict(
            os.environ,
            {
                "MULTIMODAL_IMAGE_MAX_MB": "5",
                "MULTIMODAL_EMBEDDING_IMAGE_MAX_MB": "0.05",
            },
        ):
            content, suffix, mime_type = prepare_image_for_embedding(
                "large.png",
                source.getvalue(),
            )

        self.assertEqual(suffix, ".jpg")
        self.assertEqual(mime_type, "image/jpeg")
        self.assertTrue(content.startswith(b"\xff\xd8\xff"))
        self.assertLessEqual(len(content), 64 * 1024)

    def test_rejects_upload_above_original_size_limit(self):
        oversized = b"\x89PNG\r\n\x1a\n" + (b"x" * 128 * 1024)
        with patch.dict(os.environ, {"MULTIMODAL_IMAGE_MAX_MB": "0.1"}):
            with self.assertRaisesRegex(ValueError, "超过 0.1 MB"):
                validate_image_bytes("oversized.png", oversized)

    @patch("image_knowledge.embedding.httpx.post")
    def test_generates_text_vector_with_dashscope_payload(self, mock_post):
        mock_post.return_value = FakeResponse([0.1, 0.2, 0.3, 0.4])
        client = MultimodalEmbeddingClient()
        client.api_key = "test-key"
        client.dimension = 4

        vector = client.embed_text("红色运动鞋")

        self.assertEqual(vector, [0.1, 0.2, 0.3, 0.4])
        request_json = mock_post.call_args.kwargs["json"]
        self.assertEqual(request_json["model"], "qwen3-vl-embedding")
        self.assertEqual(
            request_json["input"]["contents"],
            [{"text": "红色运动鞋"}],
        )
        self.assertEqual(request_json["parameters"]["dimension"], 4)


if __name__ == "__main__":
    unittest.main()
