"""条款库加载：Markdown 正文 + YAML frontmatter 元数据。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

_FRONTMATTER_DELIM = "---"


class ClauseError(Exception):
    """条款文件不合法。"""


class Clause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    title: str
    region: list[str] = Field(default_factory=list)
    data_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source: str = ""
    summary: str = ""
    related_rules: list[str] = Field(default_factory=list)
    body: str
    file: str


def _split_frontmatter(text: str, file_name: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        raise ClauseError(f"条款文件 {file_name} 缺少 YAML frontmatter（首行须为 ---）")
    end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == _FRONTMATTER_DELIM), None)
    if end is None:
        raise ClauseError(f"条款文件 {file_name} frontmatter 未闭合")
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise ClauseError(f"条款文件 {file_name} frontmatter 解析失败: {exc}") from exc
    if not isinstance(meta, dict):
        raise ClauseError(f"条款文件 {file_name} frontmatter 必须是映射")
    return meta, "\n".join(lines[end + 1 :]).strip()


def load_clauses(clauses_dir: Path) -> list[Clause]:
    """加载目录下全部条款（*.md）。"""
    files = sorted(clauses_dir.glob("*.md"))
    if not files:
        raise ClauseError(f"条款目录不存在或为空: {clauses_dir}")
    clauses: list[Clause] = []
    for path in files:
        meta, body = _split_frontmatter(path.read_text(encoding="utf-8"), path.name)
        if "clause_id" not in meta or "title" not in meta:
            raise ClauseError(f"条款文件 {path.name} 缺少 clause_id 或 title")
        try:
            clauses.append(
                Clause(
                    clause_id=meta.pop("clause_id"),
                    title=meta.pop("title"),
                    body=body,
                    file=path.name,
                    **meta,
                )
            )
        except Exception as exc:  # pydantic 校验失败（未知字段/类型错误）
            raise ClauseError(f"条款文件 {path.name} 元数据不合法: {exc}") from exc
    return clauses


def get_clause_by_ref(clauses: list[Clause], clause_ref: str) -> Optional[Clause]:
    """按 clause_ref（如 clauses/identity.md#CLS-IDENT-001）查找条款。"""
    fragment = clause_ref.split("#", 1)[-1] if "#" in clause_ref else clause_ref
    file_part = clause_ref.split("#", 1)[0].rsplit("/", 1)[-1] if "#" in clause_ref else ""
    for clause in clauses:
        if clause.clause_id == fragment:
            return clause
        if file_part and clause.file == file_part:
            return clause
    return None
