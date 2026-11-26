"""평가 리포트 읽기. 레이아웃별 리포트를 서로 덮어쓰지 않도록 파일 단위로 노출한다."""

from __future__ import annotations

import json
from pathlib import Path

LEGACY_REPORT = "evaluation_report.json"


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
        data.setdefault("dataset_name", path.stem)
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
