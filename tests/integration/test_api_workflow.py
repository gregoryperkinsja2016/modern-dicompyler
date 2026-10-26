"""Integration tests for the FastAPI workflow (SQLite-backed)."""
from __future__ import annotations

from sqlalchemy import select

from src.db import get_session
from src.models import AnalysisRecord, AuditEvent


def _run_demo(client):
    response = client.post("/api/v1/demo-case")
    assert response.status_code == 201, response.text
    return response.json()


def test_demo_case_creates_analysis_and_audit_record(client):
    payload = _run_demo(client)
    analysis_id = payload["analysis_id"]
    assert payload["rt_object_type"] == "DEMO_CASE"
    assert payload["status"] == "completed"
    assert payload["source"] == "demo_case"
    result = payload["result"]
    assert result["plan"] is not None
    assert result["structures"] is not None
    assert result["dose"] is not None

    with get_session() as session:
        record = session.get(AnalysisRecord, analysis_id)
        assert record is not None
        assert record.rt_object_type == "DEMO_CASE"
        assert record.trace_id
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.analysis_id == analysis_id)
        ).all()
        assert len(events) >= 1
        assert any(event.event_type == "ANALYSIS_CREATED" for event in events)


def test_demo_case_plan_endpoint_returns_beam_data(client):
    response = client.get("/api/v1/demo-case/plan")
    assert response.status_code == 200
    payload = response.json()
    assert payload["rt_object_type"] == "RTPLAN"
    assert payload["source"] == "demo_case"
    beams = payload["plan"]["beams"]
    assert len(beams) == 2
    assert beams[0]["beam_number"] == 1
    assert beams[0]["gantry_angle"] == 0.0
    assert beams[1]["gantry_angle"] == 90.0
    assert beams[0]["treatment_machine_name"] == "SYNTH-LINAC-01"
    assert beams[0]["nominal_beam_energy"] == 6.0
    assert beams[0]["referenced_beam_number"] == 1
    assert beams[0]["beam_dose"] == 1.0


def test_analysis_history_returns_persisted_records(client):
    created_id = _run_demo(client)["analysis_id"]
    response = client.get("/api/v1/analyses", params={"page": 1, "page_size": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert len(payload["items"]) <= 5
    ids = [item["analysis_id"] for item in payload["items"]]
    assert created_id in ids
    item = next(item for item in payload["items"] if item["analysis_id"] == created_id)
    assert item["rt_object_type"] == "DEMO_CASE"
    assert item["status"] == "completed"


def test_repeated_demo_runs_create_separate_records(client):
    with get_session() as session:
        before = len(session.scalars(select(AnalysisRecord)).all())
    first = _run_demo(client)
    second = _run_demo(client)
    assert first["analysis_id"] != second["analysis_id"]
    with get_session() as session:
        after = len(session.scalars(select(AnalysisRecord)).all())
    assert after - before == 2


def test_get_single_analysis_and_structured_404(client):
    created_id = _run_demo(client)["analysis_id"]
    found = client.get(f"/api/v1/analyses/{created_id}")
    assert found.status_code == 200
    assert found.json()["result"]["plan"]["plan_label"] == "SYNTH-PLAN-01"
    assert found.json()["audit_events"]

    missing = client.get("/api/v1/analyses/does-not-exist")
    assert missing.status_code == 404
    error = missing.json()["error"]
    assert error["class"] == "NotFoundError"
    assert "trace_id" in error


def test_analysis_plan_endpoint_returns_available_plan(client):
    created_id = _run_demo(client)["analysis_id"]
    response = client.get(f"/api/v1/analyses/{created_id}/plan")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["plan"]["beams"]


def test_invalid_upload_returns_structured_400(client):
    response = client.post(
        "/api/v1/analyses",
        files={"file": ("garbage.dcm", b"not a dicom file", "application/dicom")},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["class"] == "InvalidDICOMError"
    assert error["message"]
    assert "trace_id" in error


def test_unsupported_upload_returns_structured_400(client, ct_bytes):
    response = client.post(
        "/api/v1/analyses",
        files={"file": ("ct.dcm", ct_bytes, "application/dicom")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["class"] == "UnsupportedRTObjectError"


def test_uploaded_rtplan_is_parsed_and_persisted(client, rtplan_bytes):
    response = client.post(
        "/api/v1/analyses",
        files={"file": ("plan.dcm", rtplan_bytes, "application/dicom")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["rt_object_type"] == "RTPLAN"
    assert payload["result"]["plan"]["beams"][0]["beam_name"] == "SYNTH-BEAM-01"
    with get_session() as session:
        record = session.get(AnalysisRecord, payload["analysis_id"])
        assert record is not None
        assert record.status == "completed"
        assert record.rt_object_type == "RTPLAN"


def test_failed_upload_is_persisted_for_audit(client):
    response = client.post(
        "/api/v1/analyses",
        files={"file": ("bad.dcm", b"garbage", "application/dicom")},
    )
    assert response.status_code == 400
    history = client.get("/api/v1/analyses", params={"page": 1, "page_size": 100})
    items = history.json()["items"]
    failed = [item for item in items if item["status"] == "failed"]
    assert failed, "a failed parse attempt must be persisted for audit"


def test_health_endpoint_checks_database_connectivity(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] is True
    assert payload["version"]
    assert payload["time"]


def test_metrics_endpoint_exposes_expected_metric_names(client):
    _run_demo(client)
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "rtqa_analysis_requests_total" in body
    assert "rtqa_analysis_duration_seconds" in body
    assert "rtqa_analysis_failures_total" in body
    assert "rtqa_database_up" in body
