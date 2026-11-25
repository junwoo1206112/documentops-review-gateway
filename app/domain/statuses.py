"""문서 상태와 허용 전이의 단일 출처(single source of truth).

docs/schema.md의 상태 전이표와 이 모듈이 일치하지 않으면
tests/test_contracts.py가 실패한다.
"""

from __future__ import annotations

STATUSES: tuple[str, ...] = (
    "INGESTED",
    "PENDING_REVIEW",
    "HOLD",
    "APPROVED",
    "REJECTED",
)

# 사람이 최종 판정한 상태. 이후 어떤 전이도 허용하지 않는다.
TERMINAL_STATUSES = frozenset({"APPROVED", "REJECTED"})

# 보류(HOLD)는 자동 해소되지 않는다. 규칙 재검증 또는 반려만 허용한다.
TRANSITIONS: dict[str, frozenset[str]] = {
    "INGESTED": frozenset({"PENDING_REVIEW", "HOLD"}),
    "PENDING_REVIEW": frozenset({"APPROVED", "REJECTED", "HOLD"}),
    "HOLD": frozenset({"PENDING_REVIEW", "REJECTED"}),
    "APPROVED": frozenset(),
    "REJECTED": frozenset(),
}

# HOLD에서 승인으로 가는 직접 전이는 계약 위반이다.
FORBIDDEN_TRANSITIONS: tuple[tuple[str, str], ...] = (("HOLD", "APPROVED"),)

STATUS_LABELS: dict[str, str] = {
    "INGESTED": "접수됨",
    "PENDING_REVIEW": "검토 대기",
    "HOLD": "보류",
    "APPROVED": "승인됨",
    "REJECTED": "반려됨",
}

DECISIONS: tuple[str, ...] = ("APPROVE", "REJECT")

DECISION_LABELS: dict[str, str] = {
    "APPROVE": "승인",
    "REJECT": "반려",
}


class InvalidTransition(Exception):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"허용되지 않은 상태 전이입니다: {source} -> {target}")
        self.source = source
        self.target = target


def can_transition(source: str, target: str) -> bool:
    return target in TRANSITIONS.get(source, frozenset())


def assert_transition(source: str, target: str) -> None:
    if (source, target) in FORBIDDEN_TRANSITIONS:
        raise InvalidTransition(source, target)
    if not can_transition(source, target):
        raise InvalidTransition(source, target)


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)
