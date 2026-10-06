"""编排层：一次评估的完整流程。

流程固定为：加载策略 → 引擎评估 → 判定 → 条款检索 → 辅助解释 → 组装报告。
LLM 任何失败都降级本地实现，判定流程不受影响。
"""

from __future__ import annotations

import logging
from typing import Optional

from .config import AppConfig
from .engine.evaluator import evaluate
from .engine.policy import load_policy
from .engine.verdict import collect_missing_information, decide
from .knowledge.clauses import Clause, get_clause_by_ref, load_clauses
from .knowledge.retriever import rank_clauses as local_rank
from .llm.base import LLMClient, LLMError
from .llm.explainer import build_explanation
from .llm.factory import build_llm
from .llm.null import NullLLM
from .models import ClauseSummary, EvidenceUsage, RuleResult, SubscriptionApplication, VerdictReport
from .report import build_report

logger = logging.getLogger(__name__)


def _collect_evidence_used(results: list[RuleResult]) -> list[EvidenceUsage]:
    """合并各规则引用的证据（按类型+引用去重，保留首次出现顺序）。"""
    merged: dict[tuple[str, str | None], EvidenceUsage] = {}
    for result in results:
        for usage in result.evidence_used:
            key = (usage.type, usage.reference)
            if key in merged:
                merged[key] = merged[key].model_copy(
                    update={"rule_ids": sorted(set(merged[key].rule_ids) | set(usage.rule_ids))}
                )
            else:
                merged[key] = usage
    return list(merged.values())


class ComplianceAssessor:
    """合规评估编排：组装引擎、知识库与模型辅助层。"""

    def __init__(self, config: Optional[AppConfig] = None, llm: Optional[LLMClient] = None) -> None:
        self.config = config or AppConfig()
        if llm is not None:
            self.llm = llm
        else:
            try:
                self.llm = build_llm(self.config)
            except LLMError as exc:
                logger.warning("LLM 初始化失败，降级本地实现（null）: %s", exc)
                self.llm = NullLLM()

    def assess(
        self,
        app: SubscriptionApplication,
        *,
        policy_version: Optional[str] = None,
        use_llm: Optional[bool] = None,
    ) -> VerdictReport:
        """评估订阅申请。policy_version 优先于申请内期望版本。"""
        requested = policy_version if policy_version is not None else app.policy_version
        policy = load_policy(self.config.policies_dir, requested)

        # 1. 确定性评估与判定（唯一判定来源）
        results = evaluate(app, policy)
        verdict = decide(results)
        missing = collect_missing_information(results, verdict)
        evidence_used = _collect_evidence_used(results)

        # 2. 条款检索：命中条款强制包含 + 相关性排序
        clauses = load_clauses(self.config.clauses_dir)
        selected = self._select_clauses(app, clauses, results, use_llm)

        # 3. 辅助归纳与提示（失败降级，不影响判定）
        summaries, hints, llm_used = self._assist(app, selected, use_llm)
        explanation = build_explanation(summaries, hints)

        return build_report(
            app=app,
            policy=policy,
            results=results,
            verdict=verdict,
            missing_information=missing,
            evidence_used=evidence_used,
            clause_summaries=summaries,
            explanation=explanation,
            llm_provider=self.llm.name,
            llm_used=llm_used,
        )

    def _use_model(self, use_llm: Optional[bool]) -> bool:
        """模型辅助是否启用：显式参数优先；本地实现（null）永远不参与模型路径。"""
        if self.llm.name == "null":
            return False
        if use_llm is not None:
            return use_llm
        return True

    def _select_clauses(
        self, app: SubscriptionApplication, clauses: list[Clause], results: list[RuleResult], use_llm: Optional[bool]
    ) -> list[Clause]:
        selected: list[Clause] = []
        seen: set[str] = set()
        # 引擎命中条款强制包含（保证审计引用完整）
        for result in results:
            clause = get_clause_by_ref(clauses, result.clause_ref)
            if clause is not None and clause.clause_id not in seen:
                selected.append(clause)
                seen.add(clause.clause_id)
            elif clause is None:
                logger.warning("规则 %s 引用的条款不存在: %s", result.rule_id, result.clause_ref)
        # 其余条款按相关性排序补足
        if self._use_model(use_llm):
            try:
                ranked_ids = self.llm.rank_clauses(app, clauses)
                ranked = sorted(clauses, key=lambda c: ranked_ids.index(c.clause_id) if c.clause_id in ranked_ids else len(ranked_ids))
            except Exception as exc:  # LLM 为辅助层：任何异常都降级，不影响判定
                logger.warning("LLM 检索排序失败，降级本地打分: %s", exc)
                ranked = local_rank(app, clauses)
        else:
            ranked = local_rank(app, clauses)
        for clause in ranked:
            if clause.clause_id in seen:
                continue
            if len(selected) >= self.config.llm_max_clauses:
                break
            selected.append(clause)
            seen.add(clause.clause_id)
        return selected

    def _assist(
        self, app: SubscriptionApplication, clauses: list[Clause], use_llm: Optional[bool]
    ) -> tuple[list[ClauseSummary], list[str], bool]:
        """条款归纳 + 缺失提示；任一调用失败即整体降级本地实现。"""
        if not self._use_model(use_llm):
            null = NullLLM()
            return null.summarize_clauses(app, clauses), [], False
        try:
            summaries = self.llm.summarize_clauses(app, clauses)
            hints = self.llm.suggest_missing_info(app)
            return summaries, hints, True
        except Exception as exc:  # LLM 为辅助层：任何异常都降级，不影响判定
            logger.warning("LLM 辅助归纳失败，降级本地模板: %s", exc)
            return NullLLM().summarize_clauses(app, clauses), [], False
