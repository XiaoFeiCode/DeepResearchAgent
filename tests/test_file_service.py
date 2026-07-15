import io
import tempfile
import unittest
from pathlib import Path

from fastapi import UploadFile

from api.services.file_service import FileService


class FileServiceTests(unittest.TestCase):
    def test_saves_and_describes_chat_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FileService(Path(directory))
            upload = UploadFile(
                filename="截图.png",
                file=io.BytesIO(b"image-content"),
            )

            saved = service.save_uploads([upload], "thread-1")
            described = service.describe_uploads("thread-1", ["截图.png"])

            self.assertEqual(saved, described)
            self.assertEqual(saved[0]["content_type"], "image/png")
            self.assertEqual(saved[0]["size"], 13)
            self.assertIn("/api/uploads/thread-1/", saved[0]["content_url"])
            self.assertEqual(
                service.resolve_upload("thread-1", "截图.png").read_bytes(),
                b"image-content",
            )

    def test_rejects_upload_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FileService(Path(directory))
            with self.assertRaisesRegex(ValueError, "会话 ID"):
                service.describe_uploads("../outside", ["image.png"])
            with self.assertRaisesRegex(ValueError, "附件名称"):
                service.resolve_upload("thread-1", "../image.png")


if __name__ == "__main__":
    unittest.main()
