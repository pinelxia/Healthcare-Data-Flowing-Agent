"""领域模型：订阅申请、策略、规则结果与判定报告（pydantic v2，边界校验）。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Applicant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    organization_id: str
    region: str


class Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    region: str


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    present: bool = True
    reference: Optional[str] = None


class SubscriptionApplication(BaseModel):
    """订阅申请：可信数据空间审批流的输入（系统边界，未知字段直接拒绝）。

    约束（fail fast）：
    - retention_days 为非负整数（strict 拒绝 YAML bool 隐式转换）；
    - data_types / data_fields 至少各一项，避免最小化检查空转通过；
    - submitted_at 必须携带时区（无时区视为 UTC，业务假设）。
    """

    model_config = ConfigDict(extra="forbid")

    application_id: str
    applicant: Applicant
    purpose: str
    purpose_description: Optional[str] = None
    data_types: list[str] = Field(min_length=1)
    data_fields: list[str] = Field(min_length=1)
    destination: Destination
    recipient: str
    retention_days: int = Field(ge=0, strict=True)
    requested_until: date
    submitted_at: datetime
    evidence: list[Evidence] = Field(default_factory=list)
    policy_version: Optional[str] = None

    @field_validator("submitted_at")
    @classmethod
    def ensure_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Verdict(str, Enum):
    """三态判定。唯一写入点在 engine/verdict.py:decide()。"""

    ALLOW = "allow"
    MANUAL_REVIEW = "manual_review"
    DENY = "deny"


class RuleOutcome(str, Enum):
    ALLOW = "allow"
    MANUAL_REVIEW = "manual_review"
    DENY = "deny"


class CheckSpec(BaseModel):
    """确定性检查参数。按检查类型取用不同字段。"""

    model_config = ConfigDict(extra="forbid")

    type: str
    path: Optional[str] = None
    values: Optional[list[str]] = None
    max: Optional[int] = None
    min_days: Optional[int] = None
    max_days: Optional[int] = None
    anchor: Optional[str] = None
    per_type: Optional[dict[str, list[str]]] = None
    evidence_types: Optional[list[str]] = None
    when: Optional[dict[str, str]] = None
    all_of: Optional[list[dict[str, Any]]] = None


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    name: str
    section: str
    description: str
    check: CheckSpec
    outcome_on_fail: Literal["deny", "manual_review"] = "deny"
    missing_outcome: Literal["deny", "manual_review"] = "manual_review"
    evidence_required: list[str] = Field(default_factory=list)
    clause_ref: str
    source: str
    risk: Literal["low", "medium", "high"] = "medium"
    reason: str


class Policy(BaseModel):
    """策略。fail-closed 为系统恒定行为（无规则命中 → manual_review），策略不可关闭。"""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    version: str
    effective_date: date
    regions: list[str] = Field(default_factory=list)
    description: str = ""
    rules: list[PolicyRule]


class EvidenceUsage(BaseModel):
    type: str
    reference: Optional[str] = None
    rule_ids: list[str] = Field(default_factory=list)


class RuleStatus(str, Enum):
    PASSED = "passed"
    VIOLATED = "violated"
    EVIDENCE_MISSING = "evidence_missing"
    RISK_FLAG = "risk_flag"


class RuleResult(BaseModel):
    rule_id: str
    name: str
    section: str
    status: RuleStatus
    outcome: RuleOutcome
    reason: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    clause_ref: str
    source: str
    risk: str
    evidence_used: list[EvidenceUsage] = Field(default_factory=list)


class ClauseSummary(BaseModel):
    clause_id: str
    summary: str


class VerdictReport(BaseModel):
    """判定报告：每次判定返回命中规则、使用证据、缺失信息与策略版本。"""

    model_config = ConfigDict(extra="forbid")

    application_id: str
    verdict: Verdict
    policy_id: str
    policy_version: str
    matched_rules: list[RuleResult]
    evidence_used: list[EvidenceUsage]
    missing_information: list[str]
    explanation: Optional[str] = None
    clause_summaries: list[ClauseSummary] = Field(default_factory=list)
    llm_provider: str
    llm_used: bool
    assessed_at: datetime
