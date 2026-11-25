# 평가 계약

목표는 "정확도"라는 단일 숫자가 아니라, **어떤 오류를 안전하게 잡아내고 어떤 대가를 치르는지**를
분모와 함께 공개하는 것이다.

## 1. 데이터 분리

| 디렉터리 | 용도 | 수정 규칙 |
|---|---|---|
| `fixtures/evaluation/` | Phase 4 지표 산출용 고정 36건 + 정답 | 테스트·평가 중 절대 수정하지 않는다(읽기 전용 관례). 변경은 새 `DATASET_VERSION`으로만 |
| `fixtures/demo/` | 화면·영상 시연용 4건 | 평가 지표에 포함하지 않는다 |
| `fixtures/vendors.json` | 거래처 레지스트리 | 버전 필드를 가진다 |

- 평가 실행은 빈 DB를 사용한다. `python -m app.evaluate`는 임시 SQLite 파일을 만들고 종료 시 삭제한다.
- 문서 접수 순서는 `manifest.jsonl`의 줄 순서다. 중복 판정이 순서에 의존하기 때문이다.
- 시각·처리 시간을 제외한 모든 결과는 같은 입력에서 바이트 단위로 같아야 한다(테스트로 검증).

## 2. 데이터셋 구성 (36건)

| 구분 | 건수 | 기대 상태 | 기대 규칙 |
|---|---|---|---|
| 정상 | 16 | `PENDING_REVIEW` | 없음 |
| 필수값 누락 | 3 | `HOLD` | `MISSING_REQUIRED` |
| 문서번호 형식 오류 | 2 | `HOLD` | `INVALID_DOC_NO` |
| 날짜 형식 오류 | 2 | `HOLD` | `INVALID_DATE` |
| 금액 형식 오류 | 1 | `HOLD` | `INVALID_MONEY` |
| 금액 불일치 | 6 | `HOLD` | `LINE_TOTAL_MISMATCH` |
| 중복 | 2 | 첫 건 `PENDING_REVIEW`, 둘째 `HOLD` | 둘째 `DUPLICATE_DOCUMENT` |
| 알 수 없는 거래처 | 2 | `HOLD` | `UNKNOWN_VENDOR` |
| 근거 없음 | 2 | `HOLD` | `MISSING_EVIDENCE` |

합계 36건. 문서 기준 집계는 `PENDING_REVIEW` 17건(정상 16 + 중복 첫 건), `HOLD` 19건이다.
각 문서의 정답은 `fixtures/evaluation/expected/<document_id>.json`에 둔다.

### 정답 파일 스키마

```json
{
  "document_id": "DOC-0001",
  "dataset_version": "synth-2026-11-26.1",
  "expected_status": "PENDING_REVIEW",
  "expected_rule_ids": [],
  "fields": {
    "vendor": "가온상사",
    "doc_no": "TX-2026-0001",
    "doc_date": "2026-03-04",
    "supply_amount": 430000,
    "vat": 43000,
    "total": 473000
  },
  "items": [
    {"name": "산업용 볼트 M8", "qty": 120, "unit_price": 1500, "amount": 180000}
  ],
  "evidence": {
    "vendor": {"page": 1, "char_start": 12, "char_end": 16, "excerpt": "가온상사"},
    "total": {"page": 1, "char_start": 401, "char_end": 407, "excerpt": "473,000"}
  }
}
```

- `fields`·`items`의 값은 **정규화된 값**이다(쉼표 제거, 정수 변환).
- 형식 오류로 파싱에 실패한 필드의 정답 값은 `null`이다. 원문 문자열(`2026-13-05`, `사십삼만원`)을
  값으로 남기는 추출은 오답 처리한다. 문서에 적힌 **유효한 값**만 필드 값이다.
- `expected_rule_ids`는 집합 비교다. 순서는 무시한다.
- `evidence`는 검증 가능한 span이 있는 필드만 담는다. 키는 `fields`와 같은 경로
  (`vendor`, `items[0].qty`, `supply_amount` …)이고, 파생·누락 필드는 **키를 생략**한다.
  `items` 자체(목록)의 span은 두지 않는다.

## 3. 지표 정의

`P` = 정답셋 문서 수(36), `F` = 비교 대상 필드 수.

### 3.1 필드별 Exact Match (field EM)

- 대상 필드: `vendor`, `doc_no`, `doc_date`, `supply_amount`, `vat`, `total`, 그리고 품목의 `name`·`qty`·`unit_price`·`amount`.
- 스칼라 필드의 분모: **항상 36**. 정답이 `null`(누락)이면 추출값도 `null`이어야 정답이다.
  → 누락을 "그럴듯하게 채워 넣는" 추출기는 이 지표에서 불리해진다.
- 품목 필드의 분모: 문서별 `max(정답 품목 수, 추출 품목 수)`의 합. `ordinal` 기준으로 비교하고,
  한쪽에만 있는 항목은 오답으로 센다. (예: 정답 2행·추출 3행이면 3이 분모)
