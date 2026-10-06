"""共享测试夹具。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from compliance_agent.models import (
    Applicant,
    Destination,
    Evidence,
    Policy,
    SubscriptionApplication,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_kb() -> Path:
    """仓库内真实知识库目录（策略 + 条款）。"""
    return REPO_ROOT / "knowledge_base"

SUBMITTED_AT = datetime(2026, 10, 6, 9, 0, 0)


def make_application(**overrides) -> SubscriptionApplication:
    """构造一份合规的基准申请；用 overrides 制造违规/缺失场景。"""
    data = dict(
        application_id="APP-TEST-001",
        applicant=Applicant(role="hk_insurer", organization_id="hk-ins-0001", region="hk"),
        purpose="claim",
        purpose_description="香港居民内地就医理赔",
        data_types=["diagnosis_summary", "cost_detail", "claim_certificate"],
        data_fields=["patient_name", "visit_date", "diagnosis_summary", "amount"],
        destination=Destination(connector_id="hk-crossborder-connector-1", region="hk"),
        recipient="hk-insurance-co-a",
        retention_days=30,
        requested_until=date(2026, 12, 1),
        submitted_at=SUBMITTED_AT,
        evidence=[
            Evidence(type="identity_cert", reference="REG-HK-001"),
            Evidence(type="consent_record", reference="CONSENT-001"),
            Evidence(type="insurance_order", reference="ORDER-001"),
        ],
    )
    data.update(overrides)
    return SubscriptionApplication(**data)


@pytest.fixture
def compliant_application() -> SubscriptionApplication:
    return make_application()


@pytest.fixture
def mini_policy() -> Policy:
    """精简策略：覆盖全部检查类型与三种结局映射，供单元测试使用。"""
    return Policy.model_validate(
        {
            "policy_id": "test-policy",
            "version": "1.0.0",
            "effective_date": "2026-01-01",
            "regions": ["cn-mainland", "hk"],
            "rules": [
                {
                    "rule_id": "ID-001",
                    "name": "申请方须为香港侧主体",
                    "section": "identity",
                    "description": "仅香港侧主体可发起订阅",
                    "check": {"type": "allowlist", "path": "applicant.region", "values": ["hk"]},
                    "outcome_on_fail": "deny",
                    "risk": "high",
                    "reason": "申请方所在区域不在允许范围内",
                    "clause_ref": "clauses/identity.md#CLS-IDENT-001",
                    "source": "业务假设：仅允许香港侧主体",
                },
                {
                    "rule_id": "PUR-001",
                    "name": "用途限制",
                    "section": "purpose",
                    "description": "仅允许理赔与就医报备",
                    "check": {"type": "allowlist", "path": "purpose", "values": ["claim", "medical_report"]},
                    "outcome_on_fail": "deny",
                    "risk": "high",
                    "reason": "用途不在允许列表内",
                    "clause_ref": "clauses/purpose.md#CLS-PUR-001",
                    "source": "业务假设：允许用途列表",
                },
                {
                    "rule_id": "MIN-002",
                    "name": "字段最小化",
                    "section": "data_minimization",
                    "description": "请求字段须属于请求类型的白名单",
                    "check": {
                        "type": "fields_within",
                        "path": "data_fields",
                        "per_type": {
                            "diagnosis_summary": ["patient_name", "visit_date", "diagnosis_summary"],
                            "cost_detail": ["patient_name", "item_name", "amount"],
                        },
                    },
                    "outcome_on_fail": "deny",
                    "risk": "high",
                    "reason": "请求字段超出最小化白名单",
                    "clause_ref": "clauses/data-minimization.md#CLS-MIN-001",
                    "source": "业务假设：字段白名单",
                },
                {
                    "rule_id": "EVI-001",
                    "name": "患者授权记录",
                    "section": "evidence",
                    "description": "诊断类数据须附患者授权同意记录",
                    "check": {
                        "type": "evidence_present",
                        "evidence_types": ["consent_record"],
                        "when": {"path": "data_types", "contains": "diagnosis_summary"},
                    },
                    "missing_outcome": "manual_review",
                    "evidence_required": ["consent_record"],
                    "risk": "medium",
                    "reason": "缺少患者授权同意记录，需人工审批",
                    "clause_ref": "clauses/data-minimization.md#CLS-MIN-001",
                    "source": "法律假设：敏感数据需患者授权",
                },
                {
                    "rule_id": "RSK-001",
                    "name": "诊断数据长期保留风险",
                    "section": "risk",
                    "description": "诊断类数据保留超过 30 天需人工复核",
                    "check": {
                        "type": "condition",
                        "all_of": [
                            {"path": "data_types", "op": "contains", "value": "diagnosis_summary"},
                            {"path": "retention_days", "op": "gt", "value": 30},
                        ],
                    },
                    "outcome_on_fail": "manual_review",
                    "risk": "high",
                    "reason": "诊断类数据保留期超过 30 天，风险较高，需人工复核",
                    "clause_ref": "clauses/retention.md#CLS-RET-001",
                    "source": "业务假设：高风险组合规则",
                },
            ],
        }
    )
