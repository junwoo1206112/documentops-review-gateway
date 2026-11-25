from __future__ import annotations

import pytest

from app.services.textnorm import (
    is_valid_doc_no,
    normalize_doc_no,
    normalize_vendor,
    parse_iso_date,
    parse_money,
    round_half_up_vat,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,500", 1500),
        ("1500", 1500),
        ("1,500원", 1500),
        ("₩ 1,500", 1500),
        ("  13,500  ", 13500),
        ("0", 0),
        ("사십삼만원", None),
        ("1,50O", None),
        ("-100", None),
        ("1.5", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_money(raw: str | None, expected: int | None) -> None:
    assert parse_money(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-03-04", "2026-03-04"),
        ("2026-13-05", None),
        ("2026-02-30", None),
        ("2026.03.04", None),
        ("26-3-4", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_iso_date(raw: str | None, expected: str | None) -> None:
    assert parse_iso_date(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TX-2026-0001", True),
        ("ABC-2026-9999", True),
        ("TX-26-0001", False),
        ("TX2026-0001", False),
        ("tx-2026-0001", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_doc_no(raw: str | None, expected: bool) -> None:
    assert is_valid_doc_no(raw) is expected


def test_normalizers() -> None:
    assert normalize_doc_no(" tx-2026-0001 ") == "TX-2026-0001"
    assert normalize_vendor("  가온   상사 ") == "가온 상사"


@pytest.mark.parametrize(
    ("supply", "expected"),
    [(430000, 43000), (3702, 370), (13505, 1351)],
)
def test_vat_rounding_is_half_up(supply: int, expected: int) -> None:
    assert round_half_up_vat(supply) == expected
