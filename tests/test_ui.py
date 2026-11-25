from __future__ import annotations

from fastapi.testclient import TestClient


def test_index_renders_upload_and_guidance(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "문서 업로드" in response.text
    assert "자동 승인 없음" in response.text


def test_detail_page_shows_evidence_and_rule(client: TestClient, demo_bytes) -> None:
    created = client.post(
        "/api/documents", files={"file": ("DEMO-0002.txt", demo_bytes("DEMO-0002.txt"))}
    ).json()
    document_id = created["document"]["id"]

    response = client.get(f"/documents/{document_id}")
    assert response.status_code == 200
    html = response.text
    assert "LINE_TOTAL_MISMATCH" in html
    assert "status-HOLD" in html
    assert "<mark>" in html
    assert "원문 확인" in html
    assert "검증된 근거 span" in html


def test_form_upload_redirects(client: TestClient, demo_bytes) -> None:
    response = client.post(
        "/upload",
        files={"file": ("DEMO-0001.txt", demo_bytes("DEMO-0001.txt"))},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/documents/")

    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "검토 대기" in detail.text


def test_form_decision_requires_reason(client: TestClient, demo_bytes) -> None:
    created = client.post(
        "/api/documents", files={"file": ("DEMO-0001.txt", demo_bytes("DEMO-0001.txt"))}
    ).json()
    document_id = created["document"]["id"]

    response = client.post(
        f"/documents/{document_id}/decision",
        data={"decision": "APPROVE", "reviewer_alias": "reviewer-a", "reason": "   "},
    )
    assert response.status_code == 422
    assert "사유는 필수" in response.text


def test_form_hold_approval_is_blocked(client: TestClient, demo_bytes) -> None:
    created = client.post(
        "/api/documents", files={"file": ("DEMO-0002.txt", demo_bytes("DEMO-0002.txt"))}
    ).json()
    document_id = created["document"]["id"]

    response = client.post(
        f"/documents/{document_id}/decision",
        data={"decision": "APPROVE", "reviewer_alias": "reviewer-a", "reason": "그냥 승인"},
    )
    assert response.status_code == 409
    assert "재검증" in response.text


def test_uploaded_html_is_escaped(client: TestClient) -> None:
    text = (
        "[거래명세서]\n"
        "거래처: <script>alert(1)</script>\n"
        "문서번호: TX-2026-7777\n"
        "작성일자: 2026-05-05\n"
        "\n"
        "품목명        수량        단가        금액\n"
        "테스트 품목     2        1,000       2,000\n"
        "\n"
        "공급가액: 2,000\n"
        "부가세: 200\n"
        "총액: 2,200\n"
    ).encode()
    created = client.post("/api/documents", files={"file": ("xss.txt", text)}).json()
    assert created["document"]["status"] == "HOLD"

    html = client.get(f"/documents/{created['document']['id']}").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_evaluation_page_without_report(client: TestClient) -> None:
    response = client.get("/evaluation")
    assert response.status_code == 200
    assert "아직 리포트가 없습니다" in response.text
