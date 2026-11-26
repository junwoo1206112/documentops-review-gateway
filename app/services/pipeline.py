"""추출 → (사람 수정 주입) → 근거 → 검증 파이프라인 (저장 없음).

Phase 3의 ReviewService가 이 결과를 SQLite에 저장하고,
Phase 4의 평가기가 같은 함수를 고정 데이터셋에 반복 적용한다.
Phase 14의 사람 수정은 추출 결과를 덮어쓰지 않고, 검증 직전에 주입된다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from time import perf_counter

from app.domain.fields import FIELD_KEYS, FIELD_LABELS, ITEM_FIELD_KEYS
from app.domain.models import ExistingDocument, FieldCorrection
from app.errors import UnprocessableError
from app.services.evidence import apply_evidence
from app.services.extraction.base import (
    EVIDENCE_VERIFIED,
    ExtractedField,
    ExtractionProvider,
    ExtractionResult,
    Item,
)
from app.services.extraction.deterministic import DocumentFormatError, parse_document
from app.services.extraction.providers import ExtractionProviderError
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


def apply_corrections(
    extraction: ExtractionResult, corrections: Sequence[FieldCorrection]
) -> ExtractionResult:
    """검증된 사람 수정값을 필드·품목 집합에 주입한다."""
    if not corrections:
        return extraction
    fields = extraction.by_path()
    items = list(extraction.items)
    for correction in corrections:
        item_match = re.fullmatch(r"items\[(\d+)]\.(name|qty|unit_price|amount)", correction.path)
        if item_match:
            ordinal, key = int(item_match.group(1)), item_match.group(2)
            if ordinal >= len(items):
                raise UnprocessableError("수정 대상 품목 행이 존재하지 않습니다.")
            items[ordinal] = replace(items[ordinal], **{key: correction.value})
        fields[correction.path] = ExtractedField(
            path=correction.path,
            label=FIELD_LABELS.get(correction.path, correction.path),
            value_text=correction.excerpt,
            value=correction.value,
            page=correction.page,
            char_start=correction.char_start,
            char_end=correction.char_end,
            evidence_excerpt=correction.excerpt,
            evidence_status=EVIDENCE_VERIFIED,
            confidence=1.0,
        )
    ordered = [fields[key] for key in FIELD_KEYS if key in fields]
    ordered.extend(
        fields[f"items[{item.ordinal}].{key}"] for item in items for key in ITEM_FIELD_KEYS
    )
    return ExtractionResult(fields=tuple(ordered), items=tuple(items))


def process_document(
    raw_text: str,
    *,
    sha256: str,
    registry: VendorRegistry,
    existing: Sequence[ExistingDocument] = (),
    corrections: Sequence[FieldCorrection] = (),
    extractor: ExtractionProvider | None = None,
) -> ProcessedDocument:
    started = perf_counter()
    try:
        extraction: ExtractionResult = (
            parse_document(raw_text) if extractor is None else extractor.extract(raw_text)
        )
    except DocumentFormatError as exc:
        raise UnprocessableError(f"문서 레이아웃을 해석할 수 없습니다: {exc}") from exc
    except ExtractionProviderError as exc:
        raise UnprocessableError(f"추출 provider가 문서를 처리하지 못했습니다: {exc}") from exc

    extraction = apply_corrections(extraction, corrections)
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
