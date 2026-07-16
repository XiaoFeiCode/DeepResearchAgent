"""JSONL 评测集的读取与校验。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from evaluation.models import EvaluationCase, EvaluationRun


def load_cases(path: Path, *, include_disabled: bool = False) -> list[EvaluationCase]:
    """逐行读取评测用例，错误信息保留具体文件和行号。"""
    if not path.is_file():
        raise FileNotFoundError(f"评测集不存在: {path}")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = EvaluationCase.model_validate_json(line)
        except (ValidationError, ValueError) as error:
            raise ValueError(f"{path}:{line_number} 评测用例无效: {error}") from error
        if case.id in seen_ids:
            raise ValueError(f"{path}:{line_number} 存在重复用例 ID: {case.id}")
        seen_ids.add(case.id)
        if include_disabled or case.enabled:
            cases.append(case)

    if not cases:
        raise ValueError(f"评测集中没有可执行用例: {path}")
    return cases


def load_runs(path: Path) -> list[EvaluationRun]:
    """读取已经采集的 Agent 运行记录。"""
    if not path.is_file():
        raise FileNotFoundError(f"运行记录不存在: {path}")
    runs: list[EvaluationRun] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            runs.append(EvaluationRun.model_validate_json(raw_line))
        except (ValidationError, ValueError) as error:
            raise ValueError(f"{path}:{line_number} 运行记录无效: {error}") from error
    return runs


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    """以 UTF-8 JSONL 保存中间结果，便于复跑评分而不重复调用 Agent。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")
    return path


__all__ = ["load_cases", "load_runs", "write_jsonl"]
