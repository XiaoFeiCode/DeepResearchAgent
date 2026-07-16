"""把离线评测分数作为 Annotation 回写到 Phoenix 根 Span。"""

from __future__ import annotations

from core.settings import AppSettings
from evaluation.models import MetricScore


def publish_scores(settings: AppSettings, scores: list[MetricScore]) -> int:
    """批量回写有效分数；没有 Span ID 的记录保留在本地报告中。"""
    from phoenix.client import Client
    from phoenix.client.resources.spans import SpanAnnotationData

    annotations = [
        SpanAnnotationData(
            name=score.metric,
            span_id=score.span_id,
            annotator_kind="LLM" if score.evaluator == "ragas" else "CODE",
            result={
                "score": score.score,
                "label": "pass" if score.score >= 0.6 else "fail",
                "explanation": score.reason,
            },
            metadata={"case_id": score.case_id, "evaluator": score.evaluator},
        )
        for score in scores
        if score.span_id and score.score is not None
    ]
    if not annotations:
        return 0

    client = Client(
        base_url=settings.evaluation_phoenix_base_url,
        api_key=settings.evaluation_phoenix_api_key,
    )
    client.spans.log_span_annotations(span_annotations=annotations, sync=True)
    return len(annotations)


__all__ = ["publish_scores"]
