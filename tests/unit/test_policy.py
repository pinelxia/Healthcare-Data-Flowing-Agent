"""策略加载与校验测试。"""

from __future__ import annotations

import pytest
import yaml

from compliance_agent.engine.policy import (
    PolicyNotFoundError,
    PolicyValidationError,
    list_policies,
    load_policy,
)

VALID_POLICY_YAML = """
policy_id: test-policy
version: "{version}"
effective_date: 2026-01-01
regions: [cn-mainland, hk]
rules:
  - rule_id: ID-001
    name: 申请方须为香港侧主体
    section: identity
    description: 仅香港侧主体可发起订阅
    check: {{type: allowlist, path: applicant.region, values: [hk]}}
    outcome_on_fail: deny
    reason: 申请方所在区域不在允许范围内
    clause_ref: clauses/identity.md#CLS-IDENT-001
    source: 业务假设
"""


def write_policy(tmp_path, version: str, text: str = VALID_POLICY_YAML) -> None:
    (tmp_path / f"policy-{version}.yaml").write_text(text.format(version=version), encoding="utf-8")


def test_loads_policy_and_selects_highest_version(tmp_path):
    write_policy(tmp_path, "1.0.0")
    write_policy(tmp_path, "1.2.0")
    write_policy(tmp_path, "1.10.0")

    policy = load_policy(tmp_path)

    assert policy.version == "1.10.0"
    assert policy.policy_id == "test-policy"
    assert len(policy.rules) == 1


def test_loads_exact_requested_version(tmp_path):
    write_policy(tmp_path, "1.0.0")
    write_policy(tmp_path, "1.2.0")

    policy = load_policy(tmp_path, version="1.0.0")

    assert policy.version == "1.0.0"


def test_raises_when_requested_version_missing(tmp_path):
    write_policy(tmp_path, "1.0.0")

    with pytest.raises(PolicyNotFoundError, match="1.5.0"):
        load_policy(tmp_path, version="1.5.0")


def test_raises_when_directory_empty(tmp_path):
    with pytest.raises(PolicyNotFoundError, match="不存在或为空"):
        load_policy(tmp_path)


def test_raises_on_unreadable_policy_file(tmp_path):
    (tmp_path / "locked.yaml").write_text(VALID_POLICY_YAML.format(version="1.0.0"), encoding="utf-8")
    (tmp_path / "locked.yaml").chmod(0o000)

    try:
        with pytest.raises(PolicyValidationError, match="无法读取"):
            load_policy(tmp_path)
    finally:
        (tmp_path / "locked.yaml").chmod(0o644)


def test_raises_on_invalid_yaml(tmp_path):
    (tmp_path / "broken.yaml").write_text(": bad: [unclosed", encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="YAML 解析失败"):
        load_policy(tmp_path)


def test_raises_on_unknown_check_type(tmp_path):
    bad = VALID_POLICY_YAML.replace("allowlist", "hallucinated_check", 1)
    write_policy(tmp_path, "1.0.0", text=bad)

    with pytest.raises(PolicyValidationError, match="未知检查类型"):
        load_policy(tmp_path)


def test_raises_on_unknown_rule_field(tmp_path):
    bad = VALID_POLICY_YAML.replace(
        "source: 业务假设", "source: 业务假设\n    sneaky_field: true"
    )
    write_policy(tmp_path, "1.0.0", text=bad)

    with pytest.raises(PolicyValidationError, match="结构不合法"):
        load_policy(tmp_path)


def test_raises_on_missing_required_check_param(tmp_path):
    # lte 缺少 max：若放行会与 float('inf') 比较而永远通过（静默放行），必须在加载时拒绝
    text = VALID_POLICY_YAML.format(version="1.0.0").replace(
        "check: {type: allowlist, path: applicant.region, values: [hk]}",
        "check: {type: lte, path: retention_days}",
    )
    (tmp_path / "policy-1.0.0.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="缺少必填参数 'max'"):
        load_policy(tmp_path)


def test_raises_on_empty_values_list(tmp_path):
    bad = VALID_POLICY_YAML.replace("values: [hk]", "values: []")
    write_policy(tmp_path, "1.0.0", text=bad)

    with pytest.raises(PolicyValidationError, match="values 不能为空"):
        load_policy(tmp_path)


def test_raises_on_malformed_when_guard(tmp_path):
    # when 缺少 contains：若放行会使证据规则静默失效（fail-open），必须加载时拒绝
    text = VALID_POLICY_YAML.format(version="1.0.0").replace(
        "check: {type: allowlist, path: applicant.region, values: [hk]}",
        "check: {type: evidence_present, evidence_types: [consent_record], when: {path: data_types}}",
    )
    (tmp_path / "policy-1.0.0.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="when 守卫"):
        load_policy(tmp_path)


def test_raises_on_invalid_version_format(tmp_path):
    write_policy(tmp_path, "1.0.0", text=VALID_POLICY_YAML.replace('version: "{version}"', 'version: "1.0.0-rc1"'))

    with pytest.raises(PolicyValidationError, match="版本号"):
        load_policy(tmp_path)


def test_explicit_version_ignores_unrelated_broken_file(tmp_path):
    """草稿损坏文件不应影响显式指定的完好版本。"""
    write_policy(tmp_path, "1.0.0")
    (tmp_path / "draft.yaml").write_text(": broken: [unclosed", encoding="utf-8")

    policy = load_policy(tmp_path, version="1.0.0")

    assert policy.version == "1.0.0"


def test_latest_version_fails_loud_on_broken_file(tmp_path):
    """取最新版本时目录中损坏文件必须显式报错（部署问题不可静默）。"""
    write_policy(tmp_path, "1.0.0")
    (tmp_path / "draft.yaml").write_text(": broken: [unclosed", encoding="utf-8")

    with pytest.raises(PolicyValidationError):
        load_policy(tmp_path)


def test_raises_on_missing_check_type(tmp_path):
    raw = yaml.safe_load(VALID_POLICY_YAML.format(version="1.0.0"))
    del raw["rules"][0]["check"]["type"]
    (tmp_path / "policy-1.0.0.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="结构不合法"):
        load_policy(tmp_path)


def test_list_policies_sorted_desc(tmp_path):
    write_policy(tmp_path, "1.0.0")
    write_policy(tmp_path, "1.2.0")

    listing = list_policies(tmp_path)

    assert [p["version"] for p in listing] == ["1.2.0", "1.0.0"]
    assert listing[0]["rules_count"] == 1
