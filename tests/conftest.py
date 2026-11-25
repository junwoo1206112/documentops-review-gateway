from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


def read_doc(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.db",
        vendor_registry_path=PROJECT_ROOT / "fixtures" / "vendors.json",
        evaluation_dir=PROJECT_ROOT / "fixtures" / "evaluation",
        demo_dir=PROJECT_ROOT / "fixtures" / "demo",
        artifacts_dir=tmp_path / "artifacts",
        rate_limit_per_minute=0,
    )


@pytest.fixture()
def tiny_settings(settings: Settings, tmp_path: Path) -> Settings:
    return replace(settings, db_path=tmp_path / "tiny.db", max_upload_bytes=512)


@pytest.fixture()
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def demo_bytes(project_root: Path):
    def load(name: str) -> bytes:
        return (project_root / "fixtures" / "demo" / name).read_bytes()

    return load


def upload(client: TestClient, name: str, data: bytes):
    return client.post("/api/documents", files={"file": (name, data, "text/plain")})
