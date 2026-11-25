from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def upload(client: TestClient, name: str, data: bytes):
    return client.post("/api/documents", files={"file": (name, data, "text/plain")})


def test_health_and_meta(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert len(body["rules"]) == 8
    assert "MISSING_EVIDENCE" in {rule["rule_id"] for rule in body["rules"]}
    assert body["statuses"] == ["INGESTED", "PENDING_REVIEW", "HOLD", "APPROVED", "REJECTED"]


def test_upload_normal_document_is_pending_review(client: TestClient, demo_bytes) -> None:
    response = upload(client, "DEMO-0001.txt", demo_bytes("DEMO-0001.txt"))
    assert response.status_code == 201
    body = response.json()
    assert body["document"]["status"] == "PENDING_REVIEW"
    assert len(body["fields"]) == 6 + 4 * len(body["items"])
    assert body["issues"] == []
    assert len(body["items"]) >= 1
    assert [event["event_type"] for event in body["audit"]] == [
        "DOCUMENT_INGESTED",
        "VALIDATION_COMPLETED",
    ]


def test_upload_mismatch_is_hold(client: TestClient, demo_bytes) -> None:
    response = upload(client, "DEMO-0002.txt", demo_bytes("DEMO-0002.txt"))
    assert response.status_code == 201
    body = response.json()
    assert body["document"]["status"] == "HOLD"
    assert [issue["rule_id"] for issue in body["issues"]] == ["LINE_TOTAL_MISMATCH"]
    assert "총액" in body["raw_text"]


def test_list_filters_and_pagination(client: TestClient, demo_bytes) -> None:
    upload(client, "DEMO-0001.txt", demo_bytes("DEMO-0001.txt"))
    upload(client, "DEMO-0002.txt", demo_bytes("DEMO-0002.txt"))

    everything = client.get("/api/documents").json()
    assert everything["total"] == 2

    holds = client.get("/api/documents", params={"status": "HOLD"}).json()
    assert holds["total"] == 1
    assert holds["items"][0]["status"] == "HOLD"
    assert holds["items"][0]["blocking_count"] == 1
    assert holds["items"][0]["vendor"]

    assert client.get("/api/documents", params={"status": "NOPE"}).status_code == 422
    assert client.get("/api/documents", params={"limit": 0}).status_code == 422


def test_detail_and_audit_endpoints(client: TestClient, demo_bytes) -> None:
    created = upload(client, "DEMO-0001.txt", demo_bytes("DEMO-0001.txt")).json()
    document_id = created["document"]["id"]

    detail = client.get(f"/api/documents/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["document"]["sha256"] == created["document"]["sha256"]

    audit = client.get(f"/api/documents/{document_id}/audit").json()
    assert len(audit["items"]) == 2
    assert audit["items"][0]["to_status"] == "INGESTED"

    assert client.get("/api/documents/does-not-exist").status_code == 404


def test_decision_requires_alias_and_reason(client: TestClient, demo_bytes) -> None:
    detail = upload(client, "DEMO-0001.txt", demo_bytes("DEMO-0001.txt")).json()
    document_id = detail["document"]["id"]

    missing = client.post(f"/api/documents/{document_id}/decision", json={"decision": "APPROVE"})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "E_VALIDATION"

    blank = client.post(
        f"/api/documents/{document_id}/decision",
        json={"decision": "APPROVE", "reviewer_alias": "  ", "reason": "확인"},
    )
    assert blank.status_code == 422


def test_hold_cannot_be_approved_directly(client: TestClient, demo_bytes) -> None:
    detail = upload(client, "DEMO-0002.txt", demo_bytes("DEMO-0002.txt")).json()
    document_id = detail["document"]["id"]
    response = client.post(
        f"/api/documents/{document_id}/decision",
        json={"decision": "APPROVE", "reviewer_alias": "reviewer-a", "reason": "확인"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "E_CONFLICT"


def test_approve_then_terminal(client: TestClient, demo_bytes) -> None:
    detail = upload(client, "DEMO-0001.txt", demo_bytes("DEMO-0001.txt")).json()
    document_id = detail["document"]["id"]

    approved = client.post(
        f"/api/documents/{document_id}/decision",
        json={
            "decision": "APPROVE",
            "reviewer_alias": " reviewer-a ",
            "reason": " 원문 대조 완료 ",
        },
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["document"]["status"] == "APPROVED"
    assert body["decisions"][0]["reviewer_alias"] == "reviewer-a"
    assert body["decisions"][0]["reason"] == "원문 대조 완료"
    assert body["audit"][-1]["event_type"] == "DECISION_RECORDED"

    again = client.post(
        f"/api/documents/{document_id}/decision",
        json={"decision": "REJECT", "reviewer_alias": "reviewer-b", "reason": "뒤늦은 반려"},
    )
    assert again.status_code == 409

    revalidate = client.post(f"/api/documents/{document_id}/revalidate")
    assert revalidate.status_code == 409


def test_duplicate_then_reject_original_allows_revalidate(client: TestClient, demo_bytes) -> None:
    first = upload(client, "DEMO-0003.txt", demo_bytes("DEMO-0003.txt")).json()
    second = upload(client, "DEMO-0004.txt", demo_bytes("DEMO-0004.txt")).json()
    assert first["document"]["status"] == "PENDING_REVIEW"
    assert second["document"]["status"] == "HOLD"
    assert second["document"]["duplicate_of"] == first["document"]["id"]
    assert [issue["rule_id"] for issue in second["issues"]] == ["DUPLICATE_DOCUMENT"]

    rejected = client.post(
        f"/api/documents/{first['document']['id']}/decision",
        json={"decision": "REJECT", "reviewer_alias": "reviewer-a", "reason": "중복 원본 정정"},
    )
    assert rejected.status_code == 200

    revalidated = client.post(f"/api/documents/{second['document']['id']}/revalidate")
    assert revalidated.status_code == 200
    body = revalidated.json()
    assert body["document"]["status"] == "PENDING_REVIEW"
    assert body["document"]["duplicate_of"] is None
    assert body["issues"] == []
    assert body["audit"][-1]["event_type"] == "REVALIDATED"
    assert body["audit"][-1]["from_status"] == "HOLD"
    assert body["audit"][-1]["to_status"] == "PENDING_REVIEW"


def test_unsupported_file_type(client: TestClient) -> None:
    response = client.post(
        "/api/documents", files={"file": ("notes.md", b"hello", "text/markdown")}
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "E_UNSUPPORTED_FILE"


def test_invalid_utf8_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/documents", files={"file": ("bad.txt", b"\xff\xfe\x00bad", "text/plain")}
    )
    assert response.status_code == 415


def test_body_too_large(settings: Settings) -> None:
    from dataclasses import replace

    tiny = replace(settings, db_path=settings.db_path.parent / "tiny.db", max_upload_bytes=512)
    with TestClient(create_app(tiny)) as client:
        response = client.post(
            "/api/documents", files={"file": ("big.txt", b"x" * 4096, "text/plain")}
        )
    assert response.status_code == 413


def test_evaluation_report_404_before_generation(client: TestClient) -> None:
    response = client.get("/api/evaluation/latest")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "E_NOT_FOUND"


def test_security_headers(client: TestClient) -> None:
    response = client.get("/")
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_unknown_api_route_returns_404(client: TestClient) -> None:
    assert client.get("/api/nope").status_code == 404


@pytest.mark.parametrize("path", ["/", "/evaluation"])
def test_pages_render(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200
