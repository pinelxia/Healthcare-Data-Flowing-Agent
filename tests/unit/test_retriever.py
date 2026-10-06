"""本地关键词检索测试。"""

from __future__ import annotations

from compliance_agent.knowledge.clauses import Clause
from compliance_agent.knowledge.retriever import rank_clauses, score_clause
from tests.conftest import make_application


def make_clause(clause_id: str, keywords: list[str], data_types: list[str] | None = None) -> Clause:
    return Clause(
        clause_id=clause_id,
        title=f"条款{clause_id}",
        keywords=keywords,
        data_types=data_types or [],
        body="正文",
        file=f"{clause_id}.md",
    )


def test_keyword_hit_scores_higher():
    app = make_application()  # purpose=claim，描述含"理赔"
    hit = make_clause("C1", keywords=["理赔"])
    miss = make_clause("C2", keywords=["毫无关系的词"])

    assert score_clause(app, hit) > score_clause(app, miss)
    assert rank_clauses(app, [miss, hit])[0].clause_id == "C1"


def test_data_type_overlap_adds_bonus():
    app = make_application()
    typed = make_clause("C1", keywords=[], data_types=["diagnosis_summary"])
    untyped = make_clause("C2", keywords=["理赔"])

    # 数据类型重合 +2 分，压过单个关键词命中 +1 分
    assert score_clause(app, typed) > score_clause(app, untyped)


def test_equal_scores_keep_stable_order():
    app = make_application()
    a = make_clause("A", keywords=[])
    b = make_clause("B", keywords=[])

    ranked = rank_clauses(app, [b, a])

    assert [c.clause_id for c in ranked] == ["B", "A"]


def test_purpose_description_contributes_to_matching():
    app = make_application(purpose_description="患者授权同意与隐私保护相关")
    consent = make_clause("C1", keywords=["患者授权"])

    assert score_clause(app, consent) >= 1
