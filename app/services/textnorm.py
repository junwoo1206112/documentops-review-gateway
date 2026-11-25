"""문자열 정규화. 규칙·파서·평가가 같은 해석을 쓰도록 한 곳에 둔다."""

from __future__ import annotations

import re
from datetime import date

_MONEY_TOKEN = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)")
_DOC_NO = re.compile(r"[A-Z]{2,4}-\d{4}-\d{4}")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

_MONEY_DECORATIONS = (" ", "\t", "\u00a0", ",", "원", "₩")


def parse_money(raw: str | None) -> int | None:
    """'1,500원', '₩1500'을 1500으로. 해석 불가면 None(0과 구분)."""
    if raw is None:
        return None
    cleaned = raw
    for token in _MONEY_DECORATIONS:
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    if not _MONEY_TOKEN.fullmatch(cleaned):
        return None
    return int(cleaned)


def parse_iso_date(raw: str | None) -> str | None:
    """YYYY-MM-DD 실제 달력 날짜만 통과. 그 외는 None."""
    if raw is None:
        return None
    text = raw.strip()
    if not _ISO_DATE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def normalize_vendor(raw: str | None) -> str:
    if raw is None:
        return ""
    return " ".join(raw.split())


def normalize_doc_no(raw: str | None) -> str:
    if raw is None:
        return ""
    return "".join(raw.split()).upper()


def is_valid_doc_no(value: str | None) -> bool:
    if not value:
        return False
    return bool(_DOC_NO.fullmatch(value))


def round_half_up_vat(supply: int) -> int:
    """부가세 10%, half-up. 내림/올림 혼동을 막기 위해 한 곳에 둔다."""
    return (supply + 5) // 10
