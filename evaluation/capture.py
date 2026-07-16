"""按请求采集 Agent 的工具调用、子智能体委派和工具返回值。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator


def _json_safe(value: Any) -> Any:
    """把消息内容转换为可写入 JSONL 的普通数据。"""
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


@dataclass
class CapturedToolCall:
    """一次真实的模型工具调用以及对应返回值。"""

    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    output: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "args": _json_safe(self.args),
            "output": _json_safe(self.output),
        }


@dataclass
class ExecutionCapture:
    """单次 Agent 运行的轻量执行记录。"""

    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[CapturedToolCall] = field(default_factory=list)
    _tool_call_indexes: dict[str, int] = field(default_factory=dict)
    _seen_messages: set[str] = field(default_factory=set)

    def record_monitor_payload(self, payload: dict[str, Any]) -> None:
        self.events.append(_json_safe(dict(payload)))

    def record_messages(self, messages: list[Any]) -> None:
        """从 LangGraph 状态消息中提取工具调用和工具结果，并按消息 ID 去重。"""
        for message in messages:
            message_key = self._message_key(message)
            if message_key in self._seen_messages:
                continue
            self._seen_messages.add(message_key)

            for tool_call in getattr(message, "tool_calls", None) or []:
                call_id = str(tool_call.get("id") or f"call-{len(self.tool_calls) + 1}")
                if call_id in self._tool_call_indexes:
                    continue
                self._tool_call_indexes[call_id] = len(self.tool_calls)
                self.tool_calls.append(
                    CapturedToolCall(
                        id=call_id,
                        name=str(tool_call.get("name") or "unknown"),
                        args=dict(tool_call.get("args") or {}),
                    )
                )

            tool_call_id = getattr(message, "tool_call_id", None)
            if tool_call_id:
                self._record_tool_output(
                    str(tool_call_id),
                    getattr(message, "name", None),
                    getattr(message, "content", None),
                )

    def subagents(self) -> list[str]:
        names: list[str] = []
        for event in self.events:
            if event.get("event") != "assistant_call":
                continue
            name = str(event.get("data", {}).get("assistant_name") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def reported_tools(self) -> list[dict[str, Any]]:
        """返回 ToolMonitor 看到的真实工具入口，包含子智能体内部调用。"""
        tools: list[dict[str, Any]] = []
        for index, event in enumerate(self.events, 1):
            if event.get("event") != "tool_start":
                continue
            data = event.get("data", {})
            tools.append(
                {
                    "id": f"reported-{index}",
                    "name": str(data.get("tool_key") or data.get("tool_name") or "unknown"),
                    "display_name": str(data.get("tool_name") or ""),
                    "args": _json_safe(dict(data.get("args") or {})),
                    "output": None,
                }
            )
        return tools

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": list(self.events),
            "tool_calls": [item.to_dict() for item in self.tool_calls],
            "reported_tools": self.reported_tools(),
            "subagents": self.subagents(),
        }

    def _record_tool_output(self, call_id: str, name: str | None, output: Any) -> None:
        index = self._tool_call_indexes.get(call_id)
        if index is None:
            self._tool_call_indexes[call_id] = len(self.tool_calls)
            self.tool_calls.append(
                CapturedToolCall(
                    id=call_id,
                    name=str(name or "unknown"),
                    output=output,
                )
            )
            return
        self.tool_calls[index].output = output

    @staticmethod
    def _message_key(message: Any) -> str:
        message_id = getattr(message, "id", None)
        if message_id:
            return str(message_id)
        payload = {
            "type": type(message).__name__,
            "tool_call_id": getattr(message, "tool_call_id", None),
            "tool_calls": getattr(message, "tool_calls", None),
            "content": _json_safe(getattr(message, "content", None)),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


_capture_context: ContextVar[ExecutionCapture | None] = ContextVar(
    "evaluation_execution_capture",
    default=None,
)


@contextmanager
def capture_execution() -> Iterator[ExecutionCapture]:
    """只在离线评测期间开启采集，普通请求不会保存额外消息。"""
    capture = ExecutionCapture()
    token: Token[ExecutionCapture | None] = _capture_context.set(capture)
    try:
        yield capture
    finally:
        _capture_context.reset(token)


def record_monitor_payload(payload: dict[str, Any]) -> None:
    capture = _capture_context.get()
    if capture is not None:
        capture.record_monitor_payload(payload)


def record_stream_messages(messages: list[Any]) -> None:
    capture = _capture_context.get()
    if capture is not None:
        capture.record_messages(messages)


__all__ = [
    "ExecutionCapture",
    "capture_execution",
    "record_monitor_payload",
    "record_stream_messages",
]
