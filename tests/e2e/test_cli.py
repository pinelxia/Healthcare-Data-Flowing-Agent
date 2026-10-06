"""CLI 端到端测试：直接调用 main()（capsys 捕获输出）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compliance_agent.cli import EXIT_ERROR, EXIT_OK, main
from tests.conftest import REPO_ROOT

SAMPLES_DIR = REPO_ROOT / "samples"


@pytest.fixture(autouse=True)
def isolate_llm_env(monkeypatch):
    """隔离宿主环境：CLI 测试绝不触达真实 DeepSeek API。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("COMPLIANCE_LLM_PROVIDER", "null")


def run_cli(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_assess_allow_sample(capsys):
    code, out, _ = run_cli(capsys, "assess", "--application", str(SAMPLES_DIR / "app_allow.yaml"))

    assert code == EXIT_OK
    report = json.loads(out)
    assert report["verdict"] == "allow"
    assert report["policy_version"] == "1.0.0"


def test_assess_manual_review_sample(capsys):
    code, out, _ = run_cli(capsys, "assess", "--application", str(SAMPLES_DIR / "app_manual_review.yaml"))

    assert code == EXIT_OK
    report = json.loads(out)
    assert report["verdict"] == "manual_review"
    assert any("EVI-001" in m for m in report["missing_information"])


def test_assess_deny_sample(capsys):
    code, out, _ = run_cli(capsys, "assess", "--application", str(SAMPLES_DIR / "app_deny.yaml"))

    assert code == EXIT_OK
    report = json.loads(out)
    assert report["verdict"] == "deny"
    assert {r["rule_id"] for r in report["matched_rules"] if r["status"] == "violated"} >= {
        "PUR-001",
        "MIN-002",
        "RET-001",
    }


def test_assess_writes_output_file(capsys, tmp_path: Path):
    output = tmp_path / "report.json"

    code, out, _ = run_cli(
        capsys,
        "assess",
        "--application",
        str(SAMPLES_DIR / "app_allow.yaml"),
        "--output",
        str(output),
    )

    assert code == EXIT_OK
    assert f"{output}" in out
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["verdict"] == "allow"


def test_assess_no_llm_flag(capsys):
    code, out, _ = run_cli(
        capsys,
        "assess",
        "--application",
        str(SAMPLES_DIR / "app_allow.yaml"),
        "--no-llm",
    )

    assert code == EXIT_OK
    assert json.loads(out)["llm_used"] is False


def test_assess_unknown_policy_version_exits_error(capsys):
    code, _, err = run_cli(
        capsys,
        "assess",
        "--application",
        str(SAMPLES_DIR / "app_allow.yaml"),
        "--policy-version",
        "0.0.1",
    )

    assert code == EXIT_ERROR
    assert "0.0.1" in err


def test_assess_missing_file_exits_error(capsys):
    code, _, err = run_cli(capsys, "assess", "--application", "/no/such/file.yaml")

    assert code == EXIT_ERROR
    assert "无法读取" in err


def test_assess_invalid_application_exits_error(capsys, tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("purpose: 1\n", encoding="utf-8")

    code, _, err = run_cli(capsys, "assess", "--application", str(bad))

    assert code == EXIT_ERROR
    assert "不合法" in err


def test_policies_lists_versions(capsys):
    code, out, _ = run_cli(capsys, "policies")

    assert code == EXIT_OK
    listing = json.loads(out)
    assert any(p["version"] == "1.0.0" for p in listing)


def test_assess_output_to_missing_dir_exits_error(capsys):
    code, _, err = run_cli(
        capsys,
        "assess",
        "--application",
        str(SAMPLES_DIR / "app_allow.yaml"),
        "--output",
        "/no/such/dir/report.json",
    )

    assert code == EXIT_ERROR
    assert "无法写入" in err
