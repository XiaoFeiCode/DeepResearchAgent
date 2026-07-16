"""基于 ContextVar 的请求级运行上下文。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_session_dir_ctx: ContextVar[str | None] = ContextVar("session_dir", default=None)
_thread_id_ctx: ContextVar[str | None] = ContextVar("thread_id", default=None)
_user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)
_result_metadata_ctx: ContextVar[dict[str, Any] | None] = ContextVar(
    "result_metadata",
    default=None,
)


def set_session_context(path: str) -> Token[str | None]:
    """绑定当前任务的会话工作目录。"""
    return _session_dir_ctx.set(path)


def get_session_context() -> str | None:
    """获取当前任务的会话工作目录。"""
    return _session_dir_ctx.get()


def set_thread_context(thread_id: str) -> Token[str | None]:
    """绑定当前任务的线程标识。"""
    return _thread_id_ctx.set(thread_id)


def get_thread_context() -> str | None:
    """获取当前任务的线程标识。"""
    return _thread_id_ctx.get()


def set_user_context(user_id: str) -> Token[str | None]:
    """绑定当前任务的登录用户。"""
    return _user_id_ctx.set(user_id)


def get_user_context() -> str | None:
    """获取当前任务的登录用户。"""
    return _user_id_ctx.get()


def set_result_metadata_context() -> Token[dict[str, Any] | None]:
    """为当前任务创建结构化结果容器。"""
    return _result_metadata_ctx.set({})


def add_result_images(images: list[dict[str, Any]]) -> None:
    """记录图片检索结果，供任务结束后持久化。"""
    metadata = _result_metadata_ctx.get()
    if metadata is None:
        return

    current = metadata.setdefault("images", [])
    existing_ids = {item.get("id") for item in current}
    for image in images:
        if image.get("id") not in existing_ids:
            current.append(dict(image))
            existing_ids.add(image.get("id"))


def get_result_metadata() -> dict[str, Any]:
    """返回当前任务结构化结果的浅拷贝。"""
    metadata = _result_metadata_ctx.get() or {}
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in metadata.items()
    }


def reset_request_context(
    session_token: Token[str | None],
    thread_token: Token[str | None] | None = None,
    user_token: Token[str | None] | None = None,
    result_metadata_token: Token[dict[str, Any] | None] | None = None,
) -> None:
    """恢复任务开始前的上下文，防止并发请求相互污染。"""
    _session_dir_ctx.reset(session_token)
    if thread_token is not None:
        _thread_id_ctx.reset(thread_token)
    if user_token is not None:
        _user_id_ctx.reset(user_token)
    if result_metadata_token is not None:
        _result_metadata_ctx.reset(result_metadata_token)
