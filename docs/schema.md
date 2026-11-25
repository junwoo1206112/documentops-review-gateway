# 데이터·API 스키마 계약

이 문서는 구현보다 먼저 고정된 계약이다. 코드와 문서가 어긋나면 `tests/test_contracts.py`가 실패한다.
단일 출처는 다음 모듈이다.

| 계약 | 코드 |
|---|---|
| 상태·전이 | `app/domain/statuses.py` |
| 필드 | `app/domain/fields.py` |
| 규칙 ID·심각도 | `app/domain/rules.py` |
| 버전 | `app/version.py` |

## 1. 입력 계약

| 항목 | 값 |
|---|---|
| 파일 형식 | UTF-8 텍스트(`.txt`)만. PDF·이미지·스캔은 MVP 제외 |
| 인코딩 | UTF-8 (BOM 허용, 저장 시 제거) |
| 줄바꿈 | LF 또는 CRLF 허용, 내부에서는 LF로 정규화하지 않고 원문 그대로 보존 |
| 최대 크기 | 512 KiB (`MAX_UPLOAD_BYTES`) |
| 페이지 | MVP는 모든 문서를 `page=1`로 취급한다 |
| 원문 보존 | 업로드 원문은 수정하지 않고 `raw_text`로 저장한다. span은 이 원문 기준 문자 오프셋이다 |
| 오프셋 단위 | Python 문자열 인덱스(유니코드 코드 포인트). 바이트 오프셋이 아니다 |
| 줄바꿈 | 합성 `.txt`는 LF, 마지막 줄 뒤 개행 1개를 사용한다 |

### 문서 텍스트 레이아웃

파서가 결정론적으로 읽을 수 있는 고정 레이아웃을 사용한다. 실제 업무 문서의 축약형이며,
필드명·표 구조·금액 표기는 합성 문서 생성기가 보장한다.

```text
[거래명세서]
거래처: 가온상사
문서번호: TX-2026-0001
작성일자: 2026-03-04

품목명              수량      단가         금액
산업용 볼트 M8       120     1,500      180,000
철제 브래킷           40     6,250      250,000

공급가액: 430,000
부가세: 43,000
총액: 473,000
```

- 헤더 라벨은 `거래처:`, `문서번호:`, `작성일자:`, `공급가액:`, `부가세:`, `총액:` 정확히 사용한다.
- 품목 표는 `품목명`으로 시작하는 헤더 줄 다음부터 빈 줄 전까지다.
- 품목 열은 **2칸 이상 공백**으로 구분한다. 품목명은 공백 1칸을 포함할 수 있다.
- 금액은 `1,500`처럼 천 단위 쉼표를 쓰고 `원` 접미사는 선택이다.
- `총액` 줄이 없고 `※ 총액은 공급가액과 부가세의 합으로 확인함.` 주석이 있으면,
  파서는 총액을 `supply_amount + vat`로 계산하되 **`evidence_status=derived`**로 표시한다.
  이 값은 `MISSING_EVIDENCE`(blocking) 대상이다. 줄이 없고 주석도 없으면 `MISSING_REQUIRED`다.
- `※`로 시작하는 줄은 헤더·품목·합계 해석에서 무시한다.

## 2. 필드 계약

| key | 표시명 | 타입 | 필수 | 근거 필요 | 검증 |
|---|---|---|---|---|---|
| `vendor` | 거래처 | string | Y | Y | 거래처 레지스트리에 존재 |
| `doc_no` | 문서번호 | string | Y | Y | `^[A-Z]{2,4}-\d{4}-\d{4}$`, 대문자 정규화 |
| `doc_date` | 날짜 | date | Y | Y | `YYYY-MM-DD` 실제 달력 날짜 |
| `items` | 품목 | list | Y | Y | 최소 1개 |
| `items[].name` | 품목명 | string | Y | Y | 1자 이상 |
| `items[].qty` | 수량 | integer | Y | Y | 1 이상 |
| `items[].unit_price` | 단가 | integer | Y | Y | 0 이상, 원 단위 |
| `items[].amount` | 금액 | integer | Y | Y | 0 이상, 원 단위 |
| `supply_amount` | 공급가액 | integer | Y | Y | 0 이상, 원 단위 |
| `vat` | 부가세 | integer | Y | Y | 0 이상, 원 단위 |
| `total` | 총액 | integer | Y | Y | 0 이상, 원 단위 |

