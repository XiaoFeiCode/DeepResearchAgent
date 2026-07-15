import mimetypes
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from fastapi import UploadFile


class FileService:
    """管理会话上传文件和 Agent 输出文件。"""

    def __init__(self, project_root: Path) -> None:
        self.output_dir = project_root / "output"
        self.updated_dir = project_root / "updated"
        self.output_dir.mkdir(exist_ok=True)
        self.updated_dir.mkdir(exist_ok=True)

    def save_uploads(self, files: list[UploadFile], thread_id: str) -> list[dict]:
        target_dir = self._upload_session_dir(thread_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        saved_files: list[dict] = []
        for upload in files:
            filename = Path(upload.filename or "upload").name
            target = target_dir / filename
            with target.open("wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            saved_files.append(self._upload_payload(thread_id, target))
        return saved_files

    def describe_uploads(self, thread_id: str, filenames: list[str]) -> list[dict]:
        """Return trusted metadata for files already uploaded to one session."""
        target_dir = self._upload_session_dir(thread_id)
        attachments: list[dict] = []
        seen: set[str] = set()
        for filename in filenames:
            safe_name = Path(filename).name
            if safe_name != filename or safe_name in seen:
                continue
            file_path = (target_dir / safe_name).resolve()
            if not file_path.is_relative_to(target_dir.resolve()) or not file_path.is_file():
                raise FileNotFoundError(f"上传附件不存在: {safe_name}")
            attachments.append(self._upload_payload(thread_id, file_path))
            seen.add(safe_name)
        return attachments

    def resolve_upload(self, thread_id: str, filename: str) -> Path:
        """Resolve one uploaded attachment without allowing path traversal."""
        safe_name = Path(filename).name
        if safe_name != filename:
            raise ValueError("无效的附件名称")
        target_dir = self._upload_session_dir(thread_id)
        file_path = (target_dir / safe_name).resolve()
        if not file_path.is_relative_to(target_dir.resolve()) or not file_path.is_file():
            raise FileNotFoundError("附件不存在")
        return file_path

    def resolve_download(self, path: str) -> Path:
        file_path = self._resolve_output_path(path)
        if not file_path.is_file():
            raise FileNotFoundError("文件不存在")
        return file_path

    def list_files(self, path: str) -> list[dict]:
        directory = self._resolve_output_path(path)
        if not directory.is_dir():
            raise FileNotFoundError("目录不存在")

        files = []
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append(
                    {
                        "name": file_path.name,
                        "type": "file",
                        "path": str(file_path),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                )

        files.sort(key=lambda item: item.get("mtime", 0), reverse=True)
        return files

    def _resolve_output_path(self, path: str) -> Path:
        try:
            resolved = Path(path).resolve()
        except (OSError, RuntimeError, ValueError) as error:
            raise ValueError("无效的路径参数") from error

        if not resolved.is_relative_to(self.output_dir.resolve()):
            raise PermissionError("拒绝访问: 只能访问输出目录下的文件")
        return resolved

    def _upload_session_dir(self, thread_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", thread_id):
            raise ValueError("无效的会话 ID")
        return self.updated_dir / f"session_{thread_id}"

    @staticmethod
    def _upload_payload(thread_id: str, file_path: Path) -> dict:
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        return {
            "name": file_path.name,
            "content_type": content_type,
            "size": file_path.stat().st_size,
            "content_url": (
                f"/api/uploads/{quote(thread_id, safe='')}/"
                f"{quote(file_path.name, safe='')}"
            ),
        }
