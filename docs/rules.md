# 검증 규칙 계약

규칙 ID·심각도의 단일 출처는 `app/domain/rules.py`다. 이 문서와 코드가 어긋나면
`tests/test_contracts.py`가 실패한다.

## 1. 판정 원칙

- blocking 이슈가 **1건 이상**이면 `HOLD`, 0건이면 `PENDING_REVIEW`다. 예외는 없다.
- 규칙은 모델 판단이 아니라 코드로만 판정한다. 확률·점수는 판정에 쓰지 않는다.
- 한 문서에서 같은 규칙은 **최대 1건**의 이슈로 합친다. 단, `MISSING_REQUIRED`는 누락된 필드마다 1건이다.
- 이슈는 `(rule_id, path)` 오름차순으로 저장·노출한다.

### 연쇄 억제(cascade suppression)

원인 하나가 여러 규칙을 동시에 터뜨려 HOLD 사유를 흐리지 않도록, 상위 원인이 있으면
하위 검사를 건너뛴다.

| 상위 원인 | 건너뛰는 검사 |
|---|---|
| `vendor` 누락 | 이 문서의 `UNKNOWN_VENDOR` |
| `doc_date` 누락 | 이 문서의 `INVALID_DATE` |
| 금액 필드 누락 | 그 필드가 필요한 산술 검사 전체 |
| 금액 필드 파싱 실패(`INVALID_MONEY`) | 그 값을 쓰는 산술 검사 전체 |
| `items` 누락·빈 목록 | 품목 관련 산술 검사 전체 |

## 2. 규칙 카탈로그

| rule_id | 심각도 | 판정 조건 | 메시지 예시 |
|---|---|---|---|
| `MISSING_REQUIRED` | `blocking` | 필수 필드가 없거나 공백뿐이다 | `거래처 값이 없습니다.` |
| `INVALID_DATE` | `blocking` | `doc_date`가 `YYYY-MM-DD`가 아니거나 존재하지 않는 날짜다 | `날짜 형식이 올바르지 않습니다: 2026-13-05` |
| `INVALID_MONEY` | `blocking` | 수량·단가·금액을 원/개 단위 정수로 해석할 수 없다 | `금액 형식이 올바르지 않습니다: 사십삼만원` |
| `LINE_TOTAL_MISMATCH` | `blocking` | 4개 산술 관계 중 하나라도 어긋난다 | `금액 합계가 일치하지 않습니다: 품목 2 금액 250,000 ≠ 수량×단가 240,000` |
| `DUPLICATE_DOCUMENT` | `blocking` | 같은 `sha256` 또는 같은 정규화 `doc_no`의 문서가 이미 유효하게 접수되어 있다 | `중복 문서입니다: 문서번호 TX-2026-0001 (DOC-0007)` |
| `UNKNOWN_VENDOR` | `blocking` | 거래처가 레지스트리에 없다 | `등록되지 않은 거래처입니다: 없는상사` |
| `MISSING_EVIDENCE` | `blocking` | 값은 있으나 `evidence_status`가 `derived`/`missing`이거나 span이 원문과 맞지 않는다 | `총액 값의 원문 근거를 확인할 수 없습니다.` |

`warning` 심각도는 스키마에만 존재하고 MVP 규칙에는 쓰이지 않는다. 경고를 HOLD 사유로
오해하지 않도록, 판정은 `severity == "blocking"`만 센다.

## 3. 산술 관계 (LINE_TOTAL_MISMATCH)

모든 값은 원 단위 정수다. 아래 4개를 모두 확인하고, 어긋난 항목의 설명을 `; `로 합쳐 1건으로 만든다.

| # | 관계 | 비고 |
|---|---|---|
| 1 | `items[i].amount == items[i].qty * items[i].unit_price` | 항목별 |
| 2 | `supply_amount == Σ items[i].amount` | 합계 |
| 3 | `vat == round(supply_amount * 0.1)` | 반올림은 half-up. 합성 데이터는 10%만 사용 |
| 4 | `total == supply_amount + vat` | 최종 |

- `qty`는 1 이상, `unit_price`·`amount`·`supply_amount`·`vat`·`total`은 0 이상이어야 한다.
  범위를 벗어나면 `INVALID_MONEY`다.
- 부가세가 10%가 아닌 실제 업무 문서는 MVP에서 다루지 않는다. 별도 규칙이 필요하면
  `docs/decisions/pending.md`에 결정 요청으로 남긴다.

## 4. 중복 판정 (DUPLICATE_DOCUMENT)

- 비교 키: `sha256` 전체 일치 **또는** 정규화 문서번호 일치(앞뒤 공백 제거 + 대문자).
- 비교 대상: `REJECTED`가 아닌 기존 문서. 반려된 문서는 중복으로 보지 않는다.
- 판정 시점: 접수 시점. 문서는 접수 순서대로만 비교하므로, 고정 데이터셋 평가는
  manifest 순서로 접수하면 재현된다.
- 중복으로 판정된 문서도 저장한다. 그래야 감사 이력과 데모에서 "왜 보류됐는지"를 보여 줄 수 있다.
  `duplicate_of`에 원본 문서 ID를 남긴다.

## 5. 근거 판정 (MISSING_EVIDENCE)

span은 다음을 모두 만족해야 `verified`다.

1. `1 <= page`
2. `0 <= char_start < char_end <= len(raw_text)`
3. `raw_text[char_start:char_end]`가 `evidence_excerpt`와 같다
4. `evidence_excerpt`를 정규화(쉼표·`원`·`₩`·공백 제거)한 값이 추출값의 정규화 값과 같다

`char_start`가 없거나, 값이 파생(`derived`)이면 `verified`가 아니다. 값이 정답과 같아도
근거가 없으면 `HOLD`다. 이것이 이 프로젝트의 핵심 주장이다.

## 6. 규칙 실행 순서

```text
1. 필드 존재       → MISSING_REQUIRED
2. 형식            → INVALID_DATE, INVALID_MONEY
3. 산술            → LINE_TOTAL_MISMATCH
4. 거래처          → UNKNOWN_VENDOR
5. 중복            → DUPLICATE_DOCUMENT
6. 근거            → MISSING_EVIDENCE
7. 집계            → blocking ≥ 1 ? HOLD : PENDING_REVIEW
```

순서는 이슈 정렬이 아니라 **연쇄 억제 판단**을 위한 것이다. 최종 저장 순서는 `(rule_id, path)`다.

## 7. 재검증(VALIDATION 재실행)

- 기존 `open` 이슈는 `resolved`로 닫고, 새 이슈를 다시 만든다.
- 해소 가능한 대표 사례: 중복 상대 문서가 반려되어 `DUPLICATE_DOCUMENT`가 사라짐,
  거래처 레지스트리 갱신으로 `UNKNOWN_VENDOR`가 사라짐.
- 해소 불가능한 대표 사례: 원문에 값이 없는 `MISSING_REQUIRED`. 이때는 문서를 고쳐
  **새로 업로드**해야 한다. 필드 단위 사람 수정은 MVP 범위가 아니다.
- 재검증 후 상태는 `HOLD → PENDING_REVIEW` 또는 `PENDING_REVIEW → HOLD`만 가능하다.
  종료 상태(`APPROVED`, `REJECTED`)는 재검증 대상이 아니다.
