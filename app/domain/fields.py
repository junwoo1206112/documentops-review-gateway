"""추출 대상 필드 계약.

docs/schema.md의 필드 표와 이 모듈이 일치하지 않으면
tests/test_contracts.py가 실패한다.
"""

from __future__ import annotations

# 문서 단위 스칼라 필드 (표시 순서 = 이 순서)
FIELD_KEYS: tuple[str, ...] = (
    "vendor",
    "doc_no",
    "doc_date",
    "supply_amount",
    "vat",
    "total",
)

# 품목(line item) 필드
ITEM_FIELD_KEYS: tuple[str, ...] = ("name", "qty", "unit_price", "amount")

# 필수 필드: 하나라도 없으면 MISSING_REQUIRED(blocking) → HOLD
REQUIRED_FIELDS: tuple[str, ...] = (
    "vendor",
    "doc_no",
    "doc_date",
    "items",
    "supply_amount",
    "vat",
    "total",
)

MONEY_FIELDS: frozenset[str] = frozenset({"supply_amount", "vat", "total"})

FIELD_LABELS: dict[str, str] = {
    "vendor": "거래처",
    "doc_no": "문서번호",
    "doc_date": "날짜",
    "items": "품목",
    "name": "품목명",
    "qty": "수량",
    "unit_price": "단가",
    "amount": "금액",
    "supply_amount": "공급가액",
    "vat": "부가세",
    "total": "총액",
}

# 평가 지표에서 문서 완전 일치를 계산할 때 비교하는 필드 순서
COMPARABLE_FIELDS: tuple[str, ...] = FIELD_KEYS + ("items",)


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key, key)
