"""规则评估：申请 × 策略 → 规则结果列表（含状态、理由、证据引用）。"""

from __future__ import annotations

from ..models import (
    Policy,
    PolicyRule,
    RuleOutcome,
    RuleResult,
    RuleStatus,
    SubscriptionApplication,
)
from .checks import CheckResult, run_check


def _map_rule_result(rule: PolicyRule, check_result: CheckResult) -> RuleResult:
    evidence_used = [
        usage.model_copy(update={"rule_ids": [rule.rule_id]}) for usage in check_result.evidence_used
    ]
    common = dict(
        rule_id=rule.rule_id,
        name=rule.name,
        section=rule.section,
        expected=check_result.expected,
        actual=check_result.actual,
        clause_ref=rule.clause_ref,
        source=rule.source,
        risk=rule.risk,
        evidence_used=evidence_used,
    )
    if check_result.status == "pass":
        return RuleResult(
            **common,
            status=RuleStatus.PASSED,
            outcome=RuleOutcome.ALLOW,
            reason=f"{rule.name}：检查通过",
        )
    if check_result.status == "missing":
        outcome = RuleOutcome(rule.missing_outcome)
        return RuleResult(
            **common,
            status=RuleStatus.EVIDENCE_MISSING,
            outcome=outcome,
            reason=rule.reason,
        )
    # status == "fail"
    outcome = RuleOutcome(rule.outcome_on_fail)
    status = RuleStatus.RISK_FLAG if outcome is RuleOutcome.MANUAL_REVIEW else RuleStatus.VIOLATED
    return RuleResult(**common, status=status, outcome=outcome, reason=rule.reason)


def evaluate(app: SubscriptionApplication, policy: Policy) -> list[RuleResult]:
    """逐条执行确定性检查，跳过不适用的规则。"""
    results: list[RuleResult] = []
    for rule in policy.rules:
        check_result = run_check(rule.check, app)
        if check_result.status == "not_applicable":
            continue
        results.append(_map_rule_result(rule, check_result))
    return results
