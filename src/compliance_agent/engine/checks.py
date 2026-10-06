"""确定性检查函数：7 种检查类型，纯函数、无 LLM、无副作用。

每种检查返回 CheckResult：
- pass            检查通过
- fail            违反（映射到规则的 outcome_on_fail）
- missing         证据缺失（映射到规则的 missing_outcome）
- not_applicable  规则不适用于当前申请（跳过）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from ..models import CheckSpec, EvidenceUsage, SubscriptionApplication
from .policy import PolicyValidationError

_MISSING = object()


@dataclass
class CheckResult:
    status: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    evidence_used: list[EvidenceUsage] = field(default_factory=list)


def get_path(app: SubscriptionApplication, path: str) -> Any:
    """按点路径读取申请字段；路径不存在返回 _MISSING。"""
    value: Any = app
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part, _MISSING)
        else:
            value = getattr(value, part, _MISSING)
        if value is _MISSING:
            return _MISSING
    return value


def _present(value: Any) -> bool:
    return value is not _MISSING and value is not None


def check_allowlist(app: SubscriptionApplication, spec: CheckSpec) -> CheckResult:
    value = get_path(app, spec.path or "")
    if not _present(value):
        return CheckResult("fail", expected=f"字段 {spec.path} ∈ {spec.values}", actual="字段缺失")
    if value in (spec.values or []):
        return CheckResult("pass")
    return CheckResult("fail", expected=f"∈ {spec.values}", actual=repr(value))


def check_subset(app: SubscriptionApplication, spec: CheckSpec) -> CheckResult:
    value = get_path(app, spec.path or "")
    if not _present(value) or not isinstance(value, list):
        return CheckResult("fail", expected=f"列表 ⊆ {spec.values}", actual=f"字段缺失或非列表: {value!r}")
    extra = [v for v in value if v not in (spec.values or [])]
    if extra:
        return CheckResult("fail", expected=f"⊆ {spec.values}", actual=f"越界项: {extra}")
    return CheckResult("pass")


def check_fields_within(app: SubscriptionApplication, spec: CheckSpec) -> CheckResult:
    per_type = spec.per_type or {}
    offending = [
        f
        for f in app.data_fields
        if not any(f in per_type.get(data_type, []) for data_type in app.data_types)
    ]
    if offending:
        return CheckResult(
            "fail",
            expected="请求字段至少属于一个请求数据类型的白名单",
            actual=f"越界字段: {offending}",
        )
    return CheckResult("pass")


def check_lte(app: SubscriptionApplication, spec: CheckSpec) -> CheckResult:
    value = get_path(app, spec.path or "")
    if not _present(value) or not isinstance(value, (int, float)):
        return CheckResult("fail", expected=f"数值字段 {spec.path} ≤ {spec.max}", actual="字段缺失或非数值")
    if value <= (spec.max if spec.max is not None else float("inf")):
        return CheckResult("pass")
    return CheckResult("fail", expected=f"≤ {spec.max}", actual=str(value))


def check_date_within(app: SubscriptionApplication, spec: CheckSpec) -> CheckResult:
    value = get_path(app, spec.path or "")
    anchor = get_path(app, spec.anchor or "")
    if not _present(value) or not _present(anchor):
        return CheckResult("fail", expected="日期字段存在", actual="字段缺失")
    if isinstance(anchor, datetime):
        anchor = anchor.date()
    if not isinstance(value, date) or not isinstance(anchor, date):
        return CheckResult("fail", expected="日期类型", actual=f"value={value!r}, anchor={anchor!r}")
    days = (value - anchor).days
    min_days = spec.min_days if spec.min_days is not None else 0
    max_days = spec.max_days
    expected = f"{spec.path} 距 {spec.anchor} 在 [{min_days}, {max_days}] 天内"
    if min_days <= days <= (max_days if max_days is not None else float("inf")):
        return CheckResult("pass")
    return CheckResult("fail", expected=expected, actual=f"{days} 天")


def check_evidence_present(app: SubscriptionApplication, spec: CheckSpec) -> CheckResult:
    when = spec.when
    if when:
        container = get_path(app, when.get("path", ""))
        # 守卫容器必须是可迭代类型；非容器（策略配置错误）按 fail-closed 处理：
        # 视为需求生效，继续要求证据，而不是静默跳过
        if not _present(container) or not isinstance(container, (list, tuple, str)):
            pass  # 需求生效
        elif when.get("contains") not in container:
            return CheckResult("not_applicable")
    types = spec.evidence_types or []
    # 同类型多条证据：任一 present 即视为已提供（与顺序无关的确定性聚合）
    by_type: dict[str, list] = {}
    for e in app.evidence:
        by_type.setdefault(e.type, []).append(e)
    missing = [t for t in types if not any(e.present for e in by_type.get(t, []))]
    present = [
        EvidenceUsage(
            type=t,
            reference=next((e.reference for e in by_type.get(t, []) if e.present), None),
        )
        for t in types
        if any(e.present for e in by_type.get(t, []))
    ]
    if missing:
        return CheckResult(
            "missing",
            expected=f"提供证据: {types}",
            actual=f"缺失: {missing}",
            evidence_used=present,
        )
    return CheckResult("pass", expected=f"提供证据: {types}", evidence_used=present)


def _compare(value: Any, op: str, target: Any) -> bool:
    if not _present(value):
        return False
    if op == "contains":
        return isinstance(value, (list, tuple, str)) and target in value
    if op == "eq":
        return value == target
    if op == "ne":
        return value != target
    if op == "gt":
        return isinstance(value, (int, float)) and value > target
    if op == "gte":
        return isinstance(value, (int, float)) and value >= target
    if op == "lt":
        return isinstance(value, (int, float)) and value < target
    if op == "lte":
        return isinstance(value, (int, float)) and value <= target
    raise PolicyValidationError(f"未知条件操作符: {op}")


def check_condition(app: SubscriptionApplication, spec: CheckSpec) -> CheckResult:
    """组合条件：all_of 全部成立时规则触发（返回 fail，由 outcome_on_fail 映射）。"""
    for cond in spec.all_of or []:
        if not _compare(get_path(app, cond.get("path", "")), cond.get("op", "eq"), cond.get("value")):
            return CheckResult("not_applicable")
    return CheckResult(
        "fail",
        expected="未命中风险组合条件",
        actual=f"命中条件: {spec.all_of}",
    )


_CHECK_FUNCTIONS = {
    "allowlist": check_allowlist,
    "subset": check_subset,
    "fields_within": check_fields_within,
    "lte": check_lte,
    "date_within": check_date_within,
    "evidence_present": check_evidence_present,
    "condition": check_condition,
}


def run_check(spec: CheckSpec, app: SubscriptionApplication) -> CheckResult:
    """执行单条检查。未知类型在策略加载时已被拒绝，此处兜底报错。"""
    fn = _CHECK_FUNCTIONS.get(spec.type)
    if fn is None:
        raise PolicyValidationError(f"未知检查类型: {spec.type}")
    return fn(app, spec)
