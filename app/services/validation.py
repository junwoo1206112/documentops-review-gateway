"""검증 규칙 엔진.

원칙
- 규칙 ID·심각도는 app/domain/rules.py가 단일 출처다.
- blocking 1건 이상이면 HOLD. warning은 판정에 쓰지 않는다.
- 한 원인이 여러 규칙을 만들지 않도록 docs/rules.md의 연쇄 억제를 구현한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.fields import FIELD_KEYS, FIELD_LABELS, MONEY_FIELDS, REQUIRED_FIELDS
from app.domain.models import ExistingDocument
from app.domain.rules import RULE_BY_ID, SEVERITY_BLOCKING
from app.services.extraction.base import (
    EVIDENCE_VERIFIED,
    ExtractedField,
    ExtractionResult,
)
from app.services.textnorm import (
    is_valid_doc_no,
    normalize_doc_no,
    round_half_up_vat,
)
from app.services.vendors import VendorRegistry

MISSING_REQUIRED = "MISSING_REQUIRED"
INVALID_DOC_NO = "INVALID_DOC_NO"
INVALID_DATE = "INVALID_DATE"
INVALID_MONEY = "INVALID_MONEY"
LINE_TOTAL_MISMATCH = "LINE_TOTAL_MISMATCH"
DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
UNKNOWN_VENDOR = "UNKNOWN_VENDOR"
MISSING_EVIDENCE = "MISSING_EVIDENCE"


@dataclass(frozen=True)
class ValidationIssue:
    rule_id: str
    severity: str
    path: str
    message: str
    status: str = "open"


@dataclass
class _Draft:
    rule_id: str
    path: str
    message: str


def _issue(rule_id: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(
        rule_id=rule_id,
        severity=RULE_BY_ID[rule_id].severity,
        path=path,
        message=message,
    )


def status_for_issues(issues: Sequence[ValidationIssue]) -> str:
    if any(issue.severity == SEVERITY_BLOCKING for issue in issues):
        return "HOLD"
    return "PENDING_REVIEW"


def find_duplicate(
    existing: Sequence[ExistingDocument],
    *,
    doc_no: str | None,
    sha256: str,
) -> tuple[ExistingDocument, str] | None:
    for document in existing:
        if document.status == "REJECTED":
            continue
        if document.sha256 == sha256:
            return document, "같은 파일"
        if doc_no and document.doc_no == doc_no:
            return document, "같은 문서번호"
    return None


def _money_paths(extraction: ExtractionResult) -> list[str]:
    paths = [path for path in FIELD_KEYS if path in MONEY_FIELDS]
    for item in extraction.items:
        for key in ("qty", "unit_price", "amount"):
            paths.append(f"items[{item.ordinal}].{key}")
    return paths


def _field_value(field: ExtractedField | None) -> int | None:
    if field is None:
        return None
    return field.value if isinstance(field.value, int) else None


def validate(
    extraction: ExtractionResult,
    *,
    registry: VendorRegistry,
    existing: Sequence[ExistingDocument] = (),
    sha256: str = "",
) -> tuple[ValidationIssue, ...]:
    fields = extraction.by_path()
    drafts: list[_Draft] = []
    blocked: set[str] = set()
    invalid_paths: set[str] = set()

    # 1. 필수 필드
    for path in REQUIRED_FIELDS:
        if path == "items":
            if not extraction.items:
                drafts.append(
                    _Draft(MISSING_REQUIRED, "items", f"{FIELD_LABELS['items']} 값이 없습니다.")
                )
                blocked.add("items")
            continue
        field = fields.get(path)
        missing = field is None or (field.value_text is None and field.value is None)
        if field is not None and field.value_text is not None and not field.value_text.strip():
            missing = True
        if missing:
            drafts.append(_Draft(MISSING_REQUIRED, path, f"{FIELD_LABELS[path]} 값이 없습니다."))
            blocked.add(path)

    # 2. 형식
    doc_no = fields.get("doc_no")
    if "doc_no" not in blocked and doc_no is not None and doc_no.value_text:
        normalized = (
            doc_no.value if isinstance(doc_no.value, str) else normalize_doc_no(doc_no.value_text)
        )
        if not is_valid_doc_no(normalized):
            drafts.append(
                _Draft(
                    INVALID_DOC_NO,
                    "doc_no",
                    f"문서번호 형식이 올바르지 않습니다: {doc_no.value_text}",
                )
            )

    doc_date = fields.get("doc_date")
    if "doc_date" not in blocked and doc_date is not None and doc_date.value is None:
        drafts.append(
            _Draft(
                INVALID_DATE,
                "doc_date",
                f"날짜 형식이 올바르지 않습니다: {doc_date.value_text}",
            )
        )

    for path in _money_paths(extraction):
        if path in blocked:
            continue
        field = fields.get(path)
        if field is None or field.value_text is None:
            continue
        if field.value is None:
            drafts.append(
                _Draft(
                    INVALID_MONEY,
                    path,
                    f"{field.label} 형식이 올바르지 않습니다: {field.value_text}",
                )
            )
            invalid_paths.add(path)
            continue
        if isinstance(field.value, int) and path.endswith(".qty") and field.value < 1:
            drafts.append(
                _Draft(INVALID_MONEY, path, f"{field.label}은 1 이상이어야 합니다: {field.value}")
            )
            invalid_paths.add(path)

    # 3. 산술 (해석 실패·범위 위반 값이 쓰이는 관계는 건너뛴다)
    arithmetic: list[tuple[str, str]] = []
    for item in extraction.items:
        item_paths = {
            f"items[{item.ordinal}].qty",
            f"items[{item.ordinal}].unit_price",
            f"items[{item.ordinal}].amount",
        }
        if item_paths & invalid_paths:
            continue
        if item.qty is None or item.unit_price is None or item.amount is None:
            continue
        expected = item.qty * item.unit_price
        if item.amount != expected:
            arithmetic.append(
                (
                    f"items[{item.ordinal}].amount",
                    f"품목 {item.ordinal + 1} 금액 {item.amount:,} ≠ 수량×단가 {expected:,}",
                )
            )

    supply = _field_value(fields.get("supply_amount"))
    vat = _field_value(fields.get("vat"))
    total = _field_value(fields.get("total"))

    item_amounts = [item.amount for item in extraction.items]
    if (
        "supply_amount" not in invalid_paths
        and supply is not None
        and extraction.items
        and all(value is not None for value in item_amounts)
    ):
        item_sum = sum(value for value in item_amounts if value is not None)
        if supply != item_sum:
            arithmetic.append(("supply_amount", f"공급가액 {supply:,} ≠ 품목 합계 {item_sum:,}"))

    if not {"supply_amount", "vat"} & invalid_paths and supply is not None and vat is not None:
        expected_vat = round_half_up_vat(supply)
        if vat != expected_vat:
            arithmetic.append(("vat", f"부가세 {vat:,} ≠ 공급가액의 10% {expected_vat:,}"))

    if (
        not {"supply_amount", "vat", "total"} & invalid_paths
        and supply is not None
        and vat is not None
        and total is not None
    ):
        expected_total = supply + vat
        if total != expected_total:
            arithmetic.append(("total", f"총액 {total:,} ≠ 공급가액+부가세 {expected_total:,}"))

    if arithmetic:
        path, _ = arithmetic[0]
        details = "; ".join(detail for _, detail in arithmetic)
        drafts.append(
            _Draft(
                LINE_TOTAL_MISMATCH,
                path,
                f"금액 합계가 일치하지 않습니다: {details}",
            )
        )

    # 4. 거래처
    vendor = fields.get("vendor")
    if (
        "vendor" not in blocked
        and vendor is not None
        and isinstance(vendor.value, str)
        and not registry.contains(vendor.value)
    ):
        drafts.append(
            _Draft(
                UNKNOWN_VENDOR,
                "vendor",
                f"등록되지 않은 거래처입니다: {vendor.value_text}",
            )
        )

    # 5. 중복
    doc_no_value = doc_no.value if doc_no is not None and isinstance(doc_no.value, str) else None
    duplicate = find_duplicate(existing, doc_no=doc_no_value, sha256=sha256)
    if duplicate is not None:
        other, kind = duplicate
        drafts.append(
            _Draft(
                DUPLICATE_DOCUMENT,
                "doc_no" if kind == "같은 문서번호" else "sha256",
                f"중복 문서입니다: {kind} ({other.document_id})",
            )
        )

    # 6. 근거
    unverified = [
        field
        for field in extraction.fields
        if field.evidence_status != EVIDENCE_VERIFIED and field.path not in blocked
    ]
    if unverified:
        labels = ", ".join(f"{field.label}({field.path})" for field in unverified)
        drafts.append(
            _Draft(
                MISSING_EVIDENCE,
                unverified[0].path,
                f"{labels} 값의 원문 근거를 확인할 수 없습니다.",
            )
        )

    # 집계: MISSING_REQUIRED는 필드별, 나머지는 규칙당 1건
    merged: dict[str, ValidationIssue] = {}
    issues: list[ValidationIssue] = []
    for draft in drafts:
        if draft.rule_id == MISSING_REQUIRED:
            issues.append(_issue(draft.rule_id, draft.path, draft.message))
            continue
        if draft.rule_id in merged:
            previous = merged[draft.rule_id]
            merged[draft.rule_id] = _issue(
                previous.rule_id, previous.path, f"{previous.message} / {draft.message}"
            )
        else:
            merged[draft.rule_id] = _issue(draft.rule_id, draft.path, draft.message)
    issues.extend(merged.values())
    issues.sort(key=lambda issue: (issue.rule_id, issue.path))
    return tuple(issues)
