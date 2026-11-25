"""추출기 인터페이스. 기본 구현은 결정론적 파서다 (ADR 0001)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

EVIDENCE_VERIFIED = "verified"
EVIDENCE_DERIVED = "derived"
EVIDENCE_MISSING = "missing"
EVIDENCE_STATUSES: tuple[str, ...] = (
    EVIDENCE_VERIFIED,
    EVIDENCE_DERIVED,
    EVIDENCE_MISSING,
)


@dataclass(frozen=True)
class ExtractedField:
    path: str
    label: str
    value_text: str | None
    value: str | int | None
    page: int
    char_start: int | None
    char_end: int | None
    evidence_excerpt: str | None
    evidence_status: str
    confidence: float = 1.0


@dataclass(frozen=True)
class Item:
    ordinal: int
    name: str | None
    qty: int | None
    unit_price: int | None
    amount: int | None


@dataclass(frozen=True)
class ExtractionResult:
    fields: tuple[ExtractedField, ...]
    items: tuple[Item, ...]

    def by_path(self) -> dict[str, ExtractedField]:
        return {field.path: field for field in self.fields}


class ExtractionProvider(Protocol):
    """LLM 어댑터를 넣더라도 같은 결과 계약을 지켜야 한다."""

    version: str

    def extract(self, raw_text: str) -> ExtractionResult: ...
