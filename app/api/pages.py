"""서버 렌더링 화면. JS 없이 폼 전송만 사용한다 (ADR 0002)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from markupsafe import Markup, escape

from app.domain.fields import FIELD_KEYS, FIELD_LABELS
from app.domain.statuses import STATUS_LABELS
from app.errors import AppError

router = APIRouter()

EVENT_LABELS = {
    "DOCUMENT_INGESTED": "문서 접수",
    "VALIDATION_COMPLETED": "검증 완료",
    "REVALIDATED": "재검증",
    "DECISION_RECORDED": "사람 판정",
    "CORRECTION_RECORDED": "필드 수정",
}

EVIDENCE_LABELS = {
    "verified": "원문 확인",
    "derived": "파생값",
    "missing": "근거 없음",
}

MONEY_PATHS = {"supply_amount", "vat", "total"}


def _templates(request: Request):
    return request.app.state.templates


def setup_filters(templates) -> None:
    def money(value: Any) -> str:
        return f"{value:,}" if isinstance(value, int) else ("" if value is None else str(value))

    templates.env.filters["money"] = money
    templates.env.filters["status_label"] = lambda status: STATUS_LABELS.get(status, status)


def highlight_evidence(raw_text: str, fields: list[dict]) -> Markup:
    """검증된 span만 <mark>로 감싼다. 원문은 항상 이스케이프한다."""
    spans = sorted(
        (
            (field["char_start"], field["char_end"])
            for field in fields
            if field["evidence_status"] == "verified"
            and field["char_start"] is not None
            and field["char_end"] is not None
        ),
        key=lambda pair: pair[0],
    )
    parts: list[Markup] = []
    cursor = 0
    for start, end in spans:
        if start < cursor or end <= start:
            continue
        parts.append(escape(raw_text[cursor:start]))
        parts.append(Markup("<mark>"))
        parts.append(escape(raw_text[start:end]))
        parts.append(Markup("</mark>"))
        cursor = end
    parts.append(escape(raw_text[cursor:]))
    return Markup("").join(parts)


def _detail_context(request: Request, detail: dict, *, form_error: str | None = None) -> dict:
    fields = detail.get("effective_fields", detail["fields"])
    labeled_fields = [
        {
            **field,
            "display": (
                f"{field['value']:,}"
                if isinstance(field["value"], int) and field["path"] in MONEY_PATHS
                else field["value"]
            ),
        }
        for field in fields
    ]
    display_by_path = {field["path"]: field["display"] for field in labeled_fields}
    return {
        "detail": detail,
        "document": detail["document"],
        "fields": labeled_fields,
        "items": detail.get("effective_items", detail["items"]),
        "issues": detail["issues"],
        "decisions": detail["decisions"],
        "corrections": detail.get("corrections", []),
        "correctable_fields": [
            {
                "path": key,
                "label": FIELD_LABELS[key],
                "current": display_by_path.get(key),
            }
            for key in FIELD_KEYS
        ]
        + [
            {
                "path": f"items[{item['ordinal']}].{key}",
                "label": f"품목 {item['ordinal'] + 1} {FIELD_LABELS[key]}",
                "current": item[key],
            }
            for item in detail.get("effective_items", detail["items"])
            for key in ("name", "qty", "unit_price", "amount")
        ],
        "can_correct": detail["document"]["status"] in {"HOLD", "PENDING_REVIEW"},
        "raw_highlighted": highlight_evidence(detail["raw_text"], fields),
        "status_labels": STATUS_LABELS,
        "evidence_labels": EVIDENCE_LABELS,
        "event_labels": EVENT_LABELS,
        "form_error": form_error,
        "can_revalidate": detail["document"]["status"] in {"HOLD", "PENDING_REVIEW"},
        "can_decide": detail["document"]["status"] in {"PENDING_REVIEW", "HOLD"},
    }


@router.get("/", response_class=HTMLResponse)
def index(request: Request, status: str | None = None) -> HTMLResponse:
    service = request.app.state.service
    try:
        items, total = service.list_documents(status=status or None, limit=100)
    except AppError as exc:
        return _templates(request).TemplateResponse(
            request,
            "index.html",
            {"items": [], "total": 0, "counts": {}, "selected": None, "error": str(exc)},
            status_code=exc.status_code,
        )
    return _templates(request).TemplateResponse(
        request,
        "index.html",
        {
            "items": items,
            "total": total,
            "counts": request.app.state.db.count_by_status(),
            "selected": status or "",
            "status_labels": STATUS_LABELS,
            "error": None,
        },
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
    settings = request.app.state.settings
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        detail = request.app.state.service.ingest(file.filename or "document.txt", data)
    except AppError as exc:
        items, total = request.app.state.service.list_documents(limit=100)
        return _templates(request).TemplateResponse(
            request,
            "index.html",
            {
                "items": items,
                "total": total,
                "counts": request.app.state.db.count_by_status(),
                "selected": "",
                "status_labels": STATUS_LABELS,
                "error": str(exc),
            },
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/documents/{detail['document']['id']}", status_code=303)


@router.get("/documents/{document_id}", response_class=HTMLResponse)
def document_detail(request: Request, document_id: str) -> HTMLResponse:
    detail = request.app.state.service.get(document_id)
    return _templates(request).TemplateResponse(
        request, "detail.html", _detail_context(request, detail)
    )


@router.post("/documents/{document_id}/decision", response_class=HTMLResponse)
def submit_decision(
    request: Request,
    document_id: str,
    decision: str = Form(...),
    reviewer_alias: str = Form(""),
    reason: str = Form(""),
) -> HTMLResponse:
    try:
        request.app.state.service.decide(
            document_id,
            decision=decision,
            reviewer_alias=reviewer_alias,
            reason=reason,
        )
    except AppError as exc:
        detail = request.app.state.service.get(document_id)
        return _templates(request).TemplateResponse(
            request,
            "detail.html",
            _detail_context(request, detail, form_error=str(exc)),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/documents/{document_id}", status_code=303)


@router.post("/documents/{document_id}/revalidate", response_class=HTMLResponse)
def submit_revalidate(request: Request, document_id: str) -> HTMLResponse:
    try:
        request.app.state.service.revalidate(document_id)
    except AppError as exc:
        detail = request.app.state.service.get(document_id)
        return _templates(request).TemplateResponse(
            request,
            "detail.html",
            _detail_context(request, detail, form_error=str(exc)),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/documents/{document_id}", status_code=303)


@router.post("/documents/{document_id}/corrections", response_class=HTMLResponse)
def submit_correction(
    request: Request,
    document_id: str,
    path: str = Form(...),
    value: str = Form(""),
    excerpt: str = Form(""),
    row_anchor: str = Form(""),
    reviewer_alias: str = Form(""),
    reason: str = Form(""),
) -> HTMLResponse:
    try:
        request.app.state.service.record_correction(
            document_id,
            path=path,
            value=value,
            excerpt=excerpt or None,
            row_anchor=row_anchor or None,
            reviewer_alias=reviewer_alias,
            reason=reason,
        )
    except AppError as exc:
        detail = request.app.state.service.get(document_id)
        return _templates(request).TemplateResponse(
            request,
            "detail.html",
            _detail_context(request, detail, form_error=str(exc)),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/documents/{document_id}", status_code=303)


@router.get("/evaluation", response_class=HTMLResponse)
def evaluation(request: Request) -> HTMLResponse:
    path = request.app.state.settings.artifacts_dir / "evaluation_report.json"
    report = None
    error = None
    if path.exists():
        try:
            import json

            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # pragma: no cover - 손상된 파일
            error = f"평가 리포트를 읽을 수 없습니다: {exc}"
    return _templates(request).TemplateResponse(
        request,
        "evaluation.html",
        {"report": report, "error": error, "path": str(path)},
    )
