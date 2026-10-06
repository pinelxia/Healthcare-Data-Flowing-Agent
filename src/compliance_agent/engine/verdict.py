"""判定优先级与缺失信息收集。

verdict 字段的唯一写入点：本模块的 decide()。优先级 deny > manual_review > allow。
fail-closed 为系统恒定行为：无规则命中 → manual_review，绝不默认放行，
该行为不可被策略配置关闭。
"""

from __future__ import annotations

from ..models import RuleOutcome, RuleResult, RuleStatus, Verdict

NO_RULE_MATCHED_MESSAGE = "未命中任何适用规则（fail-closed，信息不足，转人工审批）"


def decide(results: list[RuleResult]) -> Verdict:
    """根据规则结果计算最终判定（确定性，不允许 LLM 参与）。"""
    outcomes = [r.outcome for r in results]
    if RuleOutcome.DENY in outcomes:
        return Verdict.DENY
    if RuleOutcome.MANUAL_REVIEW in outcomes:
        return Verdict.MANUAL_REVIEW
    if not results:
        return Verdict.MANUAL_REVIEW  # fail-closed：无规则命中绝不默认放行
    return Verdict.ALLOW


def collect_missing_information(results: list[RuleResult], verdict: Verdict) -> list[str]:
    """收集缺失信息：证据缺失的规则 + fail-closed 无规则命中的情况。"""
    missing = [
        f"[{r.rule_id}] {r.name}：{r.reason}"
        f"（期望: {r.expected or '-'}；实际: {r.actual or '-'}）"
        for r in results
        if r.status is RuleStatus.EVIDENCE_MISSING
    ]
    if not results and verdict is Verdict.MANUAL_REVIEW:
        missing.append(NO_RULE_MATCHED_MESSAGE)
    return missing
