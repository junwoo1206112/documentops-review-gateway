"""API 라우터."""

from __future__ import annotations

from fastapi import APIRouter, File, Query, Request, UploadFile

from app.api.schemas import CorrectionRequest, DecisionRequest
from app.domain.fields import FIELD_LABELS
from app.domain.rules import RULES
from app.domain.statuses import STATUSES
from app.errors import NotFoundError, PayloadTooLargeError, UnprocessableError
from app.services.reports import load_reports, primary_report
from app.version import (
    APP_NAME,
    APP_VERSION,
    DATASET_VERSION,
    EXTRACTOR_VERSION,
    RULESET_VERSION,
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict:
    return {"status": "ok", "version": APP_VERSION, "name": APP_NAME}


@router.get("/meta")
def meta(request: Request) -> dict:
    return {
        "app_version": APP_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "configured_provider": request.app.state.service.extractor.version,
        "ruleset_version": RULESET_VERSION,
        "dataset_version": DATASET_VERSION,
        "statuses": list(STATUSES),
        "fields": FIELD_LABELS,
        "rules": [
            {"rule_id": rule.rule_id, "severity": rule.severity, "summary": rule.summary}
            for rule in RULES
        ],
    }


@router.post("/documents", status_code=201)
async def upload_document(request: Request, file: UploadFile = File(...)) -> dict:
    settings = request.app.state.settings
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"파일은 {settings.max_upload_bytes}바이트 이하여야 합니다.")
    return request.app.state.service.ingest(file.filename or "document.txt", data)


@router.get("/documents")
def list_documents(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
) -> dict:
    if not 1 <= limit <= 100:
        raise UnprocessableError("limit은 1~100이어야 합니다.")
    if offset < 0:
        raise UnprocessableError("offset은 0 이상이어야 합니다.")
    items, total = request.app.state.service.list_documents(
        status=status, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/documents/{document_id}")
def get_document(request: Request, document_id: str) -> dict:
    return request.app.state.service.get(document_id)


@router.get("/documents/{document_id}/audit")
def get_audit(request: Request, document_id: str) -> dict:
    return {"items": request.app.state.service.audit(document_id)}


@router.post("/documents/{document_id}/revalidate")
def revalidate(request: Request, document_id: str) -> dict:
    return request.app.state.service.revalidate(document_id)


@router.post("/documents/{document_id}/corrections", status_code=201)
def correct_field(request: Request, document_id: str, payload: CorrectionRequest) -> dict:
    return request.app.state.service.record_correction(
        document_id,
        path=payload.path,
        value=payload.value,
        excerpt=payload.excerpt,
        char_start=payload.char_start,
        char_end=payload.char_end,
        row_anchor=payload.row_anchor,
        reviewer_alias=payload.reviewer_alias,
        reason=payload.reason,
    )


@router.post("/documents/{document_id}/decision")
def decide(request: Request, document_id: str, payload: DecisionRequest) -> dict:
    return request.app.state.service.decide(
        document_id,
        decision=payload.decision,
        reviewer_alias=payload.reviewer_alias,
        reason=payload.reason,
    )


@router.get("/evaluation/latest")
def latest_evaluation(request: Request) -> dict:
    settings = request.app.state.settings
    reports = load_reports(settings.artifacts_dir)
    if not reports:
        raise NotFoundError(
            "아직 평가 리포트가 없습니다. python -m app.evaluate를 먼저 실행하세요."
        )
    report = primary_report(reports, settings.evaluation_dir.name)
    if report is None:  # pragma: no cover
        raise NotFoundError("평가 리포트를 읽을 수 없습니다.")
    return report


@router.get("/evaluation/reports")
def evaluation_reports(request: Request) -> dict:
    reports = load_reports(request.app.state.settings.artifacts_dir)
    return {"items": reports, "total": len(reports)}
