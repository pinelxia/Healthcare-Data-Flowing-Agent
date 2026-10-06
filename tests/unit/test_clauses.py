"""条款加载测试。"""

from __future__ import annotations

import pytest

from compliance_agent.knowledge.clauses import ClauseError, get_clause_by_ref, load_clauses

VALID_CLAUSE = """---
clause_id: CLS-IDENT-001
title: 申请方身份登记要求
region: [hk]
data_types: []
keywords: [身份, 登记, 保险机构]
source: 业务假设：香港保险机构登记册（示意）
summary: 申请方须为已登记香港保险机构。
related_rules: [ID-002, ID-003]
---
申请方须在登记册内，且提供身份证明。
"""


def write_clause(tmp_path, name: str, text: str) -> None:
    (tmp_path / name).write_text(text, encoding="utf-8")


def test_loads_clause_with_frontmatter_and_body(tmp_path):
    write_clause(tmp_path, "identity.md", VALID_CLAUSE)

    clauses = load_clauses(tmp_path)

    assert len(clauses) == 1
    clause = clauses[0]
    assert clause.clause_id == "CLS-IDENT-001"
    assert clause.title == "申请方身份登记要求"
    assert clause.keywords == ["身份", "登记", "保险机构"]
    assert clause.summary.startswith("申请方须为已登记")
    assert "登记册内" in clause.body
    assert clause.file == "identity.md"


def test_raises_when_frontmatter_missing(tmp_path):
    write_clause(tmp_path, "bad.md", "没有 frontmatter 的正文")

    with pytest.raises(ClauseError, match="缺少 YAML frontmatter"):
        load_clauses(tmp_path)


def test_raises_when_frontmatter_unclosed(tmp_path):
    write_clause(tmp_path, "bad.md", "---\nclause_id: X\n（没有结束符）")

    with pytest.raises(ClauseError, match="未闭合"):
        load_clauses(tmp_path)


def test_raises_when_clause_id_missing(tmp_path):
    write_clause(tmp_path, "bad.md", "---\ntitle: 无 ID 的条款\n---\n正文")

    with pytest.raises(ClauseError, match="缺少 clause_id"):
        load_clauses(tmp_path)


def test_raises_on_unknown_metadata_field(tmp_path):
    write_clause(tmp_path, "bad.md", VALID_CLAUSE.replace("related_rules:", "sneaky_field:", 1))

    with pytest.raises(ClauseError, match="元数据不合法"):
        load_clauses(tmp_path)


def test_raises_when_directory_empty(tmp_path):
    with pytest.raises(ClauseError, match="不存在或为空"):
        load_clauses(tmp_path)


def test_get_clause_by_ref_matches_fragment(tmp_path):
    write_clause(tmp_path, "identity.md", VALID_CLAUSE)
    clauses = load_clauses(tmp_path)

    found = get_clause_by_ref(clauses, "clauses/identity.md#CLS-IDENT-001")

    assert found is not None
    assert found.clause_id == "CLS-IDENT-001"


def test_get_clause_by_ref_returns_none_for_unknown(tmp_path):
    write_clause(tmp_path, "identity.md", VALID_CLAUSE)
    clauses = load_clauses(tmp_path)

    assert get_clause_by_ref(clauses, "clauses/other.md#CLS-NOPE") is None
