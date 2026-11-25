"""입력 검증: 확장자, 크기, UTF-8. 원문은 변형하지 않고 그대로 보관한다."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.config import ALLOWED_SUFFIXES
from app.errors import PayloadTooLargeError, UnsupportedFileError

_UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class IngestedDocument:
    filename: str
    sha256: str
    raw_text: str
    size_bytes: int


def ingest_bytes(filename: str, data: bytes, *, max_bytes: int) -> IngestedDocument:
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"파일은 {max_bytes}바이트 이하여야 합니다. (요청: {len(data)}바이트)"
        )
    if len(data) == 0:
        raise UnsupportedFileError("빈 파일은 처리할 수 없습니다.")

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        allowed = ", ".join(ALLOWED_SUFFIXES)
        raise UnsupportedFileError(
            f"지원하지 않는 파일 형식입니다: {suffix or '(없음)'}. 허용: {allowed}"
        )

    payload = data[len(_UTF8_BOM) :] if data.startswith(_UTF8_BOM) else data
    try:
        raw_text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedFileError("파일은 UTF-8 텍스트여야 합니다.") from exc
    if "\x00" in raw_text:
        raise UnsupportedFileError("파일에 NUL 문자가 포함되어 있습니다.")

    return IngestedDocument(
        filename=filename,
        sha256=hashlib.sha256(data).hexdigest(),
        raw_text=raw_text,
        size_bytes=len(data),
    )
