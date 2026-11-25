from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.models import ExistingDocument
from app.errors import UnprocessableError
from app.services.evidence import apply_evidence
from app.services.extraction.deterministic import parse_document
from app.services.pipeline import process_document
from app.services.validation import ValidationIssue, status_for_issues, validate
from app.services.vendors import VendorRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "fixtures" / "evaluation"
REGISTRY = VendorRegistry.load(PROJECT_ROOT / "fixtures" / "vendors.json")


def load_manifest() -> list[dict]:
    return [
        json.loads(line)
        for line in (EVAL_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def expected_of(document_id: str) -> dict:
    path = EVAL_DIR / "expected" / f"{document_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def text_of(filename: str) -> str:
    return (EVAL_DIR / filename).read_text(encoding="utf-8")


def run(text: str, *, sha256: str = "0" * 64, existing: tuple[ExistingDocument, ...] = ()):
    return process_document(text, sha256=sha256, registry=REGISTRY, existing=existing)


def test_dataset_matches_expected_rules_and_status() -> None:
    existing: list[ExistingDocument] = []
    for entry in load_manifest():
        expected = expected_of(entry["document_id"])
        result = run(text_of(entry["filename"]), sha256=entry["sha256"], existing=tuple(existing))
        actual_rules = {issue.rule_id for issue in result.issues}
        assert actual_rules == set(expected["expected_rule_ids"]), entry["document_id"]
        assert result.status == expected["expected_status"], entry["document_id"]

        doc_no_field = result.fields and next(
            (field for field in result.fields if field.path == "doc_no"), None
        )
        doc_no = doc_no_field.value if doc_no_field is not None else None
        existing.append(
            ExistingDocument(
                document_id=entry["document_id"],
                doc_no=doc_no if isinstance(doc_no, str) else None,
                sha256=entry["sha256"],
                status=result.status,
            )
        )


def test_dataset_field_values_match_ground_truth() -> None:
    for entry in load_manifest():
        expected = expected_of(entry["document_id"])
        result = run(text_of(entry["filename"]), sha256=entry["sha256"])
        fields = result.by_path()
        for path, expected_value in expected["fields"].items():
            field = fields.get(path)
            actual = field.value if field is not None else None
            assert actual == expected_value, f"{entry['document_id']} {path}"

        assert len(result.items) == len(expected["items"]), entry["document_id"]
        for item, expected_item in zip(result.items, expected["items"], strict=True):
            assert item.name == expected_item["name"]
            assert item.qty == expected_item["qty"]
            assert item.unit_price == expected_item["unit_price"]
            assert item.amount == expected_item["amount"]


def test_dataset_evidence_is_verified_or_explicitly_derived() -> None:
    for entry in load_manifest():
        expected = expected_of(entry["document_id"])
        text = text_of(entry["filename"])
        result = run(text, sha256=entry["sha256"])
        fields = result.by_path()
        for path in expected["evidence"]:
            field = fields[path]
            assert field.evidence_status == "verified", f"{entry['document_id']} {path}"
            assert text[field.char_start : field.char_end] == expected["evidence"][path]["excerpt"]
        if entry["category"] == "missing_evidence":
            assert fields["total"].evidence_status == "derived"


def test_missing_vendor_does_not_also_report_unknown_vendor() -> None:
    text = "\n".join(
        line for line in text_of("DOC-0001.txt").splitlines() if not line.startswith("거래처:")
    )
    result = run(text)
    assert {issue.rule_id for issue in result.issues} == {"MISSING_REQUIRED"}
    assert result.status == "HOLD"


def test_invalid_money_does_not_also_report_total_mismatch() -> None:
    text = text_of("DOC-0001.txt").replace("공급가액: 13,500", "공급가액: 사십삼만원")
    result = run(text)
    assert {issue.rule_id for issue in result.issues} == {"INVALID_MONEY"}


def test_zero_quantity_is_invalid_money_not_mismatch() -> None:
    text = text_of("DOC-0001.txt").replace("  9  1,500", "  0  1,500")
    result = run(text)
    assert {issue.rule_id for issue in result.issues} == {"INVALID_MONEY"}
    assert any(issue.path == "items[0].qty" for issue in result.issues)


def test_missing_items_suppresses_item_arithmetic() -> None:
    text = (
        "[거래명세서]\n"
        "거래처: 가온상사\n"
        "문서번호: TX-2026-0001\n"
        "작성일자: 2026-01-05\n"
        "\n"
        "공급가액: 10,000\n"
        "부가세: 1,000\n"
        "총액: 11,000\n"
    )
    result = run(text)
    assert {issue.rule_id for issue in result.issues} == {"MISSING_REQUIRED"}
    assert result.issues[0].path == "items"


def test_duplicate_by_sha_requires_no_same_doc_no() -> None:
    existing = (
        ExistingDocument(
            document_id="DOC-9999",
            doc_no="TX-1999-0001",
            sha256="0" * 64,
            status="PENDING_REVIEW",
        ),
    )
    result = run(text_of("DOC-0001.txt"), sha256="0" * 64, existing=existing)
    assert {issue.rule_id for issue in result.issues} == {"DUPLICATE_DOCUMENT"}


def test_rejected_document_is_not_a_duplicate() -> None:
    existing = (
        ExistingDocument(
            document_id="DOC-9999",
            doc_no="TX-2026-1001",
            sha256="0" * 64,
            status="REJECTED",
        ),
    )
    result = run(text_of("DOC-0001.txt"), sha256="0" * 64, existing=existing)
    assert result.issues == ()
    assert result.status == "PENDING_REVIEW"


def test_tampered_span_becomes_missing_evidence() -> None:
    text = text_of("DOC-0001.txt")
    extraction = parse_document(text)
    tampered = tuple(
        field.__class__(
            path=field.path,
            label=field.label,
            value_text=field.value_text,
            value=field.value,
            page=field.page,
            char_start=(field.char_start + 1 if field.char_start is not None else None),
            char_end=(field.char_end + 1 if field.char_end is not None else None),
            evidence_excerpt=field.evidence_excerpt,
            evidence_status=field.evidence_status,
            confidence=field.confidence,
        )
        for field in extraction.fields
    )
    from app.services.extraction.base import ExtractionResult

    verified = apply_evidence(text, tampered)
    assert all(field.evidence_status != "verified" for field in verified)
    issues = validate(
        ExtractionResult(fields=verified, items=extraction.items),
        registry=REGISTRY,
    )
    assert {issue.rule_id for issue in issues} == {"MISSING_EVIDENCE"}


def test_warning_issue_does_not_hold() -> None:
    issues = (
        ValidationIssue(rule_id="MISSING_EVIDENCE", severity="warning", path="x", message="x"),
    )
    assert status_for_issues(issues) == "PENDING_REVIEW"


def test_unparsable_layout_is_422_not_a_rule() -> None:
    text = text_of("DOC-0001.txt").replace("산업용 볼트 M8  9", "산업용 볼트 M8 9", 1)
    with pytest.raises(UnprocessableError):
        run(text)
