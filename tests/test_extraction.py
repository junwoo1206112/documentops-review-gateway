from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.evidence import apply_evidence
from app.services.extraction.deterministic import DocumentFormatError, parse_document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "fixtures" / "evaluation"
LAYOUT2_DIR = PROJECT_ROOT / "fixtures" / "evaluation_layout2"


def load_manifest() -> list[dict]:
    return [
        json.loads(line)
        for line in (EVAL_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def document_text(document_id: str) -> str:
    return (EVAL_DIR / f"{document_id}.txt").read_text(encoding="utf-8")


def test_parses_normal_document_with_spans() -> None:
    text = document_text("DOC-0001")
    result = parse_document(text)
    fields = result.by_path()

    assert [field.path for field in result.fields] == [
        "vendor",
        "doc_no",
        "doc_date",
        "supply_amount",
        "vat",
        "total",
        "items[0].name",
        "items[0].qty",
        "items[0].unit_price",
        "items[0].amount",
    ]
    assert fields["vendor"].value == "가온상사"
    assert fields["doc_no"].value == "TX-2026-1001"
    assert fields["doc_date"].value == "2026-01-05"
    assert fields["supply_amount"].value == 13500
    assert fields["vat"].value == 1350
    assert fields["total"].value == 14850
    assert result.items[0].name == "산업용 볼트 M8"
    assert result.items[0].qty == 9
    assert result.items[0].unit_price == 1500
    assert result.items[0].amount == 13500

    for field in result.fields:
        assert field.evidence_status == "verified"
        assert field.char_start is not None and field.char_end is not None
        assert text[field.char_start : field.char_end] == field.evidence_excerpt


def test_derived_total_is_not_verified_evidence() -> None:
    target = next(entry for entry in load_manifest() if entry["category"] == "missing_evidence")
    text = document_text(target["document_id"])
    result = parse_document(text)
    total = result.by_path()["total"]
    assert total.evidence_status == "derived"
    assert total.value == 28800 + 2880
    assert total.char_start is None
    verified = apply_evidence(text, result.fields)
    statuses = {field.path: field.evidence_status for field in verified}
    assert statuses["total"] == "derived"
    assert statuses["supply_amount"] == "verified"


@pytest.mark.parametrize("category", ["invalid_date", "invalid_money", "invalid_doc_no"])
def test_invalid_format_keeps_raw_text_but_has_no_value(category: str) -> None:
    target = next(entry for entry in load_manifest() if entry["category"] == category)
    text = document_text(target["document_id"])
    result = parse_document(text)
    expected = json.loads(
        (EVAL_DIR / "expected" / f"{target['document_id']}.json").read_text(encoding="utf-8")
    )
    path = {
        "invalid_date": "doc_date",
        "invalid_money": "supply_amount",
        "invalid_doc_no": "doc_no",
    }[category]
    field = result.by_path()[path]
    assert field.value is None
    assert field.value_text is not None and field.value_text.strip()
    assert field.evidence_status == "verified"
    assert expected["fields"][path] is None


def test_crlf_document_keeps_offsets_consistent() -> None:
    text = document_text("DOC-0001").replace("\n", "\r\n")
    result = parse_document(text)
    fields = result.by_path()
    assert fields["vendor"].value == "가온상사"
    for field in result.fields:
        assert field.char_start is not None and field.char_end is not None
        assert text[field.char_start : field.char_end] == field.evidence_excerpt


def test_parses_pipe_layout_with_exact_cell_spans() -> None:
    text = (LAYOUT2_DIR / "DOC-0001.txt").read_text(encoding="utf-8")
    result = parse_document(text)
    fields = result.by_path()
    assert fields["vendor"].value == "가온상사"
    assert fields["doc_date"].value == "2026-01-05"
    assert result.items[0].name == "산업용 볼트 M8"
    assert result.items[0].qty == 9
    for field in result.fields:
        if field.char_start is not None:
            assert text[field.char_start : field.char_end] == field.evidence_excerpt


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace("품목 | 수량 | 단가 | 금액", "품목 | 수량 | 단가", 1),
        lambda text: text.replace("산업용 볼트 M8 | 9 | 1,500 | 13,500", "산업용 볼트 M8 | 9 | | 13,500", 1),
        lambda text: text.replace("작성일: ", "작성일자: ", 1),
    ],
)
def test_pipe_layout_rejects_incomplete_or_ambiguous_structure(mutation) -> None:
    text = (LAYOUT2_DIR / "DOC-0001.txt").read_text(encoding="utf-8")
    with pytest.raises(DocumentFormatError):
        parse_document(mutation(text))


def test_mixed_layout_is_rejected_not_guessed() -> None:
    text = document_text("DOC-0001").replace(
        "품목명                수량        단가          금액", "품목 | 수량 | 단가 | 금액", 1
    )
    with pytest.raises(DocumentFormatError):
        parse_document(text)


def test_malformed_item_row_is_rejected_not_guessed() -> None:
    text = document_text("DOC-0001").replace("산업용 볼트 M8  9", "산업용 볼트 M8 9", 1)
    with pytest.raises(DocumentFormatError):
        parse_document(text)


def test_document_without_header_is_rejected() -> None:
    with pytest.raises(DocumentFormatError):
        parse_document("   ")
