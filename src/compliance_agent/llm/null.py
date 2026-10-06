"""NullLLM：本地降级实现，零外部依赖。

条款排序用本地关键词打分，归纳直接取条款 frontmatter 的 summary 字段。
无 API Key、模型不可用或调用失败时，系统自动使用本实现，判定流程不受影响。
"""

from __future__ import annotations

from ..knowledge.clauses import Clause
from ..knowledge.retriever import rank_clauses as local_rank
from ..models import ClauseSummary, SubscriptionApplication


class NullLLM:
    name = "null"

    def rank_clauses(self, app: SubscriptionApplication, clauses: list[Clause]) -> list[str]:
        return [c.clause_id for c in local_rank(app, clauses)]

    def summarize_clauses(self, app: SubscriptionApplication, clauses: list[Clause]) -> list[ClauseSummary]:
        summaries: list[ClauseSummary] = []
        for clause in clauses:
            text = clause.summary.strip()
            if not text and clause.body.strip():
                text = clause.body.splitlines()[0].strip()
            if text:
                summaries.append(ClauseSummary(clause_id=clause.clause_id, summary=text))
        return summaries

    def suggest_missing_info(self, app: SubscriptionApplication) -> list[str]:
        return []
