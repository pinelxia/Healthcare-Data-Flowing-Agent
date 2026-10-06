"""七种确定性检查类型的单元测试。"""

from __future__ import annotations

import pytest

from compliance_agent.engine.checks import run_check
from compliance_agent.engine.policy import PolicyValidationError
from compliance_agent.models import CheckSpec
from tests.conftest import make_application

APP = make_application()


def spec(**kwargs) -> CheckSpec:
    return CheckSpec(**kwargs)


def test_allowlist_passes_when_value_in_list():
    result = run_check(spec(type="allowlist", path="purpose", values=["claim", "medical_report"]), APP)
    assert result.status == "pass"


def test_allowlist_fails_when_value_outside_list():
    app = make_application(purpose="marketing")
    result = run_check(spec(type="allowlist", path="purpose", values=["claim"]), app)
    assert result.status == "fail"
    assert "marketing" in result.actual


def test_allowlist_fails_when_field_missing():
    app = make_application().model_copy()
    app.applicant = app.applicant.model_copy(update={"region": None})  # type: ignore[arg-type]
    result = run_check(spec(type="allowlist", path="applicant.region", values=["hk"]), app)
    assert result.status == "fail"
    assert result.actual == "字段缺失"


def test_allowlist_fails_when_path_does_not_exist():
    result = run_check(spec(type="allowlist", path="no.such.field", values=["x"]), APP)
    assert result.status == "fail"
    assert result.actual == "字段缺失"


def test_subset_passes_when_all_items_allowed():
    result = run_check(
        spec(type="subset", path="data_types", values=["diagnosis_summary", "cost_detail", "claim_certificate"]),
        APP,
    )
    assert result.status == "pass"


def test_subset_fails_when_any_item_outside_list():
    app = make_application(data_types=["diagnosis_summary", "genome_data"])
    result = run_check(spec(type="subset", path="data_types", values=["diagnosis_summary"]), app)
    assert result.status == "fail"
    assert "genome_data" in result.actual


def test_fields_within_passes_when_field_allowed_for_requested_type():
    result = run_check(
        spec(
            type="fields_within",
            path="data_fields",
            per_type={"diagnosis_summary": ["patient_name", "visit_date", "diagnosis_summary"]},
        ),
        make_application(data_types=["diagnosis_summary"], data_fields=["patient_name"]),
    )
    assert result.status == "pass"


def test_fields_within_fails_when_field_not_in_any_requested_type_allowlist():
    result = run_check(
        spec(
            type="fields_within",
            path="data_fields",
            per_type={"diagnosis_summary": ["patient_name"]},
        ),
        make_application(data_types=["diagnosis_summary"], data_fields=["raw_medical_record"]),
    )
    assert result.status == "fail"
    assert "raw_medical_record" in result.actual


def test_lte_passes_when_value_within_limit():
    assert run_check(spec(type="lte", path="retention_days", max=180), APP).status == "pass"


def test_lte_fails_when_value_exceeds_limit():
    result = run_check(spec(type="lte", path="retention_days", max=180), make_application(retention_days=365))
    assert result.status == "fail"
    assert "365" in result.actual


def test_lte_fails_when_field_missing():
    result = run_check(spec(type="lte", path="no.such.field", max=10), APP)
    assert result.status == "fail"


def test_date_within_passes_within_window():
    result = run_check(
        spec(type="date_within", path="requested_until", anchor="submitted_at", min_days=0, max_days=90),
        APP,
    )
    assert result.status == "pass"


def test_date_within_fails_beyond_max_window():
    result = run_check(
        spec(type="date_within", path="requested_until", anchor="submitted_at", max_days=90),
        make_application(requested_until=__import__("datetime").date(2027, 6, 1)),
    )
    assert result.status == "fail"
    assert "238 天" in result.actual


def test_date_within_fails_when_before_anchor():
    result = run_check(
        spec(type="date_within", path="requested_until", anchor="submitted_at", min_days=0, max_days=90),
        make_application(requested_until=__import__("datetime").date(2026, 9, 1)),
    )
    assert result.status == "fail"


def test_evidence_present_passes_when_evidence_provided():
    result = run_check(
        spec(type="evidence_present", evidence_types=["consent_record"]),
        APP,
    )
    assert result.status == "pass"
    assert result.evidence_used[0].type == "consent_record"
    assert result.evidence_used[0].reference == "CONSENT-001"


def test_evidence_present_missing_when_evidence_absent():
    app = make_application(evidence=[])
    result = run_check(spec(type="evidence_present", evidence_types=["consent_record"]), app)
    assert result.status == "missing"
    assert "consent_record" in result.actual


def test_evidence_present_treats_present_false_as_missing():
    from compliance_agent.models import Evidence

    app = make_application(evidence=[Evidence(type="consent_record", present=False)])
    result = run_check(spec(type="evidence_present", evidence_types=["consent_record"]), app)
    assert result.status == "missing"


def test_evidence_present_not_applicable_when_when_condition_unmet():
    app = make_application(data_types=["cost_detail"])
    result = run_check(
        spec(
            type="evidence_present",
            evidence_types=["consent_record"],
            when={"path": "data_types", "contains": "diagnosis_summary"},
        ),
        app,
    )
    assert result.status == "not_applicable"


def test_condition_triggers_when_all_conditions_hold():
    result = run_check(
        spec(
            type="condition",
            all_of=[
                {"path": "data_types", "op": "contains", "value": "diagnosis_summary"},
                {"path": "retention_days", "op": "gt", "value": 30},
            ],
        ),
        make_application(retention_days=60),
    )
    assert result.status == "fail"  # 条件命中即触发（映射到 manual_review）
    assert result.actual.startswith("命中条件")


def test_condition_not_applicable_when_any_condition_false():
    result = run_check(
        spec(
            type="condition",
            all_of=[
                {"path": "data_types", "op": "contains", "value": "diagnosis_summary"},
                {"path": "retention_days", "op": "gt", "value": 30},
            ],
        ),
        APP,  # retention_days=30，不满足 gt 30
    )
    assert result.status == "not_applicable"


def test_condition_unknown_operator_raises():
    with pytest.raises(PolicyValidationError, match="未知条件操作符"):
        run_check(spec(type="condition", all_of=[{"path": "purpose", "op": "magic", "value": "x"}]), APP)


def test_unknown_check_type_raises():
    with pytest.raises(PolicyValidationError, match="未知检查类型"):
        run_check(spec(type="nope"), APP)
