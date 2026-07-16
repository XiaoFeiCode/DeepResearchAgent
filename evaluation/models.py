"""评测用例、执行记录和评分结果的数据结构。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ExpectedToolCall(BaseModel):
    """期望调用的工具；args 为空时只比较工具名称。"""

    name: str = Field(min_length=1)
    args: dict[str, Any] | None = None


class EvaluationCase(BaseModel):
    """一条可重复执行的离线评测用例。"""

    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    query: str = Field(min_length=1)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    reference_goal: str | None = None
    reference_contexts: list[str] = Field(default_factory=list)
    expected_tools: list[ExpectedToolCall] = Field(default_factory=list)
    expected_subagents: list[str] = Field(default_factory=list)
    context_tools: list[str] = Field(default_factory=list)
    required_answer_terms: list[str] = Field(default_factory=list)
    forbidden_answer_terms: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("query", "reference_answer", "reference_goal", "notes")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class EvaluationRun(BaseModel):
    """Agent 执行一条评测用例后得到的完整记录。"""

    case: EvaluationCase
    thread_id: str
    user_id: str
    response: str
    status: Literal["success", "error"]
    started_at: datetime
    duration_ms: float = Field(ge=0)
    trace_id: str | None = None
    span_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    reported_tools: list[dict[str, Any]] = Field(default_factory=list)
    subagents: list[str] = Field(default_factory=list)
    retrieved_contexts: list[str] = Field(default_factory=list)


class MetricScore(BaseModel):
    """单个用例的一项评测指标。"""

    case_id: str
    metric: str
    score: float | None = None
    evaluator: Literal["code", "ragas"]
    reason: str = ""
    error: str | None = None
    span_id: str | None = None


class EvaluationSummary(BaseModel):
    """一次评测批次的聚合结果。"""

    generated_at: datetime
    run_count: int
    success_count: int
    average_duration_ms: float
    metric_averages: dict[str, float]
    scores: list[MetricScore]


__all__ = [
    "EvaluationCase",
    "EvaluationRun",
    "EvaluationSummary",
    "ExpectedToolCall",
    "MetricScore",
]
