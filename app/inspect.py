"""한 파일을 DB 없이 검사하는 CLI. Phase 3 화면이 생기기 전의 확인 수단이다.

python -m app.inspect fixtures/evaluation/DOC-0001.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import Settings
from app.domain.fields import FIELD_LABELS
from app.services.ingestion import ingest_bytes
from app.services.pipeline import process_document
from app.services.vendors import VendorRegistry
from app.version import EXTRACTOR_VERSION, RULESET_VERSION


def _fmt_money(value: object) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return "-" if value is None else str(value)


def render(path: Path, settings: Settings) -> str:
    data = path.read_bytes()
    document = ingest_bytes(path.name, data, max_bytes=settings.max_upload_bytes)
    registry = VendorRegistry.load(settings.vendor_registry_path)
    result = process_document(
        document.raw_text,
        sha256=document.sha256,
        registry=registry,
    )

    lines = [
        f"문서: {path.name}",
        f"SHA-256: {document.sha256[:16]}…  ({document.size_bytes} bytes)",
        f"상태: {result.status} ({result.elapsed_ms:.3f} ms)",
        f"버전: {RULESET_VERSION} / {EXTRACTOR_VERSION}",
        "",
        "필드",
    ]
    for field in result.fields:
        span = "-"
        if field.char_start is not None and field.char_end is not None:
            span = f"1:{field.char_start}-{field.char_end}"
        lines.append(
            f"  {FIELD_LABELS.get(field.path.split('.')[-1], field.path):<8}"
            f" {_fmt_money(field.value):>12}  [{field.evidence_status}] {span}"
        )

    if result.items:
        lines.extend(["", "품목"])
        for item in result.items:
            lines.append(
                f"  {item.ordinal + 1}. {item.name}"
                f"  수량 {_fmt_money(item.qty)}"
                f"  단가 {_fmt_money(item.unit_price)}"
                f"  금액 {_fmt_money(item.amount)}"
            )

    lines.extend(["", "검증 이슈"])
    if result.issues:
        for issue in result.issues:
            lines.append(f"  [{issue.severity}] {issue.rule_id} ({issue.path}): {issue.message}")
    else:
        lines.append("  없음")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="문서 1건 추출·검증 결과 출력")
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    try:
        print(render(args.path, settings))
    except Exception as exc:  # noqa: BLE001 - CLI는 오류를 한 줄로 보여 준다
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
