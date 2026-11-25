from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.services.review import ReviewService


def upload(client: TestClient, name: str, data: bytes):
    return client.post("/api/documents", files={"file": (name, data, "text/plain")})


def test_audit_is_append_only_at_database_level(client: TestClient, settings, demo_bytes) -> None:
    detail = upload(client, "DEMO-0001.txt", demo_bytes("DEMO-0001.txt")).json()
    document_id = detail["document"]["id"]

    db = Database(settings.db_path)
    with pytest.raises(sqlite3.DatabaseError), db.transaction() as connection:
        connection.execute(
            "UPDATE audit_events SET actor = 'tampered' WHERE document_id = ?",
            (document_id,),
        )
    with pytest.raises(sqlite3.DatabaseError), db.transaction() as connection:
        connection.execute("DELETE FROM audit_events WHERE document_id = ?", (document_id,))

    with db.read() as connection:
        actors = [
            row["actor"]
            for row in connection.execute(
                "SELECT actor FROM audit_events WHERE document_id = ? ORDER BY id", (document_id,)
            )
        ]
    assert actors == ["system", "system"]


def test_validation_issues_are_resolved_not_deleted_on_revalidate(
    client: TestClient, settings, demo_bytes
) -> None:
    first = upload(client, "DEMO-0003.txt", demo_bytes("DEMO-0003.txt")).json()
    second = upload(client, "DEMO-0004.txt", demo_bytes("DEMO-0004.txt")).json()

    client.post(
        f"/api/documents/{first['document']['id']}/decision",
        json={"decision": "REJECT", "reviewer_alias": "reviewer-a", "reason": "정정"},
    )
    client.post(f"/api/documents/{second['document']['id']}/revalidate")

    db = Database(settings.db_path)
    with db.read() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM validation_issues "
            "WHERE document_id = ? GROUP BY status",
            (second["document"]["id"],),
        ).fetchall()
    counts = {row["status"]: row["count"] for row in rows}
    assert counts.get("resolved") == 1
    assert "open" not in counts


def test_state_machine_rejects_unknown_status(client: TestClient) -> None:
    response = client.get("/api/documents", params={"status": "APPROVED_BY_AI"})
    assert response.status_code == 422


def test_service_requires_existing_document(app, settings) -> None:
    service: ReviewService = app.state.service
    from app.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.get("missing")
    with pytest.raises(NotFoundError):
        service.revalidate("missing")


def test_audit_metadata_records_versions(client: TestClient, demo_bytes) -> None:
    detail = upload(client, "DEMO-0001.txt", demo_bytes("DEMO-0001.txt")).json()
    metadata = detail["audit"][1]["metadata"]
    assert metadata["extractor_version"] == detail["document"]["extractor_version"]
    assert metadata["ruleset_version"] == detail["document"]["ruleset_version"]
    assert metadata["issue_count"] == 0
