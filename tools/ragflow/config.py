"""RAGFlow 客户端配置兼容入口。"""

from __future__ import annotations

from core.settings import PROJECT_ROOT, get_settings


def load_ragflow_env() -> tuple[str, str]:
    """读取并校验统一配置中的 RAGFlow 凭据。"""
    return get_settings().require_ragflow()


__all__ = ["PROJECT_ROOT", "load_ragflow_env"]
