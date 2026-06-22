import shutil
from pathlib import Path

from fastapi import UploadFile


class FileService:
    """管理会话上传文件和 Agent 输出文件。"""

    def __init__(self, project_root: Path) -> None:
        self.output_dir = project_root / "output"
        self.updated_dir = project_root / "updated"
        self.output_dir.mkdir(exist_ok=True)
        self.updated_dir.mkdir(exist_ok=True)

    def save_uploads(self, files: list[UploadFile], thread_id: str) -> list[str]:
        target_dir = self.updated_dir / f"session_{thread_id}"
        target_dir.mkdir(parents=True, exist_ok=True)

        saved_files: list[str] = []
        for upload in files:
            filename = Path(upload.filename or "upload").name
            with (target_dir / filename).open("wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            saved_files.append(filename)
        return saved_files

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
