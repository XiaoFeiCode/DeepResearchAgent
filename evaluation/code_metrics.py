"""无需裁判模型即可稳定复现的 Agent 路由和答案规则指标。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from evaluation.models import EvaluationRun, MetricScore

CONTROL_TOOL_NAMES = {"task", "write_todos", "read_todos"}


def _multiset_f1(expected: list[str], actual: list[str]) -> tuple[float, str]:
    if not expected:
        return 1.0, "未配置期望项"
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    matched = sum((expected_counts & actual_counts).values())
    precision = matched / len(actual) if actual else 0.0
    recall = matched / len(expected)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return f1, f"precision={precision:.3f}, recall={recall:.3f}"


def _args_match(expected: dict[str, Any] | None, actual: dict[str, Any]) -> bool:
    if expected is None:
        return True
    return all(actual.get(key) == value for key, value in expected.items())


def score_code_metrics(run: EvaluationRun) -> list[MetricScore]:
    """对执行成功、工具、子智能体和答案关键词进行确定性评分。"""
    scores = [
        MetricScore(
            case_id=run.case.id,
            metric="execution_success",
            score=1.0 if run.status == "success" else 0.0,
            evaluator="code",
            reason="Agent 正常返回" if run.status == "success" else run.response[:500],
            span_id=run.span_id,
        )
    ]

    if run.case.expected_tools:
        expected_names = [item.name for item in run.case.expected_tools]
        observed_calls = run.reported_tools or run.tool_calls
        business_calls = [
            item
            for item in observed_calls
            if str(item.get("name")) not in CONTROL_TOOL_NAMES
        ]
        actual_names = [str(item.get("name")) for item in business_calls]
        f1, reason = _multiset_f1(expected_names, actual_names)
        scores.append(
            MetricScore(
                case_id=run.case.id,
                metric="tool_call_f1_code",
                score=f1,
                evaluator="code",
                reason=f"{reason}; expected={expected_names}; actual={actual_names}",
                span_id=run.span_id,
            )
        )
        exact = len(expected_names) == len(actual_names) and all(
            expected.name == actual.get("name")
            and _args_match(expected.args, dict(actual.get("args") or {}))
            for expected, actual in zip(run.case.expected_tools, business_calls)
        )
        scores.append(
            MetricScore(
                case_id=run.case.id,
                metric="tool_call_sequence_accuracy_code",
                score=1.0 if exact else 0.0,
                evaluator="code",
                reason="严格比较工具顺序和已配置参数",
                span_id=run.span_id,
            )
        )

    if run.case.expected_subagents:
        f1, reason = _multiset_f1(run.case.expected_subagents, run.subagents)
        scores.append(
            MetricScore(
                case_id=run.case.id,
                metric="subagent_routing_f1",
                score=f1,
                evaluator="code",
                reason=(
                    f"{reason}; expected={run.case.expected_subagents}; "
                    f"actual={run.subagents}"
                ),
                span_id=run.span_id,
            )
        )

    if run.case.required_answer_terms:
        matched = [term for term in run.case.required_answer_terms if term in run.response]
        scores.append(
            MetricScore(
                case_id=run.case.id,
                metric="required_term_coverage",
                score=len(matched) / len(run.case.required_answer_terms),
                evaluator="code",
                reason=f"matched={matched}; expected={run.case.required_answer_terms}",
                span_id=run.span_id,
            )
        )

    if run.case.forbidden_answer_terms:
        found = [term for term in run.case.forbidden_answer_terms if term in run.response]
        scores.append(
            MetricScore(
                case_id=run.case.id,
                metric="forbidden_term_safety",
                score=0.0 if found else 1.0,
                evaluator="code",
                reason=f"命中的禁止内容: {found}" if found else "未命中禁止内容",
                span_id=run.span_id,
            )
        )
    return scores


__all__ = ["score_code_metrics"]
