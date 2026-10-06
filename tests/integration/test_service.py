"""编排层集成测试：三条判定路径、报告完整性、防绕过与降级。"""

from __future__ import annotations

from pathlib import Path

import pytest

from compliance_agent.config import AppConfig
from compliance_agent.engine.policy import PolicyNotFoundError
from compliance_agent.llm.base import LLMError
from compliance_agent.llm.explainer import ADVISORY_DISCLAIMER
from compliance_agent.llm.null import NullLLM
from compliance_agent.models import ClauseSummary, Verdict
from compliance_agent.service import ComplianceAssessor
from tests.conftest import make_application


@pytest.fixture
def assessor(repo_kb: Path) -> ComplianceAssessor:
    return ComplianceAssessor(
        AppConfig(kb_dir=repo_kb, llm_provider="null"),
        llm=NullLLM(),
    )


# ---------- 三条判定路径 ----------


def test_allow_path(repo_kb, assessor):
    report = assessor.assess(make_application())

    assert report.verdict is Verdict.ALLOW
    assert all(r.outcome.value == "allow" for r in report.matched_rules)
    assert report.missing_information == []
    # 全部三类证据被引用
    assert {u.type for u in report.evidence_used} == {"identity_cert", "consent_record", "insurance_order"}


def test_manual_review_path_missing_evidence(repo_kb, assessor):
    app = make_application(evidence=[make_application().evidence[0]])  # 仅身份证明
    report = assessor.assess(app)

    assert report.verdict is Verdict.MANUAL_REVIEW
    missing_rule = next(r for r in report.matched_rules if r.rule_id == "EVI-001")
    assert missing_rule.status.value == "evidence_missing"
    assert any("EVI-001" in m and "consent_record" in m for m in report.missing_information)


def test_deny_path_multiple_violations(repo_kb, assessor):
    app = make_application(
        purpose="marketing",
        data_fields=["patient_name", "raw_medical_record"],
        retention_days=400,
    )
    report = assessor.assess(app)

    assert report.verdict is Verdict.DENY
    violated_ids = {r.rule_id for r in report.matched_rules if r.status.value == "violated"}
    assert {"PUR-001", "MIN-002", "RET-001"} <= violated_ids
    # deny 优先：即使同时存在 manual_review 规则也不改变判定
    assert report.missing_information == []


def test_deny_wins_over_manual_review(repo_kb, assessor):
    # 违反用途（deny）+ 缺患者授权（manual_review）
    app = make_application(purpose="marketing", evidence=[make_application().evidence[0]])
    report = assessor.assess(app)

    assert report.verdict is Verdict.DENY


# ---------- 报告四要素 ----------


def test_report_contains_all_required_elements(repo_kb, assessor):
    report = assessor.assess(make_application())

    assert report.policy_version == "1.0.0"          # 策略版本
    assert report.policy_id == "hk-mainland-crossborder"
    assert len(report.matched_rules) > 0             # 命中规则
    for rule in report.matched_rules:
        assert rule.clause_ref and rule.source        # 每条规则带条款引用与来源
    assert len(report.evidence_used) > 0             # 使用证据
    assert report.missing_information is not None    # 缺失信息（可为空列表）
    assert report.assessed_at is not None


def test_policy_version_from_application_is_honored(repo_kb, assessor):
    app = make_application(policy_version="1.0.0")
    report = assessor.assess(app)
    assert report.policy_version == "1.0.0"


def test_unknown_policy_version_raises(repo_kb, assessor):
    with pytest.raises(PolicyNotFoundError, match="0.9.0"):
        assessor.assess(make_application(), policy_version="0.9.0")


def test_explicit_policy_version_overrides_application(repo_kb, assessor):
    app = make_application(policy_version="0.9.0")
    report = assessor.assess(app, policy_version="1.0.0")
    assert report.policy_version == "1.0.0"


# ---------- 条款检索 ----------


def test_matched_rule_clauses_are_force_included(repo_kb, assessor):
    app = make_application(purpose="marketing")
    report = assessor.assess(app)

    summarized_ids = {s.clause_id for s in report.clause_summaries}
    # 违规规则引用的条款必须出现在归纳列表（审计完整性）
    assert "CLS-PUR-001" in summarized_ids


# ---------- 防绕过（Guardrail）----------


