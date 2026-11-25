"""근거(span) 검증. 값이 정답이어도 근거가 없으면 통과시키지 않는다."""

from __future__ import annotations

from dataclasses import replace

from app.services.extraction.base import (
    EVIDENCE_DERIVED,
    EVIDENCE_MISSING,
    EVIDENCE_VERIFIED,
    ExtractedField,
)
from app.services.textnorm import (
    normalize_doc_no,
    normalize_vendor,
    parse_iso_date,
    parse_money,
)

MONEY_PATHS = frozenset({"supply_amount", "vat", "total"})
ITEM_KEY_BY_SUFFIX = {"qty": "qty", "unit_price": "unit_price", "amount": "amount"}


def _item_key(path: str) -> str | None:
    if not path.startswith("items["):
        return None
    return path.rsplit(".", 1)[-1]


def normalized_matches(path: str, excerpt: str, value: str | int) -> bool:
    item_key = _item_key(path)
    if item_key in ITEM_KEY_BY_SUFFIX:
        return parse_money(excerpt) == value
    if item_key == "name":
        return excerpt.strip() == value
    if path in MONEY_PATHS:
        return parse_money(excerpt) == value
    if path == "doc_date":
        return parse_iso_date(excerpt) == value
    if path == "doc_no":
        return normalize_doc_no(excerpt) == value
    if path == "vendor":
        return normalize_vendor(excerpt) == value
    return excerpt.strip() == value


def is_valid(field: ExtractedField, raw_text: str) -> bool:
    if field.evidence_status == EVIDENCE_DERIVED:
        return False
    if field.char_start is None or field.char_end is None:
        return False
    if field.char_start < 0 or field.char_end > len(raw_text):
        return False
    if field.char_start >= field.char_end:
        return False
    excerpt = raw_text[field.char_start : field.char_end]
    if field.evidence_excerpt is None or excerpt != field.evidence_excerpt:
        return False
    if field.value is None:
        return True
    return normalized_matches(field.path, excerpt, field.value)


def apply_evidence(raw_text: str, fields: tuple[ExtractedField, ...]) -> tuple[ExtractedField, ...]:
    """파서가 verified라고 한 필드도 원문과 대조해 실제 상태로 낮춘다."""
    result: list[ExtractedField] = []
    for field in fields:
        if field.evidence_status == EVIDENCE_DERIVED:
            result.append(field)
            continue
        if is_valid(field, raw_text):
            result.append(
                field
                if field.evidence_status == EVIDENCE_VERIFIED
                else replace(field, evidence_status=EVIDENCE_VERIFIED)
            )
        else:
            result.append(replace(field, evidence_status=EVIDENCE_MISSING))
    return tuple(result)
