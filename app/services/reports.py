"""평가 리포트 읽기. 레이아웃별 리포트를 서로 덮어쓰지 않도록 파일 단위로 노출한다."""

from __future__ import annotations

import json
from pathlib import Path

LEGACY_REPORT = "evaluation_report.json"
LAYOUT2_LEGACY_REPORT = "evaluation_report_layout2.json"


def _dataset_name(path: Path, data: dict) -> str:
    """Phase 17-I 이전 리포트도 화면에서 올바른 레이아웃명으로 보여 준다."""
    declared = data.get("dataset_name")
    if isinstance(declared, str) and declared:
        return declared
    if path.name == LEGACY_REPORT:
        return "evaluation"
    if path.name == LAYOUT2_LEGACY_REPORT:
        return "evaluation_layout2"
    return path.stem.removeprefix("evaluation_report_")


def load_reports(artifacts_dir: Path) -> list[dict]:
    """artifacts의 `evaluation_report*.json`을 모두 읽는다. 깨진 파일은 건너뛴다."""
    if not artifacts_dir.exists():
        return []
    reports: list[dict] = []
    for path in sorted(artifacts_dir.glob("evaluation_report*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        data["dataset_name"] = _dataset_name(path, data)
        data["report_file"] = path.name
        reports.append(data)
    reports.sort(
        key=lambda report: (
            report.get("dataset_name") != "evaluation",
            str(report.get("dataset_name", "")),
        )
    )
    return reports


def primary_report(reports: list[dict], default_dataset: str) -> dict | None:
    for report in reports:
        if report.get("dataset_name") == default_dataset:
            return report
    return reports[0] if reports else None