- 보고: 필드별 EM, 필드별 `matched/total`, 그리고 필드별 EM의 산술 평균(macro).
- macro 평균은 필드 10개를 동등 가중한다. 금액 필드가 1개 더 많다는 이유로 왜곡되지 않게
  하기 위한 선택이며, 대신 문서 완전 일치(3.2)를 항상 함께 본다.

### 3.2 문서 완전 일치 (document EM)

- 분모: 36건.
- 조건: 3.1의 모든 필드가 정답과 일치.
- 상태(승인/HOLD)는 포함하지 않는다. 값 추출 품질만 본다.

### 3.3 HOLD 재현율 (hold recall)

- 양성(positive): `expected_status == "HOLD"`인 19건.
- `recall = (HOLD로 판정한 양성 수) / 19`
- 안전성 지표다. 낮으면 문제 문서를 승인 대기로 올려 보낸 것이다.

### 3.4 오보류율 (false hold rate)

- 음성(negative): `expected_status == "PENDING_REVIEW"`인 17건.
- `false_hold = (HOLD로 판정한 음성 수) / 17`
- 비용 지표다. 높으면 정상 문서가 사람을 불필요하게 부른다.
- `recall`과 항상 함께 보고한다. 한쪽만 인용하지 않는다.

### 3.5 규칙 일치 (rule match)

- 문서별로 `expected_rule_ids`와 실제 `rule_id` 집합이 같은 비율.
- 분모: 36건.
- "HOLD를 맞혔지만 이유가 다른" 경우를 잡기 위한 보조 지표다.

### 3.6 근거 유효율 (evidence validity)

- 분모: 값이 추출된 필드 수.
- 분자: `evidence_status == "verified"`이고 span 검사를 통과한 필드 수.
- `derived`/`missing`은 분모에는 들어가고 분자에서 빠진다.
- 근거가 없는데 값을 낸 추출기를 정확도로 가릴 수 없게 만드는 지표다.

### 3.7 처리 시간

- 단위: ms/doc. 측정 구간은 `ingestion.start → validation.end`다.
- p50, p95를 소수점 3자리로 반올림해 보고한다. 표본은 36건이며 신뢰구간은 주장하지 않는다.
- 시간은 환경 의존적이므로 **테스트에서 값을 단정하지 않는다.** `>= 0`과 필드 존재만 검증한다.
- 측정값은 `measurement` 섹션에 두고, 결정론 비교 대상에서 제외한다.

## 4. 리포트 스키마

`artifacts/evaluation_report.json`

```json
{
  "schema_version": "eval-report-1",
  "dataset_version": "synth-2026-11-26.1",
  "ruleset_version": "rules-1.0.0",
  "extractor_version": "deterministic-1.0.0",
  "documents": 36,
  "metrics": {
    "field_exact_match": {"vendor": {"matched": 34, "total": 36, "value": 0.944}, "...": {}},
    "field_exact_match_macro": 0.981,
    "document_exact_match": {"matched": 33, "total": 36, "value": 0.917},
    "hold_recall": {"matched": 19, "total": 19, "value": 1.0},
    "false_hold_rate": {"matched": 0, "total": 17, "value": 0.0},
    "rule_match": {"matched": 36, "total": 36, "value": 1.0},
    "evidence_validity": {"matched": 192, "total": 196, "value": 0.98}
  },
  "measurement": {"p50_ms": 11.2, "p95_ms": 24.8, "runs": 36},
  "failures": [
    {"document_id": "DOC-0031", "expected_status": "HOLD", "actual_status": "HOLD",
     "expected_rule_ids": ["MISSING_EVIDENCE"], "actual_rule_ids": ["MISSING_EVIDENCE"],
     "why": "값은 맞지만 총액 근거가 파생값이어서 승인 불가", "next": "이미지 문서에서 근거 span을 찾는 별도 규칙 필요"}
  ],
  "limitations": [
    "합성 한국어 문서 36건 기준이며 실제 기업 문서 분포를 대표하지 않는다.",
    "중복 판정은 접수 순서에 의존하므로, 운영 DB에서는 같은 문서의 상태가 재검증으로 바뀔 수 있다.",
    "OCR·이미지 문서·PDF 레이아웃은 평가 대상이 아니다.",
    "부가세율은 10% 단일 가정이다.",
    "reviewer_alias는 인증된 사용자가 아니다."
  ]
}
```

- `failures`는 최대 3건, `input → actual → why → next` 4요소를 모두 채운다.
- 지표 값은 소수점 3자리 반올림. `matched`/`total` 원값을 항상 함께 남긴다.
- `limitations`는 데이터셋 규모·합성 데이터·OCR 제외·한국어 규칙 범위를 명시한다.

## 5. 재현성 규칙

- 리포트 생성은 네트워크·외부 API·시스템 시각에 의존하지 않는다.
- 같은 커밋 + 같은 데이터셋이면 `metrics`, `failures`가 동일해야 한다(테스트).
- 데이터셋 파일이 바뀌면 `DATASET_VERSION`과 manifest SHA-256이 함께 바뀐다.
- `python -m app.evaluate`는 `fixtures/evaluation`이 쓰기 불가여도 동작해야 한다(읽기만).
