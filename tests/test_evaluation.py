from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.evaluate import evaluate_dataset, percentile, ratio
from app.main import create_app
from app.services.vendors import VendorRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "fixtures" / "evaluation"
LAYOUT2_DIR = PROJECT_ROOT / "fixtures" / "evaluation_layout2"
REGISTRY = VendorRegistry.load(PROJECT_ROOT / "fixtures" / "vendors.json")


def report() -> dict:
    return evaluate_dataset(EVAL_DIR, REGISTRY)


def _single_doc_dataset(tmp_path: Path, version: str) -> Path:
    dataset = tmp_path / "dataset"
    (dataset / "expected").mkdir(parents=True)
    text = (EVAL_DIR / "DOC-0001.txt").read_bytes()
    (dataset / "DOC-0001.txt").write_bytes(text)
    expected = json.loads((EVAL_DIR / "expected" / "DOC-0001.json").read_text(encoding="utf-8"))
    (dataset / "expected" / "DOC-0001.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    entry = {
        "sequence": 1,
        "document_id": "DOC-0001",
        "filename": "DOC-0001.txt",
        "sha256": hashlib.sha256(text).hexdigest(),
        "bytes": len(text),
        "category": "normal",
        "expected_status": "PENDING_REVIEW",
        "expected_rule_ids": [],
        "dataset_version": version,
    }
    (dataset / "manifest.jsonl").write_text(
        json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return dataset


def test_report_schema_and_versions() -> None:
    data = report()
    assert data["schema_version"] == "eval-report-1"
    assert data["dataset_version"] == "synth-2026-11-26.3"
    assert data["ruleset_version"] == "rules-1.0.0"
    assert data["extractor_version"] == "deterministic-1.1.0"
    assert data["documents"] == 36
    for key in (
        "field_exact_match",
        "field_exact_match_macro",
        "document_exact_match",
        "hold_recall",
        "false_hold_rate",
        "rule_match",
        "evidence_validity",
    ):
        assert key in data["metrics"]


def test_baseline_metrics_are_exact() -> None:
    metrics = report()["metrics"]
    assert metrics["document_exact_match"] == {"matched": 36, "total": 36, "value": 1.0}
    assert metrics["hold_recall"] == {"matched": 19, "total": 19, "value": 1.0}
    assert metrics["false_hold_rate"] == {"matched": 0, "total": 17, "value": 0.0}
    assert metrics["rule_match"] == {"matched": 36, "total": 36, "value": 1.0}

    fields = metrics["field_exact_match"]
    assert set(fields) == {
        "vendor",
        "doc_no",
        "doc_date",
        "supply_amount",
        "vat",
        "total",
        "name",
        "qty",
        "unit_price",
        "amount",
    }
    assert all(metric["value"] == 1.0 for metric in fields.values())
    assert fields["vendor"]["total"] == 36
    assert fields["qty"]["total"] == 51
    assert metrics["field_exact_match_macro"] == 1.0

    evidence = metrics["evidence_validity"]
    assert evidence["total"] == 412
    assert evidence["matched"] == 410
    assert evidence["value"] == 0.995


def test_pipe_layout_dataset_has_an_independent_perfect_baseline() -> None:
    data = evaluate_dataset(LAYOUT2_DIR, REGISTRY)
    assert data["documents"] == 36
    assert data["metrics"]["document_exact_match"] == {"matched": 36, "total": 36, "value": 1.0}
    assert data["metrics"]["rule_match"] == {"matched": 36, "total": 36, "value": 1.0}


def test_no_regressions_and_three_published_cases() -> None:
    data = report()
    assert data["regressions"] == []
    assert len(data["failures"]) == 3
    assert [case["document_id"] for case in data["failures"]] == [
        "DOC-0035",
        "DOC-0033",
        "DOC-0025",
    ]
    for case in data["failures"]:
        assert case["actual_status"] == "HOLD"
        assert case["why"]
        assert case["next"]
        assert case["actual_rule_ids"]


def test_report_is_deterministic_except_measurement() -> None:
    first = report()
    second = report()
    first.pop("measurement")
    second.pop("measurement")
    assert first == second


def test_measurement_shape() -> None:
    measurement = report()["measurement"]
    assert measurement["runs"] == 36
    assert measurement["p50_ms"] >= 0
    assert measurement["p95_ms"] >= measurement["p50_ms"]


def test_ratio_and_percentile_helpers() -> None:
    assert ratio(0, 0) == {"matched": 0, "total": 0, "value": 0.0}
    assert ratio(2, 3)["value"] == 0.667
    assert percentile([], 95) == 0.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0


def test_report_uses_manifest_dataset_version(tmp_path: Path) -> None:
    dataset = _single_doc_dataset(tmp_path, "custom-2026-11-26.9")
    data = evaluate_dataset(dataset, REGISTRY)
    assert data["dataset_version"] == "custom-2026-11-26.9"
    assert data["documents"] == 1
    assert data["metrics"]["document_exact_match"]["total"] == 1


def test_inconsistent_manifest_versions_are_rejected(tmp_path: Path) -> None:
    dataset = _single_doc_dataset(tmp_path, "v-one")
    manifest = dataset / "manifest.jsonl"
    second = json.loads(manifest.read_text(encoding="utf-8"))
    second["dataset_version"] = "v-two"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + json.dumps(second, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        evaluate_dataset(dataset, REGISTRY)


def test_empty_manifest_is_rejected(tmp_path: Path) -> None:
    dataset = tmp_path / "empty"
    dataset.mkdir()
    (dataset / "manifest.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate_dataset(dataset, REGISTRY)


def test_cli_writes_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.evaluate",
            "--dataset",
            str(EVAL_DIR),
            "--report",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["metrics"]["hold_recall"]["value"] == 1.0
    assert "hold_recall=1.0" in result.stdout


def test_cli_fails_cleanly_on_missing_dataset(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.evaluate",
            "--dataset",
            str(tmp_path / "nope"),
            "--report",
            str(tmp_path / "r.json"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 2
    assert "평가 실패" in result.stderr


def test_api_serves_latest_report(tmp_path: Path) -> None:
    settings = Settings(
        db_path=tmp_path / "api.db",
        vendor_registry_path=PROJECT_ROOT / "fixtures" / "vendors.json",
        evaluation_dir=EVAL_DIR,
        artifacts_dir=tmp_path / "artifacts",
        rate_limit_per_minute=0,
    )
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (settings.artifacts_dir / "evaluation_report.json").write_text(
        json.dumps(report(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/evaluation/latest")
        assert response.status_code == 200
        assert response.json()["metrics"]["rule_match"]["value"] == 1.0

        page = client.get("/evaluation")
        assert page.status_code == 200
        assert "hold_recall" in page.text
        assert "0.995" in page.text
        assert "DOC-0035" in page.text
