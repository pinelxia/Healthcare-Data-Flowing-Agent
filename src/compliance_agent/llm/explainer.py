"""解释组装：模型辅助内容只进入 explanation 字段，不进入判定。"""

from __future__ import annotations

from typing import Optional

from ..models import ClauseSummary

ADVISORY_DISCLAIMER = (
    "以下内容由模型辅助生成，仅供参考，不构成判定依据；"
    "判定结果以确定性策略引擎及命中规则为准。"
)


def build_explanation(summaries: list[ClauseSummary], hints: list[str]) -> Optional[str]:
    """把条款归纳与缺失提示拼成给人工审阅的解释文本。"""
    sections: list[str] = []
    if summaries:
        lines = [f"- [{s.clause_id}] {s.summary}" for s in summaries]
        sections.append("相关条款归纳：\n" + "\n".join(lines))
    if hints:
        lines = [f"- {h}" for h in hints]
        sections.append("缺失信息提示（供人工参考）：\n" + "\n".join(lines))
    if not sections:
        return None
    return ADVISORY_DISCLAIMER + "\n\n" + "\n\n".join(sections)