- 금액·수량은 원/개 단위 **정수**다. 소수·음수·통화기호 외 문자는 `INVALID_MONEY`다.
- 쉼표·`원`·`₩`·앞뒤 공백은 허용하고 정규화한다.
- 날짜는 `YYYY-MM-DD`만 허용한다. `2026.03.04`, `2026/03/04`, `26-3-4`는 `INVALID_DATE`다.
- `evidence_status`는 `verified`(원문 span에서 직접 인용), `derived`(계산·추론), `missing`(위치 없음) 중 하나다.
  `derived`와 `missing`은 모두 `MISSING_EVIDENCE`(blocking) 대상이다.

## 3. 상태 계약

| 상태 | 표시명 | 의미 | 종료 상태 |
|---|---|---|---|
| `INGESTED` | 접수됨 | 파일 저장 직후, 검증 전 | 아니오 |
| `PENDING_REVIEW` | 검토 대기 | blocking 이슈 없음, 사람 판정 대기 | 아니오 |
| `HOLD` | 보류 | blocking 이슈 존재, 사람 판정 대기 | 아니오 |
| `APPROVED` | 승인됨 | 사람이 승인 | 예 |
| `REJECTED` | 반려됨 | 사람이 반려 | 예 |

### 상태 전이표

| from | to | 조건 |
|---|---|---|
| `INGESTED` | `PENDING_REVIEW` | blocking 이슈 0건 |
| `INGESTED` | `HOLD` | blocking 이슈 1건 이상 |
| `PENDING_REVIEW` | `APPROVED` | 사람 승인 + 별칭 + 사유 |
| `PENDING_REVIEW` | `REJECTED` | 사람 반려 + 별칭 + 사유 |
| `PENDING_REVIEW` | `HOLD` | 재검증에서 blocking 이슈 발생(예: 이후 중복 접수) |
| `HOLD` | `PENDING_REVIEW` | 재검증에서 blocking 이슈 0건 |
| `HOLD` | `REJECTED` | 사람 반려 + 별칭 + 사유 |
| `HOLD` | `APPROVED` | **금지.** 반드시 `PENDING_REVIEW`를 거친다 |
| `APPROVED` | * | **금지.** 종료 상태 |
| `REJECTED` | * | **금지.** 종료 상태 |

- `INGESTED`는 API 응답에서 관측되지 않는다. 업로드 요청 한 번 안에서 검증까지 끝나 `PENDING_REVIEW` 또는 `HOLD`로 저장된다.
- 재검증(`revalidate`)은 `HOLD`/`PENDING_REVIEW`에서만 허용하고, 판정 근거와 무관하게 감사 이벤트를 남긴다.
- 승인·반려에는 `reviewer_alias`(1~40자)와 `reason`(1~500자)이 필수다.

## 4. 저장소 계약 (SQLite)

| 테이블 | 핵심 컬럼 | 규칙 |
|---|---|---|
| `documents` | `id`, `sha256`, `filename`, `raw_text`, `size_bytes`, `source_kind`, `status`, `extractor_version`, `ruleset_version`, `duplicate_of`, `received_at` | `raw_text`는 수정하지 않는다 |
| `extracted_fields` | `document_id`, `path`, `value_text`, `value_int`, `page`, `char_start`, `char_end`, `evidence_excerpt`, `evidence_status`, `confidence` | `path`는 `vendor`, `items[0].qty` 형식 |
| `validation_issues` | `document_id`, `rule_id`, `severity`, `path`, `message`, `status`, `created_at` | `status`는 `open`/`resolved` |
| `review_decisions` | `document_id`, `decision`, `reviewer_alias`, `reason`, `from_status`, `to_status`, `created_at` | 수정·삭제 API 없음 |
| `audit_events` | `event_id`, `document_id`, `event_type`, `from_status`, `to_status`, `actor`, `metadata_json`, `created_at` | **append-only**. UPDATE/DELETE는 DB 트리거가 차단 |

- `audit_events.event_type`: `DOCUMENT_INGESTED`, `VALIDATION_COMPLETED`, `REVALIDATED`, `DECISION_RECORDED`.
- 감사 이벤트는 시간순(`event_id` 오름차순)으로만 노출한다.
- 인덱스: `documents(status)`, `documents(sha256)`, `documents(doc_no)`, `extracted_fields(document_id)`, `validation_issues(document_id, status)`, `audit_events(document_id, event_id)`.

