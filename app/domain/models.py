"""도메인 값 객체 (서비스 간 공유)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExistingDocument:
    """중복 판정에 필요한 기존 문서의 최소 정보."""

    document_id: str
    doc_no: str | None
    sha256: str
    status: str


@dataclass(frozen=True)
class FieldCorrection:
    """원문 재인용으로 검증된 사람 수정값. 추출값을 덮어쓰지 않고 재검증에 주입한다."""

    path: str
    value: str | int
    excerpt: str
    page: int
    char_start: int
    char_end: int
