"""策略加载与校验：YAML → Policy；版本解析与选择。

校验策略（fail fast，防静默放行）：
- 每种检查类型必须有完整的必填参数，否则加载即失败；
- evidence_present 的 when 守卫必须有 path+contains；
- condition 的每条子条件必须有 path/op/value，且 op 在允许集合内；
- 版本号必须是纯数字点分格式。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from ..models import CheckSpec, Policy, PolicyRule

SUPPORTED_CHECK_TYPES = {
    "allowlist",
    "subset",
    "fields_within",
    "lte",
    "date_within",
    "evidence_present",
    "condition",
}

# 每种检查类型必填的参数（缺失/为 None → 策略加载失败，绝不静默放行）
CHECK_REQUIRED_PARAMS: dict[str, list[str]] = {
    "allowlist": ["path", "values"],
    "subset": ["path", "values"],
    "fields_within": ["per_type"],
    "lte": ["path", "max"],
    "date_within": ["path", "anchor", "max_days"],
    "evidence_present": ["evidence_types"],
    "condition": ["all_of"],
}

CONDITION_OPS = {"contains", "eq", "ne", "gt", "gte", "lt", "lte"}

_VERSION_PATTERN = re.compile(r"^\d+(\.\d+)+$")


class PolicyError(Exception):
    """策略相关错误基类。"""


class PolicyNotFoundError(PolicyError):
    """策略文件缺失或指定版本不存在。"""


class PolicyValidationError(PolicyError):
    """策略内容不合法（结构/检查类型/未知字段）。"""


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _validate_rule(rule: PolicyRule) -> None:
    check = rule.check
    if check.type not in SUPPORTED_CHECK_TYPES:
        raise PolicyValidationError(
            f"规则 {rule.rule_id} 使用未知检查类型 {check.type!r}；"
            f"支持: {sorted(SUPPORTED_CHECK_TYPES)}"
        )
    for param in CHECK_REQUIRED_PARAMS.get(check.type, []):
        if getattr(check, param, None) is None:
            raise PolicyValidationError(
                f"规则 {rule.rule_id} 检查类型 {check.type!r} 缺少必填参数 {param!r}"
            )
    if check.type in ("allowlist", "subset") and not check.values:
        raise PolicyValidationError(f"规则 {rule.rule_id} 的 values 不能为空列表")
    if check.type == "evidence_present" and not check.evidence_types:
        raise PolicyValidationError(f"规则 {rule.rule_id} 的 evidence_types 不能为空列表")
    if check.when is not None and (not check.when.get("path") or not check.when.get("contains")):
        raise PolicyValidationError(f"规则 {rule.rule_id} 的 when 守卫必须包含 path 与 contains")
    for cond in check.all_of or []:
        if not cond.get("path") or cond.get("op") not in CONDITION_OPS or "value" not in cond:
            raise PolicyValidationError(f"规则 {rule.rule_id} 的条件子项不合法: {cond}")


def _parse_policy_file(path: Path) -> Policy:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyValidationError(f"策略文件 {path.name} 无法读取: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyValidationError(f"策略文件 {path.name} YAML 解析失败: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyValidationError(f"策略文件 {path.name} 顶层必须是映射")
    try:
        policy = Policy.model_validate(raw)
    except ValidationError as exc:
        raise PolicyValidationError(f"策略文件 {path.name} 结构不合法: {exc}") from exc
    if not _VERSION_PATTERN.fullmatch(policy.version):
        raise PolicyValidationError(
            f"策略文件 {path.name} 版本号 {policy.version!r} 不合法（须为纯数字点分格式，如 1.0.0）"
        )
    for rule in policy.rules:
        _validate_rule(rule)
    return policy


def _iter_policy_files(policies_dir: Path) -> list[Path]:
    files = sorted(policies_dir.glob("*.yaml")) + sorted(policies_dir.glob("*.yml"))
    if not files:
        raise PolicyNotFoundError(
            f"策略目录不存在或为空: {policies_dir}（可用环境变量 COMPLIANCE_KB_DIR 指定知识库目录）"
        )
    return files


def load_policy(policies_dir: Path, version: Optional[str] = None) -> Policy:
    """加载策略：version 为 None 时取最高版本，否则精确匹配。

    行为约定：
    - 显式指定版本时，其他无关文件的损坏不影响该版本（草稿文件可共存）；
    - 取最新版本时，目录中任何损坏文件都会报错（部署问题必须显式暴露）。
    """
    files = _iter_policy_files(policies_dir)
    policies: list[Policy] = []
    first_error: Optional[PolicyError] = None
    for path in files:
        try:
            policies.append(_parse_policy_file(path))
        except PolicyError as exc:
            if first_error is None:
                first_error = exc
    if not policies:
        raise first_error if first_error is not None else PolicyNotFoundError(f"策略目录为空: {policies_dir}")
    if version is None:
        if first_error is not None:
            raise first_error
        return max(policies, key=lambda p: _version_key(p.version))
    for policy in policies:
        if policy.version == version:
            return policy
    available = ", ".join(sorted({p.version for p in policies}))
    raise PolicyNotFoundError(f"策略版本 {version} 不存在；可用版本: {available}")


def list_policies(policies_dir: Path) -> list[dict]:
    """列出全部可用策略版本（供 API/CLI 展示）。"""
    files = _iter_policy_files(policies_dir)
    policies: list[Policy] = []
    for path in files:
        policies.append(_parse_policy_file(path))  # 任一文件损坏即报错（部署问题显式暴露）
    policies.sort(key=lambda p: _version_key(p.version), reverse=True)
    return [
        {
            "policy_id": p.policy_id,
            "version": p.version,
            "effective_date": p.effective_date.isoformat(),
            "regions": p.regions,
            "rules_count": len(p.rules),
        }
        for p in policies
    ]
