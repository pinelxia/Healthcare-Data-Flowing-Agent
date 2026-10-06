"""报告组装。

verdict 参数只接受 engine/verdict.py:decide() 的结果——本模块与 service
均不提供任何其他判定写入点，LLM 内容仅进入 explanation/clause_summaries。
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    ClauseSummary,
    EvidenceUsage,
    Policy,
    RuleResult,
    SubscriptionApplication,
    Verdict,
    VerdictReport,
)


def build_report(
    app: SubscriptionApplication,
    policy: Policy,
    results: list[RuleResult],
    verdict: Verdict,
    missing_information: list[str],
    evidence_used: list[EvidenceUsage],
    clause_summaries: list[ClauseSummary],
    explanation: str | None,
    llm_provider: str,
    llm_used: bool,
    assessed_at: datetime | None = None,
) -> VerdictReport:
    return VerdictReport(
        application_id=app.application_id,
        verdict=verdict,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        matched_rules=results,
        evidence_used=evidence_used,
        missing_information=missing_information,
        explanation=explanation,
        clause_summaries=clause_summaries,
        llm_provider=llm_provider,
        llm_used=llm_used,
        assessed_at=assessed_at or datetime.now(timezone.utc),
    )
