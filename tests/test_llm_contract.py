"""Phase 17: 외부 모델 없이 provider 계약과 evidence 경계를 고정한다."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import UnprocessableError
from app.main import create_app
from app.services.extraction.base import ExtractionResult
from app.services.extraction.deterministic import parse_document
from app.services.extraction.providers import (
    ExtractionProviderError,
    OfflineLLMContractStub,
    build_extractor,
)
from app.services.pipeline import process_document
from app.services.vendors import VendorRegistry


def _normal_text(project_root) -> str:
    return (project_root / "fixtures" / "evaluation" / "DOC-0001.txt").read_text(encoding="utf-8")


def test_stub_is_explicit_and_matches_deterministic_contract(project_root) -> None:
    text = _normal_text(project_root)
    result = build_extractor("llm-contract-stub").extract(text)

    assert result == parse_document(text)
    assert build_extractor("deterministic").version == "deterministic-1.1.0"
    assert result.fields and all(field.evidence_excerpt for field in result.fields)


def test_stub_provider_failure_is_explicit_not_silently_fallback() -> None:
    def broken(_: str) -> ExtractionResult:
        raise RuntimeError("model unavailable")

    with pytest.raises(ExtractionProviderError):
        OfflineLLMContractStub(broken).extract("any text")


def test_missing_provider_spans_flow_to_existing_hold_gate(project_root) -> None:
    text = _normal_text(project_root)
    parsed = parse_document(text)
    no_evidence = ExtractionResult(
        fields=tuple(
            replace(field, char_start=None, char_end=None, evidence_excerpt=None)
            for field in parsed.fields
        ),
        items=parsed.items,
    )
    registry = VendorRegistry.load(project_root / "fixtures" / "vendors.json")
    result = process_document(
        text,
        sha256="provider-contract-test",
        registry=registry,
        extractor=OfflineLLMContractStub(lambda _: no_evidence),
    )

    assert result.status == "HOLD"
    assert "MISSING_EVIDENCE" in {issue.rule_id for issue in result.issues}


def test_provider_error_becomes_explicit_unprocessable(project_root) -> None:
    registry = VendorRegistry.load(project_root / "fixtures" / "vendors.json")
    with pytest.raises(UnprocessableError, match="provider"):
        process_document(
            _normal_text(project_root),
            sha256="provider-contract-test",
            registry=registry,
            extractor=OfflineLLMContractStub(lambda _: "not an extraction result"),
        )


def test_stub_provider_is_opt_in_and_recorded_on_ingest(settings: Settings, demo_bytes) -> None:
    app = create_app(replace(settings, extraction_provider="llm-contract-stub"))
    with TestClient(app) as client:
        response = client.post(
            "/api/documents",
            files={"file": ("demo.txt", demo_bytes("DEMO-0001.txt"), "text/plain")},
        )
        assert response.status_code == 201
        document_id = response.json()["document"]["id"]
        detail = client.get(f"/api/documents/{document_id}")
        assert detail.json()["document"]["extractor_version"] == "llm-contract-stub-0.1.0"
        assert client.get("/api/meta").json()["configured_provider"] == "llm-contract-stub-0.1.0"
