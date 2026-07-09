"""Daytona sandbox lifecycle and workspace synchronization."""

from __future__ import annotations

import json
import os
import shlex
import threading
from pathlib import Path, PurePosixPath
from typing import Any

from daytona import Daytona, DaytonaConfig, Sandbox
from deepagents.backends.protocol import BackendProtocol
from dotenv import find_dotenv, load_dotenv
from langchain.tools import ToolRuntime
from langchain_daytona import DaytonaSandbox
from api.context import get_user_context
from skills.registry import (
    INSTALLED_SKILLS_ROOT,
    REMOTE_SKILLS_ROOT,
    SKILL_ASSIGNMENTS,
    SKILL_TARGETS,
    user_skill_storage_key,
)

load_dotenv(find_dotenv())

REMOTE_WORKSPACE = "/home/daytona/workspace"


class DaytonaSandboxManager:
    """Create one reusable Daytona sandbox for each conversation thread."""

    def __init__(self) -> None:
        self._client: Daytona | None = None
        self._sandboxes: dict[str, Sandbox] = {}
        self._backends: dict[str, DaytonaSandbox] = {}
        self._lock = threading.RLock()

    def _get_client(self) -> Daytona:
        if self._client is not None:
            return self._client

        api_key = os.getenv("DAYTONA_API_KEY")
        if not api_key:
            raise RuntimeError("DAYTONA_API_KEY is not configured")

        config_values: dict[str, str] = {"api_key": api_key}
        if api_url := os.getenv("DAYTONA_API_URL"):
            config_values["api_url"] = api_url
        if target := os.getenv("DAYTONA_TARGET"):
            config_values["target"] = target

        self._client = Daytona(DaytonaConfig(**config_values))
        return self._client

    def get_backend(self, thread_id: str) -> DaytonaSandbox:
        """Return the sandbox assigned to a thread, creating it on first use."""
        with self._lock:
            backend = self._backends.get(thread_id)
            if backend is not None:
                return backend

            sandbox = self._get_client().create()
            backend = DaytonaSandbox(
                sandbox=sandbox,
                timeout=int(os.getenv("DAYTONA_COMMAND_TIMEOUT_SECONDS", "1800")),
            )
            init_result = backend.execute(f"mkdir -p {REMOTE_WORKSPACE}")
            if init_result.exit_code != 0:
                self._get_client().delete(sandbox)
                raise RuntimeError(f"Failed to initialize Daytona workspace: {init_result.output}")

            self._upload_project_skills(
                backend,
                user_id=get_user_context() or "anonymous",
            )
            self._sandboxes[thread_id] = sandbox
            self._backends[thread_id] = backend
            return backend

    @staticmethod
    def _upload_skill_files(
        backend: DaytonaSandbox,
        uploads: list[tuple[Path, str]],
    ) -> None:
        """Upload prepared skill files while preserving their directory structure."""
        if not uploads:
            return

        destinations = [remote_path for _, remote_path in uploads]
        parent_dirs = sorted({str(PurePosixPath(path).parent) for path in destinations})
        mkdir_result = backend.execute(
            "mkdir -p " + " ".join(shlex.quote(path) for path in parent_dirs)
        )
        if mkdir_result.exit_code != 0:
            raise RuntimeError(f"Failed to prepare Daytona skill directories: {mkdir_result.output}")

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

    def _upload_project_skills(self, backend: DaytonaSandbox, user_id: str) -> None:
        """Copy built-in and user-installed skills into the remote backend."""
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
        """Sync one newly installed user skill into the active conversation sandbox."""
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
        """Resolve the current thread's backend for DeepAgents tools."""
        configurable = (runtime.config or {}).get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            raise RuntimeError("The Daytona backend requires configurable.thread_id")
        return self.get_backend(str(thread_id))

    def upload_workspace(self, thread_id: str, local_dir: Path) -> DaytonaSandbox:
        """Upload local session files before the agent starts working."""
        backend = self.get_backend(thread_id)
        files = [path for path in local_dir.rglob("*") if path.is_file()]
        if not files:
            return backend

        destinations = [
            f"{REMOTE_WORKSPACE}/{path.relative_to(local_dir).as_posix()}"
            for path in files
        ]
        parent_dirs = sorted({str(PurePosixPath(path).parent) for path in destinations})
        mkdir_command = "mkdir -p " + " ".join(shlex.quote(path) for path in parent_dirs)
        mkdir_result = backend.execute(mkdir_command)
        if mkdir_result.exit_code != 0:
            raise RuntimeError(f"Failed to prepare Daytona directories: {mkdir_result.output}")

        responses = backend.upload_files(
            [
                (remote_path, local_path.read_bytes())
                for local_path, remote_path in zip(files, destinations, strict=True)
            ]
        )
        errors = [response for response in responses if response.error]
        if errors:
            details = ", ".join(f"{item.path}: {item.error}" for item in errors)
            raise RuntimeError(f"Failed to upload files to Daytona: {details}")
        return backend

    def download_workspace(self, thread_id: str, local_dir: Path) -> None:
        """Download generated sandbox files into the local session directory."""
        with self._lock:
            backend = self._backends.get(thread_id)
        if backend is None:
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

        local_root = local_dir.resolve()
        for start in range(0, len(remote_paths), 100):
            responses = backend.download_files(remote_paths[start : start + 100])
            for response in responses:
                if response.error or response.content is None:
                    continue
                relative_path = PurePosixPath(response.path).relative_to(REMOTE_WORKSPACE)
                destination = (local_root / Path(*relative_path.parts)).resolve()
                if local_root not in destination.parents and destination != local_root:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(response.content)

    def close(self) -> None:
        """Delete managed sandboxes so a stopped API does not keep billing."""
        with self._lock:
            client = self._client
            sandboxes = list(self._sandboxes.values())
            self._sandboxes.clear()
            self._backends.clear()

        if client is None:
            return
        for sandbox in sandboxes:
            try:
                client.delete(sandbox)
            except Exception:
                # Keep shutdown progressing if a remote sandbox was removed manually.
                continue


daytona_sandbox_manager = DaytonaSandboxManager()
