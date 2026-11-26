from dataclasses import replace


def test_public_demo_allows_reads_and_blocks_mutations(client, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    read_only_app = create_app(replace(settings, public_demo_read_only=True))
    with TestClient(read_only_app) as read_only_client:
        assert read_only_client.get("/api/health").status_code == 200
        response = read_only_client.post("/api/documents")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "E_PUBLIC_DEMO_READ_ONLY"
