import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import AIMessage

from tools.multimodal.image import (
    _build_data_url,
    _resolve_image_path,
    analyze_image_file,
)


PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"test-image-data"


class FakeVisionModel:
    def __init__(self):
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content="图片中显示错误代码 E1。")


class ImageAnalysisTests(unittest.IsolatedAsyncioTestCase):
    def test_resolves_daytona_path_inside_current_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            image_path = session_dir / "panel.png"
            image_path.write_bytes(PNG_HEADER)

            resolved = _resolve_image_path(
                "/home/daytona/workspace/panel.png",
                str(session_dir),
            )

            self.assertEqual(resolved, image_path.resolve())

    def test_rejects_paths_outside_current_session(self):
        with tempfile.TemporaryDirectory() as session_temp, tempfile.TemporaryDirectory() as other_temp:
            image_path = Path(other_temp) / "outside.png"
            image_path.write_bytes(PNG_HEADER)

            with self.assertRaises(PermissionError):
                _resolve_image_path(str(image_path), session_temp)

    def test_rejects_fake_image_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fake.png"
            image_path.write_text("not an image", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "扩展名不匹配"):
                _resolve_image_path("fake.png", temp_dir)

    async def test_sends_inline_image_to_vision_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "panel.png"
            image_path.write_bytes(PNG_HEADER)
            model = FakeVisionModel()

            result = await analyze_image_file(
                "panel.png",
                "识别错误代码",
                model=model,
                session_dir=temp_dir,
            )

            self.assertEqual(result, "图片中显示错误代码 E1。")
            content = model.messages[0].content
            self.assertEqual(content[0]["text"], "识别错误代码")
            self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
            self.assertEqual(
                _build_data_url(image_path),
                content[1]["image_url"]["url"],
            )


if __name__ == "__main__":
    unittest.main()
