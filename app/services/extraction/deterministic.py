"""결정론적 텍스트 파서.

계약: docs/schema.md '문서 텍스트 레이아웃'. 모든 값은 원문 span을 가진다.
레이아웃을 해석할 수 없으면 DocumentFormatError(HTTP 422)로 끝내고, 조용히 추측하지 않는다.
"""

from __future__ import annotations

import re

from app.domain.fields import FIELD_KEYS, FIELD_LABELS, ITEM_FIELD_KEYS
from app.services.extraction.base import (
    EVIDENCE_DERIVED,
    EVIDENCE_MISSING,
    EVIDENCE_VERIFIED,
    ExtractedField,
    ExtractionResult,
    Item,
)
from app.services.textnorm import (
    is_valid_doc_no,
    normalize_doc_no,
    normalize_vendor,
    parse_iso_date,
    parse_money,
)

EXTRACTOR_VERSION = "deterministic-1.0.0"

HEADER_LABELS: dict[str, str] = {
    "거래처": "vendor",
    "문서번호": "doc_no",
    "작성일자": "doc_date",
    "공급가액": "supply_amount",
    "부가세": "vat",
    "총액": "total",
}

HEADER_RE = re.compile(r"^(거래처|문서번호|작성일자|공급가액|부가세|총액):[ \t]*(.*)$")
ITEM_HEADER_PREFIX = "품목명"
ITEM_ROW_RE = re.compile(
    r"^(?P<name>.+?)\s{2,}(?P<qty>\S+)\s{2,}(?P<unit>\S+)\s{2,}(?P<amount>\S+)$"
)
DERIVED_TOTAL_NOTE = "※ 총액은"
ITEM_PATH_RE = re.compile(r"^items\[(?P<ordinal>\d+)\]\.(?P<key>[a-z_]+)$")


class DocumentFormatError(Exception):
    """문서 레이아웃을 계약대로 해석할 수 없다. 추측하지 않는다."""


def _iter_lines(text: str):
    offset = 0
    for raw_line in text.split("\n"):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        yield offset, line
        offset += len(raw_line) + 1


def _header_value(path: str, raw: str) -> str | int | None:
    if path == "vendor":
        return normalize_vendor(raw) or None
    if path == "doc_no":
        normalized = normalize_doc_no(raw)
        return normalized if is_valid_doc_no(normalized) else None
    if path == "doc_date":
        return parse_iso_date(raw)
    return parse_money(raw)


def _make_header_field(path: str, text: str, start: int, end: int) -> ExtractedField:
    value_text = text or None
    evidence_status = EVIDENCE_VERIFIED if value_text is not None else EVIDENCE_MISSING
    return ExtractedField(
        path=path,
        label=FIELD_LABELS[path],
        value_text=value_text,
        value=_header_value(path, text) if value_text is not None else None,
        page=1,
        char_start=start if value_text is not None else None,
        char_end=end if value_text is not None else None,
        evidence_excerpt=value_text,
        evidence_status=evidence_status,
    )


def _parse_items(text: str) -> tuple[list[Item], dict[str, ExtractedField]]:
    lines = list(_iter_lines(text))
    header_index = next(
        (index for index, (_, line) in enumerate(lines) if line.startswith(ITEM_HEADER_PREFIX)),
        None,
    )
    if header_index is None:
        return [], {}

    items: list[Item] = []
    fields: dict[str, ExtractedField] = {}
    for ordinal, (offset, line) in enumerate(lines[header_index + 1 :]):
        if not line.strip():
            break
        match = ITEM_ROW_RE.fullmatch(line)
        if match is None:
            raise DocumentFormatError(f"품목 행을 해석할 수 없습니다: {line!r}")

        name = match.group("name")
        qty_text = match.group("qty")
        unit_text = match.group("unit")
        amount_text = match.group("amount")
        name_span = (offset + match.start("name"), offset + match.end("name"))
        qty_span = (offset + match.start("qty"), offset + match.end("qty"))
        unit_span = (offset + match.start("unit"), offset + match.end("unit"))
        amount_span = (offset + match.start("amount"), offset + match.end("amount"))

        qty = parse_money(qty_text)
        unit = parse_money(unit_text)
        amount = parse_money(amount_text)
        items.append(Item(ordinal=ordinal, name=name, qty=qty, unit_price=unit, amount=amount))

        cells = (
            ("name", name, name, *name_span),
            ("qty", qty_text, qty, *qty_span),
            ("unit_price", unit_text, unit, *unit_span),
            ("amount", amount_text, amount, *amount_span),
        )
        for key, raw, value, start, end in cells:
            path = f"items[{ordinal}].{key}"
            fields[path] = ExtractedField(
                path=path,
                label=FIELD_LABELS[key],
                value_text=raw,
                value=value,
                page=1,
                char_start=start,
                char_end=end,
                evidence_excerpt=raw,
                evidence_status=EVIDENCE_VERIFIED,
            )
    return items, fields


def parse_document(text: str) -> ExtractionResult:
    if not text.strip():
        raise DocumentFormatError("문서가 비어 있습니다.")

    fields: dict[str, ExtractedField] = {}
    has_derived_note = False

    for offset, line in _iter_lines(text):
        if line.startswith(DERIVED_TOTAL_NOTE):
            has_derived_note = True
        match = HEADER_RE.match(line)
        if match is None:
            continue
        label, raw_group = match.group(1), match.group(2)
        path = HEADER_LABELS[label]
        if path in fields:
            continue
        stripped = raw_group.strip()
        leading = len(raw_group) - len(raw_group.lstrip())
        start = offset + match.start(2) + leading
        fields[path] = _make_header_field(path, stripped, start, start + len(stripped))

    items, item_fields = _parse_items(text)
    fields.update(item_fields)

    if "total" not in fields and has_derived_note:
        supply = fields.get("supply_amount")
        vat = fields.get("vat")
        supply_value = supply.value if supply and isinstance(supply.value, int) else None
        vat_value = vat.value if vat and isinstance(vat.value, int) else None
        derived = (
            supply_value + vat_value if supply_value is not None and vat_value is not None else None
        )
        fields["total"] = ExtractedField(
            path="total",
            label=FIELD_LABELS["total"],
            value_text=None,
            value=derived,
            page=1,
            char_start=None,
            char_end=None,
            evidence_excerpt=None,
            evidence_status=EVIDENCE_DERIVED,
        )

    ordered: list[ExtractedField] = []
    for key in FIELD_KEYS:
        if key in fields:
            ordered.append(fields.pop(key))
    ordered.extend(
        fields[f"items[{item.ordinal}].{key}"] for item in items for key in ITEM_FIELD_KEYS
    )
    return ExtractionResult(fields=tuple(ordered), items=tuple(items))


class DeterministicExtractor:
    version = EXTRACTOR_VERSION

    def extract(self, raw_text: str) -> ExtractionResult:
        return parse_document(raw_text)
