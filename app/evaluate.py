"""고정 데이터셋 평가. 제품과 같은 파이프라인을 읽기 전용으로 반복 실행한다.

python -m app.evaluate --dataset fixtures/evaluation
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings
from app.domain.fields import ITEM_FIELD_KEYS
from app.domain.models import ExistingDocument
from app.services.extraction.base import ExtractedField
from app.services.pipeline import process_document
from app.services.vendors import VendorRegistry
from app.version import EXTRACTOR_VERSION, RULESET_VERSION

SCHEMA_VERSION = "eval-report-1"
SCALAR_FIELDS = ("vendor", "doc_no", "doc_date", "supply_amount", "vat", "total")

FAILURE_PRIORITY = ("missing_evidence", "unknown_vendor", "line_total_mismatch")
NEXT_STEP_BY_RULE = {
    "MISSING_EVIDENCE": "이미지·스캔 문서에서도 원문 span을 확보하는 별도 추출 경로가 필요합니다.",
    "UNKNOWN_VENDOR": "거래처 마스터 동기화와 신규 거래처 등록 절차가 필요합니다.",
    "LINE_TOTAL_MISMATCH": "발행 시스템의 반올림·세율 규칙 차이를 확인해야 합니다.",
    "MISSING_REQUIRED": "원문에 없는 값을 추론하지 않는 현재 원칙을 유지하되, 보완 요청 흐름을 설계해야 합니다.",
    "INVALID_DOC_NO": "문서번호 형식 예외 목록을 계약에 추가할지 결정해야 합니다.",
    "INVALID_DATE": "다른 날짜 표기(점·슬래시)를 정규화할지 결정해야 합니다.",
    "INVALID_MONEY": "한글 금액 표기(예: 사십삼만원)를 숫자로 바꿀지 결정해야 합니다.",
    "DUPLICATE_DOCUMENT": "중복 원본을 반려했을 때 후속 문서를 자동 재검증할지 결정해야 합니다.",
}

LIMITATIONS = (
    "합성 한국어 문서 36건 기준이며 실제 기업 문서 분포를 대표하지 않는다.",
    "중복 판정은 접수 순서에 의존하므로, 운영 DB에서는 같은 문서의 상태가 재검증으로 바뀔 수 있다.",
    "문서 레이아웃이 1종류다. 헤더 순서·표 형태가 다르면 422로 끝내고 추측하지 않는다.",
    "OCR·이미지 문서·PDF 레이아웃은 평가 대상이 아니다.",
    "부가세율은 10% 단일 가정이다.",
    "reviewer_alias는 인증된 사용자가 아니다.",
    "p50/p95는 36건 표본이며 신뢰구간을 주장하지 않는다.",
)


def ratio(matched: int, total: int) -> dict[str, Any]:
    return {
        "matched": matched,
        "total": total,
        "value": round(matched / total, 3) if total else 0.0,
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(p / 100.0 * len(ordered)) - 1)
    return round(ordered[index], 3)


def _scalar(extracted: dict[str, ExtractedField], key: str) -> Any:
    field = extracted.get(key)
    return field.value if field is not None else None


@dataclass
class _FieldTally:
    matched: int = 0
    total: int = 0

    def add(self, *, ok: bool) -> None:
        self.total += 1
        if ok:
            self.matched += 1


@dataclass
class _DocumentOutcome:
    document_id: str
    category: str
    expected_status: str
    actual_status: str
    expected_rules: tuple[str, ...]
    actual_rules: tuple[str, ...]
    field_mismatches: list[str] = field(default_factory=list)
    issue_messages: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


def evaluate_dataset(dataset_dir: Path, registry: VendorRegistry) -> dict[str, Any]:
    manifest_path = dataset_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.jsonl이 없습니다: {dataset_dir}")

    entries = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not entries:
        raise ValueError(f"manifest가 비어 있습니다: {manifest_path}")

    versions = {str(entry.get("dataset_version", "")) for entry in entries}
    if len(versions) != 1 or "" in versions:
        raise ValueError(
            "manifest의 dataset_version이 일관되지 않습니다: " + ", ".join(sorted(versions))
        )
    dataset_version = versions.pop()

    existing: list[ExistingDocument] = []
    tallies = {key: _FieldTally() for key in (*SCALAR_FIELDS, *ITEM_FIELD_KEYS)}
    outcomes: list[_DocumentOutcome] = []
    document_matched = 0
    evidence_matched = 0
    evidence_total = 0
    rule_matched = 0
    durations: list[float] = []

    for entry in entries:
        document_id = entry["document_id"]
        expected = json.loads(
            (dataset_dir / "expected" / f"{document_id}.json").read_text(encoding="utf-8")
        )
        raw_text = (dataset_dir / entry["filename"]).read_text(encoding="utf-8")
        result = process_document(
            raw_text,
            sha256=entry["sha256"],
            registry=registry,
            existing=tuple(existing),
        )
        extracted = result.by_path()
        mismatches: list[str] = []

        for key in SCALAR_FIELDS:
            actual = _scalar(extracted, key)
            expected_value = expected["fields"][key]
            tallies[key].add(ok=actual == expected_value)
            if actual != expected_value:
                mismatches.append(f"{key}: 기대 {expected_value!r}, 실제 {actual!r}")

        expected_items = expected["items"]
        actual_items = result.items
        item_count = max(len(expected_items), len(actual_items))
        for index in range(item_count):
            for key in ITEM_FIELD_KEYS:
                expected_value = expected_items[index][key] if index < len(expected_items) else None
                actual = getattr(actual_items[index], key) if index < len(actual_items) else None
                tallies[key].add(ok=actual == expected_value)
                if actual != expected_value:
                    mismatches.append(
                        f"items[{index}].{key}: 기대 {expected_value!r}, 실제 {actual!r}"
                    )

        actual_rules = tuple(sorted(issue.rule_id for issue in result.issues))
        if not mismatches:
            document_matched += 1
        if set(actual_rules) == set(expected["expected_rule_ids"]):
            rule_matched += 1

        for extracted_field in result.fields:
            if extracted_field.value is None:
                continue
            evidence_total += 1
            if extracted_field.evidence_status == "verified":
                evidence_matched += 1

        durations.append(result.elapsed_ms)
        existing.append(
            ExistingDocument(
                document_id=document_id,
                doc_no=_scalar(extracted, "doc_no"),
                sha256=entry["sha256"],
                status=result.status,
            )
        )
        outcomes.append(
            _DocumentOutcome(
                document_id=document_id,
                category=entry["category"],
                expected_status=expected["expected_status"],
                actual_status=result.status,
                expected_rules=tuple(sorted(expected["expected_rule_ids"])),
                actual_rules=actual_rules,
                field_mismatches=mismatches,
                issue_messages=[issue.message for issue in result.issues],
                elapsed_ms=result.elapsed_ms,
            )
        )

    positives = [outcome for outcome in outcomes if outcome.expected_status == "HOLD"]
    negatives = [outcome for outcome in outcomes if outcome.expected_status == "PENDING_REVIEW"]
    hold_hits = sum(1 for outcome in positives if outcome.actual_status == "HOLD")
    false_holds = sum(1 for outcome in negatives if outcome.actual_status == "HOLD")

    field_metrics = {key: ratio(tally.matched, tally.total) for key, tally in tallies.items()}
    macro = round(statistics.fmean(metric["value"] for metric in field_metrics.values()), 3)

    metrics = {
        "field_exact_match": field_metrics,
        "field_exact_match_macro": macro,
        "document_exact_match": ratio(document_matched, len(outcomes)),
        "hold_recall": ratio(hold_hits, len(positives)),
        "false_hold_rate": ratio(false_holds, len(negatives)),
        "rule_match": ratio(rule_matched, len(outcomes)),
        "evidence_validity": ratio(evidence_matched, evidence_total),
    }

    regressions = [
        {
            "document_id": outcome.document_id,
            "expected_status": outcome.expected_status,
            "actual_status": outcome.actual_status,
            "expected_rule_ids": list(outcome.expected_rules),
            "actual_rule_ids": list(outcome.actual_rules),
            "field_mismatches": outcome.field_mismatches,
        }
        for outcome in outcomes
        if outcome.actual_status != outcome.expected_status
        or set(outcome.actual_rules) != set(outcome.expected_rules)
        or outcome.field_mismatches
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "ruleset_version": RULESET_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "documents": len(outcomes),
        "metrics": metrics,
        "measurement": {
            "p50_ms": percentile(durations, 50),
            "p95_ms": percentile(durations, 95),
            "runs": len(durations),
        },
        "failures": _failure_cases(outcomes),
        "regressions": regressions,
        "limitations": list(LIMITATIONS),
    }


def _failure_cases(outcomes: list[_DocumentOutcome]) -> list[dict[str, Any]]:
    """자동 승인되지 않은 대표 문서 3건을 입력 → 실제 → 왜 → 다음 형식으로 공개한다."""
    cases: list[dict[str, Any]] = []
    for category in FAILURE_PRIORITY:
        outcome = next(
            (
                item
                for item in outcomes
                if item.category == category and item.actual_status == "HOLD"
            ),
            None,
        )
        if outcome is None:
            continue
        rule_id = outcome.actual_rules[0] if outcome.actual_rules else "MISSING_REQUIRED"
        cases.append(
            {
                "document_id": outcome.document_id,
                "category": outcome.category,
                "expected_status": outcome.expected_status,
                "actual_status": outcome.actual_status,
                "expected_rule_ids": list(outcome.expected_rules),
                "actual_rule_ids": list(outcome.actual_rules),
                "why": outcome.issue_messages[0] if outcome.issue_messages else "blocking 이슈",
                "next": NEXT_STEP_BY_RULE.get(rule_id, "규칙과 데이터 계약을 재검토합니다."),
            }
        )
    return cases


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="고정 데이터셋 평가")
    parser.add_argument("--dataset", type=Path, default=settings.evaluation_dir)
    parser.add_argument(
        "--report", type=Path, default=settings.artifacts_dir / "evaluation_report.json"
    )
    args = parser.parse_args(argv)

    try:
        registry = VendorRegistry.load(settings.vendor_registry_path)
        report = evaluate_dataset(args.dataset, registry)
    except (FileNotFoundError, ValueError) as exc:
        print(f"평가 실패: {exc}", file=sys.stderr)
        return 2

    write_report(report, args.report)
    metrics = report["metrics"]
    print(f"dataset={report['dataset_version']} documents={report['documents']}")
    print(f"document_em={metrics['document_exact_match']['value']}")
    print(
        f"hold_recall={metrics['hold_recall']['value']} ({metrics['hold_recall']['matched']}/{metrics['hold_recall']['total']})"
    )
    print(
        f"false_hold_rate={metrics['false_hold_rate']['value']} ({metrics['false_hold_rate']['matched']}/{metrics['false_hold_rate']['total']})"
    )
    print(f"rule_match={metrics['rule_match']['value']}")
    print(f"evidence_validity={metrics['evidence_validity']['value']}")
    print(f"p50={report['measurement']['p50_ms']}ms p95={report['measurement']['p95_ms']}ms")
    print(f"report={args.report}")
    if report["regressions"]:
        print(f"회귀 {len(report['regressions'])}건:", file=sys.stderr)
        for regression in report["regressions"]:
            print(f"  {regression['document_id']}: {regression}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
