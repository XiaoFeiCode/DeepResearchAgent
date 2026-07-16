"""Daytona 沙箱生命周期与工作区同步。"""

from __future__ import annotations

import hashlib
import json
import logging
import shlex
import shutil
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any

from api.context import get_thread_context, get_user_context
from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig, Sandbox
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import BackendProtocol
from langchain.tools import ToolRuntime
from langchain_daytona import DaytonaSandbox
from langgraph.config import get_config
from core.settings import get_settings
from skills.registry import (
    INSTALLED_SKILLS_ROOT,
    REMOTE_SKILLS_ROOT,
    SKILL_ASSIGNMENTS,
    SKILL_TARGETS,
    user_skill_storage_key,
)

logger = logging.getLogger(__name__)

REMOTE_WORKSPACE = "/home/daytona/workspace"
LOCAL_FALLBACK_ROOT = (
    Path(__file__).resolve().parent.parent / "runtime" / "fallback_sandboxes"
)


class DaytonaSandboxManager:
    """为每个活动会话任务管理独立后端。"""

    def __init__(self) -> None:
        self._client: Daytona | None = None
        self._sandboxes: dict[str, Sandbox] = {}
        self._backends: dict[str, BackendProtocol] = {}
        self._local_roots: dict[str, Path] = {}
        self._lock = threading.RLock()

    def _get_client(self) -> Daytona:
        if self._client is not None:
            return self._client

        settings = get_settings()
        api_key = settings.require_daytona_api_key()

        config_values: dict[str, str] = {"api_key": api_key}
        if api_url := settings.daytona_api_url:
            config_values["api_url"] = api_url
        if target := settings.daytona_target:
            config_values["target"] = target

        self._client = Daytona(DaytonaConfig(**config_values))
        return self._client

    def _create_daytona_backend(self, thread_id: str) -> DaytonaSandbox:
        """创建 Daytona 后端，并对临时远程故障进行重试。"""
        settings = get_settings()
        attempts = settings.daytona_create_retries
        retry_delay = settings.daytona_retry_delay_seconds
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            sandbox: Sandbox | None = None
            try:
                client = self._get_client()
                sandbox = client.create(
                    CreateSandboxFromSnapshotParams(
                        name=f"deep-agent-{thread_id[:12]}",
                        labels={
                            "project": "omniresearch",
                            "thread_id": thread_id,
                        },
                        auto_stop_interval=settings.daytona_auto_stop_minutes,
                        ephemeral=True,
                    )
                )
                backend = DaytonaSandbox(
                    sandbox=sandbox,
                    timeout=settings.daytona_command_timeout_seconds,
                )
                init_result = backend.execute(f"mkdir -p {REMOTE_WORKSPACE}")
                if init_result.exit_code != 0:
                    raise RuntimeError(
                        f"Failed to initialize Daytona workspace: {init_result.output}"
                    )

                self._upload_project_skills(
                    backend,
                    user_id=get_user_context() or "anonymous",
                )
                self._sandboxes[thread_id] = sandbox
                return backend
            except Exception as error:
                last_error = error
                if sandbox is not None:
                    try:
                        self._get_client().delete(sandbox)
                    except Exception:
                        pass

                    # 丢失的 HTTP 会话不能影响后续重试。
                self._client = None
                missing_key = "DAYTONA_API_KEY is not configured" in str(error)
                if attempt < attempts and not missing_key:
                    logger.warning(
                        "Daytona 沙箱创建失败（%s/%s）：%s，准备重试",
                        attempt,
                        attempts,
                        error,
                    )
                    time.sleep(retry_delay * attempt)
                else:
                    break

        assert last_error is not None
        raise last_error

    def _create_local_fallback(self, thread_id: str) -> FilesystemBackend:
        """Daytona 不可用时创建仅支持文件操作的后端。"""
        thread_key = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:24]
        local_root = (LOCAL_FALLBACK_ROOT / thread_key).resolve()
        local_root.mkdir(parents=True, exist_ok=True)
        backend = FilesystemBackend(root_dir=local_root, virtual_mode=True)
        self._upload_project_skills(
            backend,
            user_id=get_user_context() or "anonymous",
        )
        self._local_roots[thread_id] = local_root
        return backend

    def get_backend(self, thread_id: str) -> BackendProtocol:
        """默认返回 Daytona，服务故障时返回受限文件后端。"""
        with self._lock:
            backend = self._backends.get(thread_id)
            if backend is not None:
                return backend

            try:
                backend = self._create_daytona_backend(thread_id)
            except Exception as error:
                logger.warning(
                    "Daytona 不可用，线程 %s 降级为受限本地文件后端：%s",
                    thread_id,
                    error,
                )
                backend = self._create_local_fallback(thread_id)

            self._backends[thread_id] = backend
            return backend

    @staticmethod
    def _upload_skill_files(
        backend: BackendProtocol,
        uploads: list[tuple[Path, str]],
    ) -> None:
        """上传准备好的 Skill 文件，并保留原目录结构。"""
        if not uploads:
            return

        if isinstance(backend, DaytonaSandbox):
            destinations = [remote_path for _, remote_path in uploads]
            parent_dirs = sorted(
                {str(PurePosixPath(path).parent) for path in destinations}
            )
            mkdir_result = backend.execute(
                "mkdir -p " + " ".join(shlex.quote(path) for path in parent_dirs)
            )
            if mkdir_result.exit_code != 0:
                raise RuntimeError(
                    f"Failed to prepare Daytona skill directories: {mkdir_result.output}"
                )

        responses = backend.upload_files(
            [
                (remote_path, local_path.read_bytes())
                for local_path, remote_path in uploads
            ]
        )
        errors = [response for response in responses if response.error]
        if errors:
            details = ", ".join(f"{item.path}: {item.error}" for item in errors)
            raise RuntimeError(f"Failed to upload skill files: {details}")

    def _upload_project_skills(self, backend: BackendProtocol, user_id: str) -> None:
        """把内置和用户安装的 Skill 复制到选定后端。"""
        local_root = Path(__file__).resolve().parent.parent / "skills"
        uploads: list[tuple[Path, str]] = []
        for group, skill_names in SKILL_ASSIGNMENTS.items():
            for skill_name in skill_names:
                skill_dir = local_root / skill_name
                for path in skill_dir.rglob("*"):
                    if not path.is_file():
                        continue
                    relative_path = path.relative_to(skill_dir).as_posix()
                    remote_path = (
                        f"{REMOTE_SKILLS_ROOT}/{group}/{skill_name}/{relative_path}"
                    )
                    uploads.append((path, remote_path))

        user_root = INSTALLED_SKILLS_ROOT / user_skill_storage_key(user_id)
        for target_agent in SKILL_TARGETS:
            target_root = user_root / target_agent
            if not target_root.exists():
                continue
            for skill_dir in target_root.iterdir():
                if not skill_dir.is_dir():
                    continue
                for path in skill_dir.rglob("*"):
                    if path.is_file():
                        relative_path = path.relative_to(skill_dir).as_posix()
                        uploads.append(
                            (
                                path,
                                f"{REMOTE_SKILLS_ROOT}/{target_agent}/"
                                f"{skill_dir.name}/{relative_path}",
                            )
                        )

        self._upload_skill_files(backend, uploads)

    def upload_user_skill(
        self,
        *,
        thread_id: str,
        user_id: str,
        target_agent: str,
        skill_name: str,
        local_directory: str,
    ) -> None:
        """把新安装的用户 Skill 同步到活动后端。"""
        if target_agent not in SKILL_TARGETS:
            raise ValueError(f"Unknown skill target: {target_agent}")

        expected = (
            INSTALLED_SKILLS_ROOT
            / user_skill_storage_key(user_id)
            / target_agent
            / skill_name
        ).resolve()
        local_root = Path(local_directory).resolve()
        if local_root != expected or not local_root.is_dir():
            raise ValueError("Installed skill path is outside the expected user directory")

        uploads = [
            (
                path,
                f"{REMOTE_SKILLS_ROOT}/{target_agent}/{skill_name}/"
                f"{path.relative_to(local_root).as_posix()}",
            )
            for path in local_root.rglob("*")
            if path.is_file()
        ]
        self._upload_skill_files(self.get_backend(thread_id), uploads)

    def backend_for_runtime(self, runtime: ToolRuntime[Any, Any]) -> BackendProtocol:
        """为 DeepAgents 工具解析当前线程对应的后端。"""
        config = getattr(runtime, "config", None)
        if config is None:
            config = get_config()
        configurable = (config or {}).get("configurable", {})
        thread_id = configurable.get("thread_id") or get_thread_context()
        if not thread_id:
            raise RuntimeError("The Daytona backend requires configurable.thread_id")
        return self.get_backend(str(thread_id))

    def upload_workspace(self, thread_id: str, local_dir: Path) -> BackendProtocol:
        """在智能体开始工作前上传本地会话文件。"""
        backend = self.get_backend(thread_id)
        files = [path for path in local_dir.rglob("*") if path.is_file()]
        if not files:
            return backend

        destinations = [
            f"{REMOTE_WORKSPACE}/{path.relative_to(local_dir).as_posix()}"
            for path in files
        ]
        if isinstance(backend, DaytonaSandbox):
            parent_dirs = sorted(
                {str(PurePosixPath(path).parent) for path in destinations}
            )
            mkdir_command = "mkdir -p " + " ".join(
                shlex.quote(path) for path in parent_dirs
            )
            mkdir_result = backend.execute(mkdir_command)
            if mkdir_result.exit_code != 0:
                raise RuntimeError(
                    f"Failed to prepare Daytona directories: {mkdir_result.output}"
                )

        responses = backend.upload_files(
            [
                (remote_path, local_path.read_bytes())
                for local_path, remote_path in zip(files, destinations, strict=True)
            ]
        )
        errors = [response for response in responses if response.error]
        if errors:
            details = ", ".join(f"{item.path}: {item.error}" for item in errors)
            raise RuntimeError(f"Failed to upload workspace files: {details}")
        return backend

    def download_workspace(self, thread_id: str, local_dir: Path) -> None:
        """把后端生成的文件下载到本地会话目录。"""
        with self._lock:
            backend = self._backends.get(thread_id)
            local_root = self._local_roots.get(thread_id)
        if backend is None:
            return

        if local_root is not None:
            workspace_root = local_root / REMOTE_WORKSPACE.lstrip("/")
            if not workspace_root.exists():
                return
            destination_root = local_dir.resolve()
            for source in workspace_root.rglob("*"):
                if not source.is_file():
                    continue
                destination = (
                    destination_root / source.relative_to(workspace_root)
                ).resolve()
                if destination_root not in destination.parents:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            return

        if not isinstance(backend, DaytonaSandbox):
            return

        list_command = (
            "python3 - <<'PY'\n"
            "import json\n"
            "from pathlib import Path\n"
            f"root = Path({REMOTE_WORKSPACE!r})\n"
            "for path in root.rglob('*'):\n"
            "    if path.is_file():\n"
            "        print(json.dumps(str(path)))\n"
            "PY"
        )
        result = backend.execute(list_command)
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to list Daytona workspace: {result.output}")

        remote_paths: list[str] = []
        for line in result.output.splitlines():
            try:
                remote_paths.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        local_root_path = local_dir.resolve()
        for start in range(0, len(remote_paths), 100):
            responses = backend.download_files(remote_paths[start : start + 100])
            for response in responses:
                if response.error or response.content is None:
                    continue
                relative_path = PurePosixPath(response.path).relative_to(REMOTE_WORKSPACE)
                destination = (local_root_path / Path(*relative_path.parts)).resolve()
                if (
                    local_root_path not in destination.parents
                    and destination != local_root_path
                ):
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(response.content)

    def release(self, thread_id: str) -> None:
        """文件同步到本地后删除线程后端。"""
        with self._lock:
            sandbox = self._sandboxes.pop(thread_id, None)
            self._backends.pop(thread_id, None)
            local_root = self._local_roots.pop(thread_id, None)
            client = self._client

        if local_root is not None:
            shutil.rmtree(local_root, ignore_errors=True)
        if sandbox is not None and client is not None:
            client.delete(sandbox)

    def close(self) -> None:
        """删除受管后端，避免 API 停止后继续占用资源。"""
        with self._lock:
            client = self._client
            sandboxes = list(self._sandboxes.values())
            local_roots = list(self._local_roots.values())
            self._sandboxes.clear()
            self._backends.clear()
            self._local_roots.clear()

        for local_root in local_roots:
            shutil.rmtree(local_root, ignore_errors=True)
        if client is not None:
            for sandbox in sandboxes:
                try:
                    client.delete(sandbox)
                except Exception:
                    # 远程沙箱被手动删除时仍需继续完成关闭流程。
                    continue


daytona_sandbox_manager = DaytonaSandboxManager()
