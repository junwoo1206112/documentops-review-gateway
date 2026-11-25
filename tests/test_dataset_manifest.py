"""합성 데이터셋의 무결성·정답 스키마·재생성 가능성을 검증한다."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.domain.rules import RULE_IDS
from app.domain.statuses import STATUSES
from app.version import DATASET_VERSION, VENDOR_REGISTRY_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "fixtures" / "evaluation"
DEMO_DIR = PROJECT_ROOT / "fixtures" / "demo"
MANIFEST = EVAL_DIR / "manifest.jsonl"
VENDOR_PATH = PROJECT_ROOT / "fixtures" / "vendors.json"

CATEGORY_COUNTS = {
    "normal": 16,
    "missing_required": 3,
    "invalid_doc_no": 2,
    "invalid_date": 2,
    "invalid_money": 1,
    "line_total_mismatch": 6,
    "duplicate": 2,
    "unknown_vendor": 2,
    "missing_evidence": 2,
}

MONEY_PATHS = {"supply_amount", "vat", "total"}
ITEM_MONEY_KEYS = {"qty", "unit_price", "amount"}


def load_manifest() -> list[dict]:
    assert MANIFEST.exists(), "manifest.jsonl이 없습니다. tools/generate_dataset.py를 실행하세요."
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_expected(document_id: str) -> dict:
    path = EVAL_DIR / "expected" / f"{document_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> list[dict]:
    return load_manifest()


def normalize(path: str, value: object) -> object:
    if value is None:
        return None
    if path in MONEY_PATHS or path.rsplit(".", 1)[-1] in ITEM_MONEY_KEYS:
        return int(str(value).replace(",", "").replace("원", "").replace("₩", "").strip())
    return value


def test_manifest_has_36_unique_documents(manifest: list[dict]) -> None:
    assert len(manifest) == 36
    assert [entry["sequence"] for entry in manifest] == list(range(1, 37))
    ids = [entry["document_id"] for entry in manifest]
    assert len(set(ids)) == 36


def test_manifest_hashes_and_sizes_match_files(manifest: list[dict]) -> None:
    for entry in manifest:
        path = EVAL_DIR / entry["filename"]
        assert path.exists(), f"{path.name} 파일이 없습니다"
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["filename"]
        assert len(data) == entry["bytes"], entry["filename"]
        assert b"\r\n" not in data, f"{entry['filename']}에 CRLF가 섞였습니다"


def test_manifest_category_counts(manifest: list[dict]) -> None:
    counts: dict[str, int] = {}
    for entry in manifest:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    assert counts == CATEGORY_COUNTS
    assert sum(counts.values()) == 36


def test_every_document_has_expected_file(manifest: list[dict]) -> None:
    for entry in manifest:
        expected = load_expected(entry["document_id"])
        assert expected["document_id"] == entry["document_id"]
        assert expected["dataset_version"] == DATASET_VERSION == entry["dataset_version"]
        assert expected["expected_status"] == entry["expected_status"]
        assert sorted(expected["expected_rule_ids"]) == sorted(entry["expected_rule_ids"])


def test_expected_schema_and_status_consistency(manifest: list[dict]) -> None:
    for entry in manifest:
        expected = load_expected(entry["document_id"])
        assert expected["expected_status"] in STATUSES
        assert set(expected["expected_rule_ids"]) <= set(RULE_IDS)
        if expected["expected_rule_ids"]:
            assert expected["expected_status"] == "HOLD"
        else:
            assert expected["expected_status"] == "PENDING_REVIEW"
        assert set(expected["fields"]) == {
            "vendor",
            "doc_no",
            "doc_date",
            "supply_amount",
            "vat",
            "total",
        }
        assert expected["items"], "품목은 최소 1개여야 합니다"


def test_expected_status_distribution(manifest: list[dict]) -> None:
    statuses = [entry["expected_status"] for entry in manifest]
    assert statuses.count("PENDING_REVIEW") == 17  # 정상 16 + 중복 첫 건 1
    assert statuses.count("HOLD") == 19


def test_evidence_spans_point_at_values(manifest: list[dict]) -> None:
    for entry in manifest:
        expected = load_expected(entry["document_id"])
        text = (EVAL_DIR / entry["filename"]).read_text(encoding="utf-8")
        assert expected["evidence"], f"{entry['document_id']}에 근거 span이 없습니다"
        for path, span in expected["evidence"].items():
            assert span["page"] == 1
            start, end = span["char_start"], span["char_end"]
            assert 0 <= start < end <= len(text)
            assert text[start:end] == span["excerpt"], f"{entry['document_id']} {path} span 불일치"
            if path.startswith("items["):
                index = int(path.split("[")[1].split("]")[0])
                key = path.rsplit(".", 1)[1]
                expected_value = expected["items"][index][key]
            else:
                expected_value = expected["fields"][path]
            assert normalize(path, span["excerpt"]) == expected_value


def test_duplicate_pair_is_ordered(manifest: list[dict]) -> None:
    duplicates = [entry for entry in manifest if entry["category"] == "duplicate"]
    assert len(duplicates) == 2
    first, second = duplicates
    assert first["expected_rule_ids"] == []
    assert second["expected_rule_ids"] == ["DUPLICATE_DOCUMENT"]
    first_text = (EVAL_DIR / first["filename"]).read_text(encoding="utf-8")
    second_text = (EVAL_DIR / second["filename"]).read_text(encoding="utf-8")
    first_no = re.search(r"문서번호: (\S+)", first_text).group(1)  # type: ignore[union-attr]
    second_no = re.search(r"문서번호: (\S+)", second_text).group(1)  # type: ignore[union-attr]
    assert first_no == second_no


def test_missing_evidence_documents_derive_total(manifest: list[dict]) -> None:
    targets = [entry for entry in manifest if entry["category"] == "missing_evidence"]
    assert len(targets) == 2
    for entry in targets:
        text = (EVAL_DIR / entry["filename"]).read_text(encoding="utf-8")
        expected = load_expected(entry["document_id"])
        assert "※ 총액은 공급가액과 부가세의 합으로 확인함." in text
        assert "total" not in expected["evidence"]
        assert expected["fields"]["total"] == (
            expected["fields"]["supply_amount"] + expected["fields"]["vat"]
        )


def test_demo_set_is_separate(manifest: list[dict]) -> None:
    demo_files = sorted(DEMO_DIR.glob("*.txt"))
    assert len(demo_files) == 4
    eval_hashes = {entry["sha256"] for entry in manifest}
    for path in demo_files:
        assert hashlib.sha256(path.read_bytes()).hexdigest() not in eval_hashes


def test_vendor_registry_is_versioned() -> None:
    registry = json.loads(VENDOR_PATH.read_text(encoding="utf-8"))
    assert registry["registry_version"] == VENDOR_REGISTRY_VERSION
    assert registry["vendors"]
    assert len(set(registry["vendors"])) == len(registry["vendors"])


def test_dataset_contains_no_personal_data_patterns() -> None:
    patterns = {
        "주민등록번호": re.compile(r"\b\d{6}-\d{7}\b"),
        "휴대전화": re.compile(r"\b01[0-9]-\d{3,4}-\d{4}\b"),
        "이메일": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
        "계좌번호": re.compile(r"\b\d{3}-\d{2,6}-\d{4,6}\b"),
    }
    for path in sorted(EVAL_DIR.glob("*.txt")) + sorted(DEMO_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        for label, pattern in patterns.items():
            assert not pattern.search(text), f"{path.name}에 {label} 패턴이 있습니다"


def test_dataset_regenerates_identically() -> None:
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "generate_dataset.py"), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_vendor_names_are_registry_or_known_unknown() -> None:
    registry = set(json.loads(VENDOR_PATH.read_text(encoding="utf-8"))["vendors"])
    known_unknown = {"미등록물산", "없는상사", "가짜상회"}
    for path in sorted(EVAL_DIR.glob("*.txt")):
        match = re.search(r"^거래처: (.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            assert match.group(1).strip() in registry | known_unknown, path.name


ITEM_ROW = re.compile(r"^(?P<name>.+?)\s{2,}(?P<qty>\S+)\s{2,}(?P<unit>\S+)\s{2,}(?P<amount>\S+)$")


def test_item_rows_follow_documented_format(manifest: list[dict]) -> None:
    """파서가 의존하는 '2칸 이상 공백' 열 구분 계약을 데이터가 지키는지 확인한다."""
    for entry in manifest:
        expected = load_expected(entry["document_id"])
        text = (EVAL_DIR / entry["filename"]).read_text(encoding="utf-8")
        lines = text.splitlines()
        header_index = next(i for i, line in enumerate(lines) if line.startswith("품목명"))
        rows: list[str] = []
        for line in lines[header_index + 1 :]:
            if not line.strip():
                break
            rows.append(line)
        assert len(rows) == len(expected["items"]), entry["document_id"]
        for row, item in zip(rows, expected["items"], strict=True):
            assert "  " not in item["name"], f"{entry['document_id']} 품목명에 2칸 공백"
            match = ITEM_ROW.match(row)
            assert match, f"{entry['document_id']} 품목 행 형식 위반: {row!r}"
            assert int(match.group("qty").replace(",", "")) == item["qty"]
            assert int(match.group("unit").replace(",", "")) == item["unit_price"]
            assert int(match.group("amount").replace(",", "")) == item["amount"]
