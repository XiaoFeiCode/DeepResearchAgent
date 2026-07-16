"""会话工作区路径解析与边界校验。"""

from __future__ import annotations

import os
from pathlib import Path

_VIRTUAL_PREFIXES = (
    "/home/daytona/workspace",
    "/workspace",
    "/mnt/data",
    "/home/user",
)


def _strip_virtual_prefix(path_text: str) -> tuple[str, bool]:
    """移除 Agent 运行环境中的虚拟工作区前缀。"""
    normalized = path_text.replace("\\", "/")
    for prefix in _VIRTUAL_PREFIXES:
        if normalized == prefix:
            return "", True
        if normalized.startswith(f"{prefix}/"):
            return normalized[len(prefix):].lstrip("/"), True
    return normalized, False


def _relative_session_path(path: Path, session_name: str) -> Path:
    """去掉模型可能重复生成的 output 或会话目录前缀。"""
    parts = list(path.parts)
    if session_name in parts:
        return Path(*parts[parts.index(session_name) + 1:])
    if parts and parts[0] == "output":
        return Path(*parts[1:])
    return path


def resolve_path(filename: str, session_dir: str | None = None) -> str:
    """解析工具文件路径，并在存在会话目录时阻止越界访问。"""
    normalized, from_virtual_workspace = _strip_virtual_prefix(filename)
    raw_path = Path(normalized)

    if not session_dir:
        return str(raw_path.resolve())

    session_path = Path(session_dir).resolve()
    is_windows_root_path = os.name == "nt" and normalized.startswith("/") and not raw_path.drive

    if from_virtual_workspace or is_windows_root_path or not raw_path.is_absolute():
        relative_path = _relative_session_path(raw_path, session_path.name)
        candidate = (session_path / relative_path).resolve()
    else:
        candidate = raw_path.resolve()

    if not candidate.is_relative_to(session_path):
        raise ValueError(f"文件路径超出当前会话目录：{filename}")
    return str(candidate)
