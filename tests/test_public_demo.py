from dataclasses import replace


def test_public_demo_allows_reads_and_blocks_mutations(client, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    read_only_app = create_app(replace(settings, public_demo_read_only=True))
    with TestClient(read_only_app) as read_only_client:
        assert read_only_client.get("/api/health").status_code == 200
        documents = read_only_client.get("/api/documents")
        assert documents.status_code == 200
        assert documents.json()["total"] == 4
        page = read_only_client.get("/")
        assert "공개 읽기 전용 데모" in page.text
        assert 'action="/upload"' not in page.text
        document_id = documents.json()["items"][0]["id"]
        detail = read_only_client.get(f"/documents/{document_id}")
        assert detail.status_code == 200
        assert "공개 데모에서는 판정할 수 없습니다" in detail.text
        assert "/corrections\" method=\"post\"" not in detail.text
        assert "/decision\" method=\"post\"" not in detail.text
        response = read_only_client.post("/api/documents")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "E_PUBLIC_DEMO_READ_ONLY"
