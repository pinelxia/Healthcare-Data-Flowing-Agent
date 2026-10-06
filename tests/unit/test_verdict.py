"""判定优先级与缺失信息收集测试。"""

from __future__ import annotations

from compliance_agent.engine.verdict import NO_RULE_MATCHED_MESSAGE, collect_missing_information, decide
from compliance_agent.models import RuleOutcome, RuleResult, RuleStatus, Verdict


def make_result(rule_id: str, outcome: RuleOutcome, status: RuleStatus = RuleStatus.VIOLATED) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        name=f"规则{rule_id}",
        section="test",
        status=status,
        outcome=outcome,
        reason="测试理由",
        clause_ref="clauses/test.md",
        source="测试",
        risk="medium",
    )


def test_all_pass_returns_allow():
    results = [make_result("R1", RuleOutcome.ALLOW, RuleStatus.PASSED)]
    assert decide(results) is Verdict.ALLOW


def test_manual_review_wins_over_allow():
    results = [
        make_result("R1", RuleOutcome.ALLOW, RuleStatus.PASSED),
        make_result("R2", RuleOutcome.MANUAL_REVIEW, RuleStatus.EVIDENCE_MISSING),
    ]
    assert decide(results) is Verdict.MANUAL_REVIEW


def test_deny_wins_over_manual_review_and_allow():
    results = [
        make_result("R1", RuleOutcome.ALLOW, RuleStatus.PASSED),
        make_result("R2", RuleOutcome.MANUAL_REVIEW, RuleStatus.RISK_FLAG),
        make_result("R3", RuleOutcome.DENY),
    ]
    assert decide(results) is Verdict.DENY


def test_fail_closed_no_rules_returns_manual_review():
    """无规则命中 → manual_review 是系统恒定行为，不可被配置关闭。"""
    assert decide([]) is Verdict.MANUAL_REVIEW


def test_collect_missing_information_includes_evidence_missing():
    results = [
        make_result("R1", RuleOutcome.ALLOW, RuleStatus.PASSED),
        make_result(
            "EVI-001",
            RuleOutcome.MANUAL_REVIEW,
            RuleStatus.EVIDENCE_MISSING,
        ).model_copy(update={"expected": "提供证据", "actual": "缺失: [consent_record]"}),
    ]
    missing = collect_missing_information(results, Verdict.MANUAL_REVIEW)

    assert len(missing) == 1
    assert "EVI-001" in missing[0]
    assert "consent_record" in missing[0]


def test_collect_missing_information_includes_no_rule_matched():
    missing = collect_missing_information([], Verdict.MANUAL_REVIEW)

    assert missing == [NO_RULE_MATCHED_MESSAGE]


def test_collect_missing_information_empty_on_allow():
    results = [make_result("R1", RuleOutcome.ALLOW, RuleStatus.PASSED)]
    assert collect_missing_information(results, Verdict.ALLOW) == []