## 5. API 계약

오류 본문은 항상 다음 형태다.

```json
{"error": {"code": "E_CONFLICT", "message": "사람이 읽을 수 있는 설명", "details": null}}
```

| Method | Path | 성공 | 실패 |
|---|---|---|---|
| GET | `/api/health` | 200 `{status, version}` | - |
| GET | `/api/meta` | 200 버전·필드·규칙 카탈로그 | - |
| POST | `/api/documents` | 201 문서 상세 | 413 크기 초과, 415 형식·인코딩, 422 필수 파트 누락 또는 문서 레이아웃 해석 불가 |
| GET | `/api/documents` | 200 `{items, total}` (`status`, `limit`, `offset` 쿼리) | 422 잘못된 쿼리 |
| GET | `/api/documents/{id}` | 200 문서 상세 | 404 |
| POST | `/api/documents/{id}/revalidate` | 200 문서 상세 | 404, 409 종료 상태 |
| POST | `/api/documents/{id}/decision` | 200 문서 상세 | 404, 409 허용되지 않은 전이, 422 사유·별칭 누락 |
| GET | `/api/documents/{id}/audit` | 200 `{items}` | 404 |
| GET | `/api/evaluation/latest` | 200 최신 평가 리포트 | 404 리포트 없음 |

### 문서 상세 응답

```json
{
  "document": {
    "id": "…", "filename": "DOC-0001.txt", "sha256": "…", "size_bytes": 512,
    "source_kind": "text", "status": "HOLD", "duplicate_of": null,
    "extractor_version": "deterministic-1.0.0", "ruleset_version": "rules-1.0.0",
    "received_at": "2026-11-26T00:00:00+00:00"
  },
  "fields": [
    {"path": "vendor", "label": "거래처", "value": "가온상사", "value_int": null,
     "page": 1, "char_start": 12, "char_end": 16,
     "evidence_excerpt": "가온상사", "evidence_status": "verified", "confidence": 1.0}
  ],
  "items": [
    {"ordinal": 0, "name": "산업용 볼트 M8", "qty": 120, "unit_price": 1500, "amount": 180000}
  ],
  "issues": [
    {"rule_id": "LINE_TOTAL_MISMATCH", "severity": "blocking", "path": "total",
     "message": "금액 합계가 일치하지 않습니다: …", "status": "open"}
  ],
  "decisions": [
    {"decision": "APPROVE", "reviewer_alias": "reviewer-a", "reason": "…",
     "from_status": "PENDING_REVIEW", "to_status": "APPROVED", "created_at": "…"}
  ],
  "audit": [
    {"event_id": 1, "event_type": "DOCUMENT_INGESTED", "from_status": null,
     "to_status": "HOLD", "actor": "system", "created_at": "…"}
  ],
  "raw_text": "…"
}
```

- `fields`는 `docs/schema.md`의 필드 순서, `items[]`는 `ordinal` 순서로 고정한다.
- `issues`는 `(rule_id, path)` 오름차순으로 고정한다.
- `raw_text`는 상세 응답에만 포함한다.

### 업로드 요청

`multipart/form-data`, 파트 이름 `file`. Content-Type은 검사하지 않고 확장자·UTF-8 디코딩으로 판단한다.

### 판정 요청

```json
{"decision": "APPROVE", "reviewer_alias": "reviewer-a", "reason": "원문 대조 완료"}
```

- `decision`은 `APPROVE` 또는 `REJECT`다.
- 공백만 있는 별칭·사유는 422다.
- 같은 문서에 대한 중복 요청은 409다(이미 종료 상태).

## 6. 버전

| 항목 | 값 | 올리는 시점 |
|---|---|---|
| `APP_VERSION` | `0.1.0` | 릴리스 |
| `EXTRACTOR_VERSION` | `deterministic-1.0.0` | 파서 동작 변경 |
| `RULESET_VERSION` | `rules-1.0.0` | 규칙 추가·판정 변경 |
| `DATASET_VERSION` | `synth-2026-11-26.1` | 데이터셋 파일 변경 |

버전 3종은 문서 레코드, 감사 이벤트, 평가 리포트에 함께 기록된다.
