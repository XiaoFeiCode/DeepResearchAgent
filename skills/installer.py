"""Download, validate, and persist user-provided DeepAgents skills."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlparse

import requests
import yaml

from skills.registry import (
    INSTALLED_SKILLS_ROOT,
    SKILL_ASSIGNMENTS,
    SKILL_TARGETS,
    user_skill_storage_key,
)

MAX_SKILL_FILES = 50
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
SAFE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
BLOCKED_EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".js",
    ".msi",
    ".ps1",
    ".py",
    ".sh",
}


class SkillInstallError(ValueError):
    """Raised when a remote skill fails validation or installation."""


def _request_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DeepAgent-Studio-Skill-Installer",
    }
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(url: str, *, json_response: bool = False) -> Any:
    response = requests.get(
        url,
        headers=_request_headers(),
        timeout=20,
        allow_redirects=True,
    )
    response.raise_for_status()
    final_host = (urlparse(response.url).hostname or "").lower()
    if final_host not in {"api.github.com", "github.com", "raw.githubusercontent.com"}:
        raise SkillInstallError(f"下载被重定向到不允许的主机: {final_host}")
    return response.json() if json_response else response.content


def _github_contents(owner: str, repo: str, ref: str, path: str) -> dict[PurePosixPath, bytes]:
    files: dict[PurePosixPath, bytes] = {}
    total_bytes = 0

    def visit(current_path: str) -> None:
        nonlocal total_bytes
        encoded_path = quote(current_path.strip("/"), safe="/")
        endpoint = f"https://api.github.com/repos/{owner}/{repo}/contents"
        if encoded_path:
            endpoint += f"/{encoded_path}"
        payload = _get(f"{endpoint}?ref={quote(ref, safe='')}", json_response=True)
        entries = payload if isinstance(payload, list) else [payload]

        for entry in entries:
            entry_type = entry.get("type")
            entry_path = str(entry.get("path", ""))
            if entry_type == "dir":
                visit(entry_path)
                continue
            if entry_type != "file":
                continue
            if len(files) >= MAX_SKILL_FILES:
                raise SkillInstallError(f"Skill 文件数量不能超过 {MAX_SKILL_FILES}")

            size = int(entry.get("size") or 0)
            if size > MAX_FILE_BYTES:
                raise SkillInstallError(f"单个文件不能超过 {MAX_FILE_BYTES // 1024} KB: {entry_path}")
            content = _get(entry["download_url"])
            if len(content) > MAX_FILE_BYTES:
                raise SkillInstallError(f"单个文件不能超过 {MAX_FILE_BYTES // 1024} KB: {entry_path}")
            total_bytes += len(content)
            if total_bytes > MAX_TOTAL_BYTES:
                raise SkillInstallError(f"Skill 总大小不能超过 {MAX_TOTAL_BYTES // 1024 // 1024} MB")

            relative = PurePosixPath(entry_path).relative_to(PurePosixPath(path or "."))
            files[relative] = content

    visit(path)
    return files


def download_skill(skill_url: str) -> dict[PurePosixPath, bytes]:
    """Download one skill directory from an approved GitHub URL."""
    parsed = urlparse(skill_url.strip())
    if parsed.scheme != "https":
        raise SkillInstallError("Skill 地址必须使用 HTTPS")

    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]

    if host == "raw.githubusercontent.com":
        if len(parts) < 5 or parts[-1] != "SKILL.md":
            raise SkillInstallError("raw.githubusercontent.com 地址必须指向 SKILL.md")
        return {PurePosixPath("SKILL.md"): _get(skill_url)}

    if host != "github.com" or len(parts) < 2:
        raise SkillInstallError("当前只允许 github.com 或 raw.githubusercontent.com Skill 地址")

    owner, repo = parts[0], parts[1].removesuffix(".git")
    if len(parts) == 2:
        repository = _get(
            f"https://api.github.com/repos/{owner}/{repo}",
            json_response=True,
        )
        return _github_contents(owner, repo, repository["default_branch"], "")

    kind = parts[2]
    if kind not in {"tree", "blob"} or len(parts) < 5:
        raise SkillInstallError("请提供 GitHub 仓库、Skill 文件夹或 SKILL.md 文件地址")

    ref = parts[3]
    source_path = "/".join(parts[4:])
    if kind == "blob":
        if not source_path.endswith("/SKILL.md") and source_path != "SKILL.md":
            raise SkillInstallError("GitHub blob 地址必须指向 SKILL.md")
        source_path = str(PurePosixPath(source_path).parent)
        if source_path == ".":
            source_path = ""
    return _github_contents(owner, repo, ref, source_path)


def _parse_metadata(files: dict[PurePosixPath, bytes]) -> dict[str, Any]:
    skill_file = files.get(PurePosixPath("SKILL.md"))
    if skill_file is None:
        raise SkillInstallError("Skill 根目录中缺少 SKILL.md")
    try:
        content = skill_file.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillInstallError("SKILL.md 必须使用 UTF-8 编码") from exc
    if not content.startswith("---"):
        raise SkillInstallError("SKILL.md 缺少 YAML frontmatter")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise SkillInstallError("SKILL.md frontmatter 格式不完整")
    metadata = yaml.safe_load(parts[1]) or {}
    if not isinstance(metadata, dict):
        raise SkillInstallError("SKILL.md frontmatter 必须是对象")

    name = str(metadata.get("name", "")).strip()
    description = str(metadata.get("description", "")).strip()
    if not SAFE_NAME_PATTERN.fullmatch(name):
        raise SkillInstallError("Skill name 只能包含小写字母、数字和连字符，最长 64 字符")
    if not description:
        raise SkillInstallError("SKILL.md frontmatter 缺少 description")
    return {"name": name, "description": description}


def _validate_files(files: dict[PurePosixPath, bytes]) -> None:
    allow_executable = os.getenv("SKILL_ALLOW_EXECUTABLE_FILES", "false").lower() == "true"
    for relative_path in files:
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise SkillInstallError(f"Skill 包含不安全路径: {relative_path}")
        if not allow_executable and relative_path.suffix.lower() in BLOCKED_EXECUTABLE_SUFFIXES:
            raise SkillInstallError(
                f"Skill 包含默认禁止的可执行脚本: {relative_path}；"
                "可信环境可设置 SKILL_ALLOW_EXECUTABLE_FILES=true"
            )


def installed_skill_directory(user_id: str, target_agent: str, skill_name: str) -> Path:
    if target_agent not in SKILL_TARGETS:
        raise SkillInstallError(f"未知目标智能体: {target_agent}")
    return INSTALLED_SKILLS_ROOT / user_skill_storage_key(user_id) / target_agent / skill_name


def install_skill(
    *,
    skill_url: str,
    target_agent: str,
    user_id: str,
    replace: bool = False,
) -> dict[str, Any]:
    """Install a validated skill into one user's target-agent namespace."""
    if target_agent not in SKILL_TARGETS:
        allowed = ", ".join(SKILL_TARGETS)
        raise SkillInstallError(f"target_agent 必须是: {allowed}")

    files = download_skill(skill_url)
    _validate_files(files)
    metadata = _parse_metadata(files)
    skill_name = metadata["name"]

    built_in_names = {name for names in SKILL_ASSIGNMENTS.values() for name in names}
    if skill_name in built_in_names:
        raise SkillInstallError(f"不能覆盖项目内置 Skill: {skill_name}")

    destination = installed_skill_directory(user_id, target_agent, skill_name)
    if destination.exists() and not replace:
        raise SkillInstallError(f"Skill 已安装: {skill_name}；如需更新请设置 replace=true")

    staging = destination.parent / f".{skill_name}-{uuid.uuid4().hex}.tmp"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for relative_path, content in files.items():
            output_path = staging.joinpath(*relative_path.parts)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(content)
        if destination.exists():
            shutil.rmtree(destination)
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return {
        "name": skill_name,
        "description": metadata["description"],
        "target_agent": target_agent,
        "source_url": skill_url,
        "file_count": len(files),
        "directory": str(destination),
    }


def list_installed_skills(user_id: str) -> list[dict[str, str]]:
    """List skills assigned to this user, grouped by target agent."""
    user_root = INSTALLED_SKILLS_ROOT / user_skill_storage_key(user_id)
    if not user_root.exists():
        return []

    installed: list[dict[str, str]] = []
    for target_dir in sorted(path for path in user_root.iterdir() if path.is_dir()):
        for skill_dir in sorted(path for path in target_dir.iterdir() if path.is_dir()):
            installed.append(
                {
                    "name": skill_dir.name,
                    "target_agent": target_dir.name,
                }
            )
    return installed
