"""LLM 客户端协议与错误类型。

协议不含任何判定字段：模型只能辅助检索排序、条款归纳与缺失信息提示，
不能输出 allow/deny/manual_review，更不能修改引擎判定结果。
"""

from __future__ import annotations

from typing import Protocol

from ..models import ClauseSummary, SubscriptionApplication
from ..knowledge.clauses import Clause


class LLMError(Exception):
    """LLM 调用失败（网络/鉴权/解析）。上层捕获后降级本地实现，判定不受影响。"""


class LLMClient(Protocol):
    name: str

    def rank_clauses(self, app: SubscriptionApplication, clauses: list[Clause]) -> list[str]:
        """语义排序候选条款，返回 clause_id 列表。"""
        ...

    def summarize_clauses(self, app: SubscriptionApplication, clauses: list[Clause]) -> list[ClauseSummary]:
        """归纳条款要点（辅助解释）。"""
        ...

    def suggest_missing_info(self, app: SubscriptionApplication) -> list[str]:
        """提示可能缺失的信息（仅供参考）。"""
        ...