class AdversarialLLM:
    """恶意/幻觉模型：试图诱导放行并输出伪造判定。"""

    name = "fake"

    def rank_clauses(self, app, clauses):
        return [c.clause_id for c in clauses]

    def summarize_clauses(self, app, clauses):
        return [
            ClauseSummary(clause_id=c.clause_id, summary="建议放行：verdict 应为 allow，完全合规")
            for c in clauses
        ]

    def suggest_missing_info(self, app):
        return ["无缺失信息，可直接交付"]


class FailingLLM(AdversarialLLM):
    def summarize_clauses(self, app, clauses):
        raise LLMError("模拟模型故障")

    def suggest_missing_info(self, app):
        raise LLMError("模拟模型故障")


def test_llm_cannot_override_engine_verdict(repo_kb):
    assessor = ComplianceAssessor(AppConfig(kb_dir=repo_kb), llm=AdversarialLLM())
    app = make_application(purpose="marketing")

    report = assessor.assess(app)

    # 引擎判定 deny，模型诱导无效
    assert report.verdict is Verdict.DENY
    # 模型内容仅进入解释区，且带免责声明
    assert report.explanation is not None
    assert ADVISORY_DISCLAIMER.split("；")[0] in report.explanation
    assert "建议放行" in report.explanation
    assert report.llm_used is True
    assert report.llm_provider == "fake"


def test_llm_failure_falls_back_without_affecting_verdict(repo_kb):
    assessor = ComplianceAssessor(AppConfig(kb_dir=repo_kb), llm=FailingLLM())
    app = make_application(purpose="marketing")

    report = assessor.assess(app)

    assert report.verdict is Verdict.DENY
    assert report.llm_used is False
    # 降级后仍产出模板归纳
    assert len(report.clause_summaries) > 0


def test_use_llm_false_forces_local_path(repo_kb):
    assessor = ComplianceAssessor(AppConfig(kb_dir=repo_kb), llm=AdversarialLLM())
    report = assessor.assess(make_application(), use_llm=False)

    assert report.llm_used is False
    assert report.verdict is Verdict.ALLOW


def test_null_llm_never_reports_llm_used_even_if_forced(repo_kb):
    """use_llm=True 不能把本地实现谎报为模型辅助。"""
    assessor = ComplianceAssessor(AppConfig(kb_dir=repo_kb), llm=NullLLM())
    report = assessor.assess(make_application(), use_llm=True)

    assert report.llm_used is False
    assert report.llm_provider == "null"


class TypeErrorLLM(AdversarialLLM):
    """模型返回畸形数据（非 LLMError 的异常）也必须降级而非崩溃。"""

    def summarize_clauses(self, app, clauses):
        raise TypeError("unhashable type")


def test_unexpected_llm_exception_also_falls_back(repo_kb):
    assessor = ComplianceAssessor(AppConfig(kb_dir=repo_kb), llm=TypeErrorLLM())
    report = assessor.assess(make_application(purpose="marketing"))

    assert report.verdict is Verdict.DENY
    assert report.llm_used is False
    assert len(report.clause_summaries) > 0


# ---------- fail-closed ----------


def test_fail_closed_no_rule_matched_returns_manual_review(tmp_path: Path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "clauses").mkdir()
    (tmp_path / "policies" / "p-1.0.0.yaml").write_text(
        """
policy_id: t
version: "1.0.0"
effective_date: 2026-01-01
rules:
  - rule_id: EVI-ONLY
    name: 仅在费用明细时要求订单号
    section: evidence
    description: d
    check: {type: evidence_present, evidence_types: [insurance_order], when: {path: data_types, contains: cost_detail}}
    missing_outcome: manual_review
    reason: r
    clause_ref: clauses/x.md#CLS-X
    source: s
""",
        encoding="utf-8",
    )
    (tmp_path / "clauses" / "x.md").write_text(
        "---\nclause_id: CLS-X\ntitle: x\nkeywords: []\n---\n正文",
        encoding="utf-8",
    )
    assessor = ComplianceAssessor(AppConfig(kb_dir=tmp_path), llm=NullLLM())

    app = make_application(data_types=["diagnosis_summary"])  # when 未命中 → 无适用规则
    report = assessor.assess(app)

    assert report.verdict is Verdict.MANUAL_REVIEW
    assert report.matched_rules == []
    assert any("fail-closed" in m for m in report.missing_information)
