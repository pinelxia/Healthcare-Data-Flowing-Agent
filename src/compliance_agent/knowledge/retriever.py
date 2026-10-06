"""本地关键词检索：确定性兜底检索，与 LLM 无关。"""

from __future__ import annotations

from compliance_agent.models import SubscriptionApplication
from .clauses import Clause


def _application_text(app: SubscriptionApplication) -> str:
    parts = [
        app.purpose,
        app.purpose_description or "",
        app.recipient,
        app.applicant.organization_id,
        app.applicant.role,
        " ".join(app.data_types),
        " ".join(app.data_fields),
    ]
    return " ".join(p for p in parts if p)


def score_clause(app: SubscriptionApplication, clause: Clause) -> float:
    """打分：条款关键词在申请文本中的子串命中数 + 数据类型重合奖励。"""
    text = _application_text(app)
    keyword_hits = sum(1 for kw in clause.keywords if kw and kw in text)
    type_hits = sum(2 for dt in clause.data_types if dt in app.data_types)
    return float(keyword_hits + type_hits)


def rank_clauses(app: SubscriptionApplication, clauses: list[Clause]) -> list[Clause]:
    """按相关性降序排列条款（等分保持文件顺序，稳定、可复现）。"""
    return sorted(clauses, key=lambda c: score_clause(app, c), reverse=True)
