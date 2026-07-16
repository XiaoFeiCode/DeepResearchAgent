"""OmniResearch 自动评测命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from core.settings import PROJECT_ROOT, get_settings
from evaluation.dataset import load_cases, load_runs


def _project_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _select_cases(cases, selected_ids: list[str]):
    if not selected_ids:
        return cases
    selected = [case for case in cases if case.id in set(selected_ids)]
    missing = sorted(set(selected_ids) - {case.id for case in selected})
    if missing:
        raise ValueError(f"评测集中不存在这些用例: {', '.join(missing)}")
    return selected


def validate_command(args: argparse.Namespace) -> int:
    cases = load_cases(_project_path(args.dataset), include_disabled=args.include_disabled)
    print(f"评测集校验通过，共 {len(cases)} 条可用用例。")
    for case in cases:
        print(f"- {case.id}: {case.query[:80]}")
    return 0


def collect_command(args: argparse.Namespace) -> int:
    from evaluation.collector import collect_cases

    settings = get_settings()
    cases = load_cases(_project_path(args.dataset))
    cases = _select_cases(cases, args.case)
    output = (
        _project_path(args.output)
        if args.output
        else _project_path(settings.evaluation_output_dir)
        / f"run-{_timestamp()}"
        / "runs.jsonl"
    )
    asyncio.run(
        collect_cases(
            cases,
            user_id=args.user_id or settings.evaluation_user_id,
            output_path=output,
        )
    )
    print(f"Agent 运行记录已保存: {output}")
    print("下一步运行 RAGAS 评分：")
    print(
        "uv run --project evaluation python -m evaluation.cli score "
        f'--runs "{output}"'
    )
    return 0


def score_command(args: argparse.Namespace) -> int:
    from evaluation.code_metrics import score_code_metrics
    from evaluation.report import write_report

    settings = get_settings()
    runs_path = _project_path(args.runs)
    runs = load_runs(runs_path)
    scores = [score for run in runs for score in score_code_metrics(run)]

    if not args.code_only:
        from evaluation.ragas_metrics import RagasEvaluator

        evaluator = RagasEvaluator(settings)

        async def score_all():
            ragas_scores = []
            for index, run in enumerate(runs, 1):
                print(f"[{index}/{len(runs)}] RAGAS 评分: {run.case.id}")
                ragas_scores.extend(await evaluator.score_run(run))
            return ragas_scores

        scores.extend(asyncio.run(score_all()))

    output_dir = (
        _project_path(args.output_dir)
        if args.output_dir
        else runs_path.parent / "evaluation-results"
    )
    scores_path, summary_path, report_path = write_report(output_dir, runs, scores)
    print(f"指标明细: {scores_path}")
    print(f"聚合结果: {summary_path}")
    print(f"评测报告: {report_path}")

    if args.publish_phoenix or settings.evaluation_publish_to_phoenix:
        from evaluation.phoenix import publish_scores

        published = publish_scores(settings, scores)
        print(f"已向 Phoenix 回写 {published} 条 Span Annotation。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="OmniResearch 离线自动评测")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="只校验评测集，不调用模型")
    validate.add_argument("--dataset", default=settings.evaluation_dataset_path)
    validate.add_argument("--include-disabled", action="store_true")
    validate.set_defaults(handler=validate_command)

    collect = subparsers.add_parser("collect", help="运行 Agent 并采集执行记录")
    collect.add_argument("--dataset", default=settings.evaluation_dataset_path)
    collect.add_argument("--case", action="append", default=[], help="只运行指定用例 ID")
    collect.add_argument("--user-id")
    collect.add_argument("--output")
    collect.set_defaults(handler=collect_command)

    score = subparsers.add_parser("score", help="计算确定性指标和 RAGAS 指标")
    score.add_argument("--runs", required=True)
    score.add_argument("--output-dir")
    score.add_argument("--code-only", action="store_true", help="不调用 RAGAS 裁判模型")
    score.add_argument("--publish-phoenix", action="store_true")
    score.set_defaults(handler=score_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
