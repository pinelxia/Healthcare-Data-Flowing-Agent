"""规则评估测试：状态映射、理由与证据引用。"""

from __future__ import annotations

from compliance_agent.engine.evaluator import evaluate
from compliance_agent.models import RuleOutcome, RuleStatus
from tests.conftest import make_application


def test_compliant_application_all_matched_rules_pass(mini_policy):
    results = evaluate(make_application(), mini_policy)

    # RSK-001 条件（retention > 30）不满足，跳过；其余 4 条全部通过
    assert [r.rule_id for r in results] == ["ID-001", "PUR-001", "MIN-002", "EVI-001"]
    assert all(r.status is RuleStatus.PASSED for r in results)
    assert all(r.outcome is RuleOutcome.ALLOW for r in results)


def test_violation_maps_to_deny_with_reason(mini_policy):
    results = evaluate(make_application(purpose="marketing"), mini_policy)

    denied = [r for r in results if r.rule_id == "PUR-001"]
    assert len(denied) == 1
    assert denied[0].status is RuleStatus.VIOLATED
    assert denied[0].outcome is RuleOutcome.DENY
    assert denied[0].reason == "用途不在允许列表内"
    assert denied[0].expected == "∈ ['claim', 'medical_report']"
    assert denied[0].clause_ref.endswith("CLS-PUR-001")


def test_missing_evidence_maps_to_manual_review(mini_policy):
    from compliance_agent.models import Evidence

    app = make_application(
        evidence=[Evidence(type="identity_cert", reference="REG-HK-001")],
    )
    results = evaluate(app, mini_policy)

    missing = [r for r in results if r.rule_id == "EVI-001"]
    assert len(missing) == 1
    assert missing[0].status is RuleStatus.EVIDENCE_MISSING
    assert missing[0].outcome is RuleOutcome.MANUAL_REVIEW
    assert "consent_record" in missing[0].actual


def test_risk_condition_maps_to_manual_review(mini_policy):
    results = evaluate(make_application(retention_days=60), mini_policy)

    risk = [r for r in results if r.rule_id == "RSK-001"]
    assert len(risk) == 1
    assert risk[0].status is RuleStatus.RISK_FLAG
    assert risk[0].outcome is RuleOutcome.MANUAL_REVIEW


def test_not_applicable_rules_are_skipped(mini_policy):
    app = make_application(data_types=["cost_detail"])
    results = evaluate(app, mini_policy)

    rule_ids = {r.rule_id for r in results}
    assert "EVI-001" not in rule_ids  # when 未命中 → 跳过
    assert "RSK-001" not in rule_ids


def test_evidence_usage_carries_rule_id(mini_policy):
    results = evaluate(make_application(), mini_policy)

    usage = [u for r in results for u in r.evidence_used]
    assert any(u.type == "consent_record" and "EVI-001" in u.rule_ids for u in usage)
    assert any(u.reference == "CONSENT-001" for u in usage)


def test_deny_and_manual_review_can_coexist_in_results(mini_policy):
    app = make_application(purpose="marketing", evidence=[])
    results = evaluate(app, mini_policy)

    outcomes = {r.outcome for r in results}
    assert RuleOutcome.DENY in outcomes
    assert RuleOutcome.MANUAL_REVIEW in outcomes
