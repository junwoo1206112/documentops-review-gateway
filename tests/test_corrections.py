"""Phase 14: 원문 재인용 기반 필드 수정.

검증하는 계약
- 원문에 있는 값만 수정할 수 있다(재인용 필수).
- 수정은 추출값을 덮어쓰지 않고, 재검증을 거치며 자동 승인하지 않는다.
- 수정 이력은 append-only이고, 문서 상세에 노출된다.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import Database

BASE = """[거래명세서]
거래처: {vendor}
문서번호: TX-2026-5001
작성일자: {date}

품목명                수량        단가          금액
테스트 볼트            10        1,000       10,000

공급가액: 10,000
부가세: 1,000
총액: {total}
"""


def upload_text(client: TestClient, text: str, name: str = "correction.txt") -> dict:
    response = client.post(
        "/api/documents", files={"file": (name, text.encode("utf-8"), "text/plain")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def correct(client: TestClient, document_id: str, **payload) -> dict:
    body = {
        "path": "vendor",
        "value": "가온상사",
        "excerpt": "가온상사",
        "reviewer_alias": "reviewer-a",
        "reason": "원문 표기 대조",
    }
    body.update(payload)
    return client.post(f"/api/documents/{document_id}/corrections", json=body)


def test_quote_backed_correction_resolves_unknown_vendor_and_requires_decision(
    client: TestClient,
) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    document_id = created["document"]["id"]
    assert created["document"]["status"] == "HOLD"
    assert [issue["rule_id"] for issue in created["issues"]] == ["UNKNOWN_VENDOR"]

    response = correct(client, document_id)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["document"]["status"] == "PENDING_REVIEW"
    assert body["issues"] == []
    assert len(body["corrections"]) == 1

    extracted = next(field for field in body["fields"] if field["path"] == "vendor")
    assert extracted["value"] == "가온상사(주)"  # 추출값은 덮어쓰지 않는다
    assert extracted["corrected"] is False

    correction = body["corrections"][0]
    assert correction["path"] == "vendor"
    assert correction["from_value"] == "가온상사(주)"
    assert correction["to_value"] == "가온상사"
    assert correction["evidence_excerpt"] == "가온상사"
    assert correction["reviewer_alias"] == "reviewer-a"

    vendor = next(field for field in body["effective_fields"] if field["path"] == "vendor")
    assert vendor["value"] == "가온상사"
    assert vendor["corrected"] is True
    assert vendor["original_value"] == "가온상사(주)"
    assert vendor["evidence_status"] == "verified"
    assert body["raw_text"][vendor["char_start"] : vendor["char_end"]] == "가온상사"

    event_types = [event["event_type"] for event in body["audit"]]
    assert event_types[-2:] == ["CORRECTION_RECORDED", "REVALIDATED"]
    assert body["audit"][-1]["from_status"] == "HOLD"
    assert body["audit"][-1]["to_status"] == "PENDING_REVIEW"
    assert body["decisions"] == []

    approved = client.post(
        f"/api/documents/{document_id}/decision",
        json={"decision": "APPROVE", "reviewer_alias": "reviewer-a", "reason": "원문 대조 완료"},
    )
    assert approved.status_code == 200
    assert approved.json()["document"]["status"] == "APPROVED"


def test_money_correction_normalizes_commas(client: TestClient) -> None:
    text = BASE.format(vendor="가온상사", date="2026-06-01", total="11,100")
    text = text.replace("총액: 11,100", "총액: 11,100\n※ 정정 전 표기 11,000")
    created = upload_text(client, text)
    document_id = created["document"]["id"]
    assert [issue["rule_id"] for issue in created["issues"]] == ["LINE_TOTAL_MISMATCH"]

    response = correct(
        client,
        document_id,
        path="total",
        value="11,000",
        excerpt="11,000",
        reason="정정 전 표기와 대조",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document"]["status"] == "PENDING_REVIEW"
    total = next(field for field in body["effective_fields"] if field["path"] == "total")
    assert total["value"] == 11000


def test_date_correction_requires_valid_iso_quote(client: TestClient) -> None:
    text = BASE.format(vendor="가온상사", date="2026.06.01", total="11,000")
    text = text.replace("총액: 11,000", "총액: 11,000\n※ 발행일 2026-06-01")
    created = upload_text(client, text)
    document_id = created["document"]["id"]
    assert [issue["rule_id"] for issue in created["issues"]] == ["INVALID_DATE"]

    response = correct(
        client,
        document_id,
        path="doc_date",
        value="2026-06-01",
        excerpt="2026-06-01",
        reason="발행일 주석 대조",
    )
    assert response.status_code == 201, response.text
    assert response.json()["document"]["status"] == "PENDING_REVIEW"


def test_correction_without_quote_is_rejected(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    response = correct(client, created["document"]["id"], excerpt="")
    assert response.status_code == 422
    assert "재인용" in response.json()["error"]["message"]


def test_correction_quote_must_exist_in_original(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    response = correct(client, created["document"]["id"], excerpt="없는상사")
    assert response.status_code == 422
    assert "찾을 수 없습니다" in response.json()["error"]["message"]


def test_correction_value_must_match_quote(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    response = correct(client, created["document"]["id"], value="누리기계", excerpt="가온상사")
    assert response.status_code == 422
    assert "일치하지 않습니다" in response.json()["error"]["message"]


def test_ambiguous_quote_requires_explicit_span(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    document_id = created["document"]["id"]
    # "1,000"은 단가와 부가세 두 곳에 나타난다.
    ambiguous = correct(
        client,
        document_id,
        path="vat",
        value="1,000",
        excerpt="1,000",
        reason="부가세 확인",
    )
    assert ambiguous.status_code == 422
    assert "여러 번" in ambiguous.json()["error"]["message"]

    text = created["raw_text"]
    vat_start = text.rindex("1,000")
    with_span = correct(
        client,
        document_id,
        path="vat",
        value="1,000",
        excerpt=None,
        char_start=vat_start,
        char_end=vat_start + len("1,000"),
        reason="부가세 위치 지정",
    )
    assert with_span.status_code == 201, with_span.text


def test_missing_field_cannot_be_invented(client: TestClient) -> None:
    text = "\n".join(
        line
        for line in BASE.format(vendor="가온상사", date="2026-06-01", total="11,000").splitlines()
        if not line.startswith("거래처:")
    )
    created = upload_text(client, text)
    assert [issue["rule_id"] for issue in created["issues"]] == ["MISSING_REQUIRED"]

    response = correct(client, created["document"]["id"])
    assert response.status_code == 422
    assert "찾을 수 없습니다" in response.json()["error"]["message"]


def test_terminal_document_cannot_be_corrected(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    document_id = created["document"]["id"]
    rejected = client.post(
        f"/api/documents/{document_id}/decision",
        json={"decision": "REJECT", "reviewer_alias": "reviewer-a", "reason": "원본 폐기"},
    )
    assert rejected.status_code == 200

    response = correct(client, document_id)
    assert response.status_code == 409


def test_correction_history_is_append_only(client: TestClient, settings) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    document_id = created["document"]["id"]
    assert correct(client, document_id).status_code == 201

    db = Database(settings.db_path)
    with pytest.raises(sqlite3.DatabaseError), db.transaction() as connection:
        connection.execute(
            "UPDATE field_corrections SET to_value_json = '\"변조\"' WHERE document_id = ?",
            (document_id,),
        )
    with pytest.raises(sqlite3.DatabaseError), db.transaction() as connection:
        connection.execute("DELETE FROM field_corrections WHERE document_id = ?", (document_id,))


def test_revalidate_preserves_correction(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    document_id = created["document"]["id"]
    assert correct(client, document_id).status_code == 201

    revalidated = client.post(f"/api/documents/{document_id}/revalidate")
    assert revalidated.status_code == 200
    body = revalidated.json()
    assert body["document"]["status"] == "PENDING_REVIEW"
    assert len(body["corrections"]) == 1
    vendor = next(field for field in body["effective_fields"] if field["path"] == "vendor")
    assert vendor["value"] == "가온상사"


def test_unsupported_correction_path_is_rejected(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    response = correct(client, created["document"]["id"], path="items[0].qty")
    assert response.status_code == 422
    assert "수정할 수 없는 필드" in response.json()["error"]["message"]


def test_correction_requires_alias_and_reason(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    no_reason = correct(client, created["document"]["id"], reason="  ")
    assert no_reason.status_code == 422
    assert no_reason.json()["error"]["code"] == "E_VALIDATION"


def test_correction_form_renders_and_posts(client: TestClient) -> None:
    created = upload_text(
        client, BASE.format(vendor="가온상사(주)", date="2026-06-01", total="11,000")
    )
    document_id = created["document"]["id"]

    page = client.get(f"/documents/{document_id}")
    assert page.status_code == 200
    assert "필드 수정" in page.text
    assert 'action="/documents/' in page.text
    assert "수정하고 재검증" in page.text

    response = client.post(
        f"/documents/{document_id}/corrections",
        data={
            "path": "vendor",
            "value": "가온상사",
            "excerpt": "가온상사",
            "reviewer_alias": "reviewer-a",
            "reason": "원문 재인용",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get(f"/documents/{document_id}")
    assert "필드 수정 이력" in page.text
    assert "가온상사(주) → 가온상사" in page.text
