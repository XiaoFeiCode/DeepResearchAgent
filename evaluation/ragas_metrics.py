"""使用 RAGAS 0.4 Metrics Collections API 评测回答、检索和 Agent。"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

# 官方遥测与项目评测无关，关闭后也可避免离线环境等待遥测网络请求。
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from openai import AsyncOpenAI
from ragas.embeddings import embedding_factory
from ragas.llms import llm_factory
from ragas.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from ragas.metrics.collections import (
    AgentGoalAccuracyWithReference,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    FactualCorrectness,
    Faithfulness,
    ToolCallAccuracy,
    ToolCallF1,
)

from core.settings import AppSettings
from evaluation.models import EvaluationRun, MetricScore


CONTROL_TOOL_NAMES = {"task", "write_todos", "read_todos"}


class RagasEvaluator:
    """复用同一个裁判模型和 Embedding 客户端批量评分。"""

    def __init__(self, settings: AppSettings) -> None:
        model, base_url, api_key = settings.evaluation_llm_credentials()
        llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.llm = llm_factory(
            model,
            provider="openai",
            client=llm_client,
            max_tokens=settings.evaluation_llm_max_tokens,
        )
        self.embeddings = None

        embedding_credentials = settings.evaluation_embedding_credentials()
        if embedding_credentials is not None:
            embedding_model, embedding_base_url, embedding_api_key = (
                embedding_credentials
            )
            embedding_client = AsyncOpenAI(
                api_key=embedding_api_key,
                base_url=embedding_base_url,
            )
            self.embeddings = embedding_factory(
                provider="openai",
                model=embedding_model,
                client=embedding_client,
                interface="modern",
            )

    async def score_run(self, run: EvaluationRun) -> list[MetricScore]:
        """根据当前用例具备的参考字段选择可计算指标。"""
        pending: list[tuple[str, Callable[[], Awaitable[Any]]]] = []

        if run.retrieved_contexts:
            metric = Faithfulness(llm=self.llm)
            pending.append(
                (
                    "faithfulness",
                    lambda metric=metric: metric.ascore(
                        user_input=run.case.query,
                        response=run.response,
                        retrieved_contexts=run.retrieved_contexts,
                    ),
                )
            )

        if self.embeddings is not None:
            metric = AnswerRelevancy(llm=self.llm, embeddings=self.embeddings)
            pending.append(
                (
                    "answer_relevancy",
                    lambda metric=metric: metric.ascore(
                        user_input=run.case.query,
                        response=run.response,
                    ),
                )
            )

        if run.case.reference_answer:
            factual = FactualCorrectness(llm=self.llm)
            pending.append(
                (
                    "factual_correctness",
                    lambda metric=factual: metric.ascore(
                        response=run.response,
                        reference=run.case.reference_answer or "",
                    ),
                )
            )

            if run.retrieved_contexts:
                precision = ContextPrecision(llm=self.llm)
                recall = ContextRecall(llm=self.llm)
                pending.extend(
                    [
                        (
                            "context_precision",
                            lambda metric=precision: metric.ascore(
                                user_input=run.case.query,
                                reference=run.case.reference_answer or "",
                                retrieved_contexts=run.retrieved_contexts,
                            ),
                        ),
                        (
                            "context_recall",
                            lambda metric=recall: metric.ascore(
                                user_input=run.case.query,
                                retrieved_contexts=run.retrieved_contexts,
                                reference=run.case.reference_answer or "",
                            ),
                        ),
                    ]
                )

        goal_reference = run.case.reference_goal or run.case.reference_answer
        if goal_reference:
            goal = AgentGoalAccuracyWithReference(llm=self.llm)
            conversation = self._conversation(run)
            pending.append(
                (
                    "agent_goal_accuracy",
                    lambda metric=goal, messages=conversation, reference=goal_reference: metric.ascore(
                        user_input=messages,
                        reference=reference,
                    ),
                )
            )

        # RAGAS 的工具指标要求参数也有标准答案；仅配置名称时交给确定性 F1。
        if run.case.expected_tools and all(
            expected.args is not None for expected in run.case.expected_tools
        ):
            messages = self._conversation(run)
            expected_calls = [
                ToolCall(name=item.name, args=item.args or {})
                for item in run.case.expected_tools
            ]
            accuracy = ToolCallAccuracy(strict_order=True)
            f1 = ToolCallF1()
            pending.extend(
                [
                    (
                        "tool_call_accuracy",
                        lambda metric=accuracy: metric.ascore(
                            user_input=messages,
                            reference_tool_calls=expected_calls,
                        ),
                    ),
                    (
                        "tool_call_f1",
                        lambda metric=f1: metric.ascore(
                            user_input=messages,
                            reference_tool_calls=expected_calls,
                        ),
                    ),
                ]
            )

        scores: list[MetricScore] = []
        for metric_name, score_call in pending:
            try:
                result = await score_call()
                scores.append(
                    MetricScore(
                        case_id=run.case.id,
                        metric=metric_name,
                        score=float(result.value),
                        evaluator="ragas",
                        reason=str(result.reason or ""),
                        span_id=run.span_id,
                    )
                )
            except Exception as error:
                scores.append(
                    MetricScore(
                        case_id=run.case.id,
                        metric=metric_name,
                        evaluator="ragas",
                        error=str(error),
                        reason="RAGAS 指标执行失败，未计入聚合平均分",
                        span_id=run.span_id,
                    )
                )
        return scores

    @staticmethod
    def _conversation(run: EvaluationRun) -> list[HumanMessage | AIMessage | ToolMessage]:
        messages: list[HumanMessage | AIMessage | ToolMessage] = [
            HumanMessage(content=run.case.query)
        ]
        observed_calls = run.reported_tools or run.tool_calls
        for call in observed_calls:
            name = str(call.get("name") or "unknown")
            if name in CONTROL_TOOL_NAMES:
                continue
            messages.append(
                AIMessage(
                    content=f"调用工具 {name}",
                    tool_calls=[ToolCall(name=name, args=dict(call.get("args") or {}))],
                )
            )
            if call.get("output") not in (None, ""):
                messages.append(ToolMessage(content=str(call["output"])))
        messages.append(AIMessage(content=run.response))
        return messages


__all__ = ["RagasEvaluator"]
