"""输入边界约束测试：fail fast，拒绝静默通过。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from compliance_agent.models import SubscriptionApplication
from tests.conftest import make_application


def test_rejects_negative_retention_days():
    with pytest.raises(ValidationError):
        make_application(retention_days=-5)


def test_rejects_boolean_retention_days():
    """YAML 的 yes/no 会被解析为 bool，strict 模式必须拒绝。"""
    with pytest.raises(ValidationError):
        make_application(retention_days=True)  # type: ignore[arg-type]


def test_rejects_empty_data_types():
    with pytest.raises(ValidationError):
        make_application(data_types=[])


def test_rejects_empty_data_fields():
    with pytest.raises(ValidationError):
        make_application(data_fields=[])


def test_rejects_unknown_field():
    with pytest.raises(ValidationError):
        make_application(sneaky_field="x")  # type: ignore[call-arg]


def test_naive_datetime_is_normalized_to_utc():
    app = make_application(submitted_at=datetime(2026, 10, 6, 9, 0, 0))

    assert app.submitted_at.tzinfo == timezone.utc


def test_aware_datetime_keeps_its_timezone():
    submitted = datetime(2026, 10, 6, 9, 0, 0, tzinfo=timezone.utc)
    app = make_application(submitted_at=submitted)

    assert app.submitted_at == submitted


def test_application_roundtrip_through_json():
    app = make_application()
    raw = app.model_dump(mode="json")

    restored = SubscriptionApplication.model_validate(raw)

    assert restored == app


def test_requested_until_is_date_not_datetime():
    app = make_application()

    assert isinstance(app.requested_until, date)
    assert not isinstance(app.requested_until, datetime)
