"""聚合评测分数并生成便于审查的 JSON 与 Markdown 报告。"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from evaluation.dataset import write_jsonl
from evaluation.models import EvaluationRun, EvaluationSummary, MetricScore


def build_summary(
    runs: list[EvaluationRun],
    scores: list[MetricScore],
) -> EvaluationSummary:
    grouped: dict[str, list[float]] = defaultdict(list)
    for score in scores:
        if score.score is not None:
            grouped[score.metric].append(score.score)
    metric_averages = {
        metric: sum(values) / len(values)
        for metric, values in sorted(grouped.items())
        if values
    }
    return EvaluationSummary(
        generated_at=datetime.now().astimezone(),
        run_count=len(runs),
        success_count=sum(run.status == "success" for run in runs),
        average_duration_ms=(
            sum(run.duration_ms for run in runs) / len(runs) if runs else 0.0
        ),
        metric_averages=metric_averages,
        scores=scores,
    )


def write_report(
    output_dir: Path,
    runs: list[EvaluationRun],
    scores: list[MetricScore],
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(runs, scores)
    scores_path = write_jsonl(
        output_dir / "scores.jsonl",
        [score.model_dump(mode="json") for score in scores],
    )
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path = output_dir / "report.md"
    report_path.write_text(_render_markdown(summary, runs), encoding="utf-8")
    return scores_path, summary_path, report_path


def _render_markdown(summary: EvaluationSummary, runs: list[EvaluationRun]) -> str:
    lines = [
        "# OmniResearch 自动评测报告",
        "",
        f"- 生成时间：{summary.generated_at.isoformat()}",
        f"- 用例数量：{summary.run_count}",
        f"- 执行成功：{summary.success_count}/{summary.run_count}",
        f"- 平均耗时：{summary.average_duration_ms:.0f} ms",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 平均分 |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {metric} | {value:.3f} |"
        for metric, value in summary.metric_averages.items()
    )
    lines.extend(
        [
            "",
            "## 用例执行",
            "",
            "| 用例 | 状态 | 工具数 | 子智能体 | 耗时 |",
            "| --- | --- | ---: | --- | ---: |",
        ]
    )
    for run in runs:
        subagents = "、".join(run.subagents) or "-"
        lines.append(
            f"| {run.case.id} | {run.status} | "
            f"{len(run.reported_tools or run.tool_calls)} | "
            f"{subagents} | {run.duration_ms:.0f} ms |"
        )

    failed_scores = [
        score
        for score in summary.scores
        if score.error or (score.score is not None and score.score < 0.6)
    ]
    lines.extend(["", "## Bad Case", ""])
    if not failed_scores:
        lines.append("当前没有低于 0.6 或执行失败的指标。")
    else:
        for score in failed_scores:
            value = "ERROR" if score.score is None else f"{score.score:.3f}"
            detail = score.error or score.reason or "无说明"
            lines.append(
                f"- `{score.case_id}` / `{score.metric}`：{value}，{detail}"
            )
    lines.append("")
    return "\n".join(lines)


__all__ = ["build_summary", "write_report"]
