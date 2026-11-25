"""추출 → 근거 → 검증 파이프라인 (저장 없음).

Phase 3의 ReviewService가 이 결과를 SQLite에 저장하고,
Phase 4의 평가기가 같은 함수를 고정 데이터셋에 반복 적용한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter

from app.domain.models import ExistingDocument
from app.errors import UnprocessableError
from app.services.evidence import apply_evidence
from app.services.extraction.base import ExtractedField, ExtractionResult, Item
from app.services.extraction.deterministic import DocumentFormatError, parse_document
from app.services.validation import (
    ValidationIssue,
    find_duplicate,
    status_for_issues,
    validate,
)
from app.services.vendors import VendorRegistry


@dataclass(frozen=True)
class ProcessedDocument:
    fields: tuple[ExtractedField, ...]
    items: tuple[Item, ...]
    issues: tuple[ValidationIssue, ...]
    status: str
    elapsed_ms: float
    duplicate_of: str | None = None

    def by_path(self) -> dict[str, ExtractedField]:
        return {field.path: field for field in self.fields}


def process_document(
    raw_text: str,
    *,
    sha256: str,
    registry: VendorRegistry,
    existing: Sequence[ExistingDocument] = (),
) -> ProcessedDocument:
    started = perf_counter()
    try:
        extraction: ExtractionResult = parse_document(raw_text)
    except DocumentFormatError as exc:
        raise UnprocessableError(f"문서 레이아웃을 해석할 수 없습니다: {exc}") from exc

    extraction = ExtractionResult(
        fields=apply_evidence(raw_text, extraction.fields),
        items=extraction.items,
    )
    issues = validate(
        extraction,
        registry=registry,
        existing=existing,
        sha256=sha256,
    )
    doc_no_field = extraction.by_path().get("doc_no")
    doc_no = doc_no_field.value if doc_no_field and isinstance(doc_no_field.value, str) else None
    duplicate = find_duplicate(existing, doc_no=doc_no, sha256=sha256)
    return ProcessedDocument(
        fields=extraction.fields,
        items=extraction.items,
        issues=issues,
        status=status_for_issues(issues),
        elapsed_ms=(perf_counter() - started) * 1000.0,
        duplicate_of=duplicate[0].document_id if duplicate else None,
    )
