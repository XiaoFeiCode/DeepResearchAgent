import unittest
from unittest.mock import patch

from image_knowledge.embedding import (
    MultimodalEmbeddingClient,
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
