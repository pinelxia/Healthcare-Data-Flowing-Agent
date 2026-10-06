"""FastAPI 集成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from compliance_agent.api.app import create_app
from compliance_agent.config import AppConfig
from tests.conftest import make_application

ALLOW_APP = make_application()
DENY_APP = make_application(purpose="marketing", retention_days=400)


@pytest.fixture
def client(repo_kb: Path) -> TestClient:
    app = create_app(AppConfig(kb_dir=repo_kb, llm_provider="null"))
    return TestClient(app)


def test_health(client):
    response = client.get("/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["metadata"]["engine"] == "deterministic"


def test_policies_lists_versions(client):
    response = client.get("/v1/policies")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    versions = [p["version"] for p in body["data"]["policies"]]
    assert "1.0.0" in versions


def test_assess_allow(client):
    response = client.post("/v1/assess", json=ALLOW_APP.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["verdict"] == "allow"
    assert body["data"]["policy_version"] == "1.0.0"
    assert len(body["data"]["matched_rules"]) > 0
    assert body["metadata"]["engine"] == "deterministic"


def test_assess_deny(client):
    response = client.post("/v1/assess", json=DENY_APP.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["verdict"] == "deny"
    violated = [r["rule_id"] for r in body["data"]["matched_rules"] if r["status"] == "violated"]
    assert "PUR-001" in violated


def test_assess_with_use_llm_false(client):
    response = client.post(
        "/v1/assess",
        json=ALLOW_APP.model_dump(mode="json"),
        params={"use_llm": "false"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["llm_used"] is False


def test_assess_rejects_unknown_field_with_envelope(client):
    payload = ALLOW_APP.model_dump(mode="json")
    payload["sneaky_extra"] = "x"

    response = client.post("/v1/assess", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "校验失败" in body["error"]


def test_assess_rejects_missing_required_field_with_envelope(client):
    payload = ALLOW_APP.model_dump(mode="json")
    del payload["purpose"]

    response = client.post("/v1/assess", json=payload)

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_assess_unknown_policy_version_returns_404_envelope(client):
    payload = ALLOW_APP.model_dump(mode="json")
    payload["policy_version"] = "0.0.1"

    response = client.post("/v1/assess", json=payload)

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert "0.0.1" in body["error"]
