"""검증 규칙 카탈로그(단일 출처).

docs/rules.md와 이 모듈의 규칙 ID·심각도가 다르면 tests/test_contracts.py가 실패한다.
실제 판정 로직은 app/services/validation.py에 있고, 이 모듈은 계약만 담는다.
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"
SEVERITIES: tuple[str, ...] = (SEVERITY_BLOCKING, SEVERITY_WARNING)


@dataclass(frozen=True)
class RuleDef:
    rule_id: str
    severity: str
    summary: str
    message_template: str


RULES: tuple[RuleDef, ...] = (
    RuleDef(
        rule_id="MISSING_REQUIRED",
        severity=SEVERITY_BLOCKING,
        summary="필수 필드가 없거나 비어 있다",
        message_template="{field} 값이 없습니다.",
    ),
    RuleDef(
        rule_id="INVALID_DOC_NO",
        severity=SEVERITY_BLOCKING,
        summary="문서번호가 정해진 패턴을 따르지 않는다",
        message_template="문서번호 형식이 올바르지 않습니다: {raw}",
    ),
    RuleDef(
        rule_id="INVALID_DATE",
        severity=SEVERITY_BLOCKING,
        summary="날짜가 YYYY-MM-DD 형식의 실제 달력 날짜가 아니다",
        message_template="날짜 형식이 올바르지 않습니다: {raw}",
    ),
    RuleDef(
        rule_id="INVALID_MONEY",
        severity=SEVERITY_BLOCKING,
        summary="금액을 원 단위 정수로 해석할 수 없다",
        message_template="금액 형식이 올바르지 않습니다: {raw}",
    ),
    RuleDef(
        rule_id="LINE_TOTAL_MISMATCH",
        severity=SEVERITY_BLOCKING,
        summary="품목 금액, 공급가액, 부가세, 총액의 산술 관계가 맞지 않는다",
        message_template="금액 합계가 일치하지 않습니다: {detail}",
    ),
    RuleDef(
        rule_id="DUPLICATE_DOCUMENT",
        severity=SEVERITY_BLOCKING,
        summary="같은 문서번호 또는 같은 파일 해시가 이미 접수되어 있다",
        message_template="중복 문서입니다: {detail}",
    ),
    RuleDef(
        rule_id="UNKNOWN_VENDOR",
        severity=SEVERITY_BLOCKING,
        summary="거래처가 등록된 거래처 목록에 없다",
        message_template="등록되지 않은 거래처입니다: {raw}",
    ),
    RuleDef(
        rule_id="MISSING_EVIDENCE",
        severity=SEVERITY_BLOCKING,
        summary="값은 있으나 원문 위치(span)로 검증할 수 없다",
        message_template="{field} 값의 원문 근거를 확인할 수 없습니다.",
    ),
)

RULE_IDS: tuple[str, ...] = tuple(rule.rule_id for rule in RULES)
RULE_BY_ID: dict[str, RuleDef] = {rule.rule_id: rule for rule in RULES}
