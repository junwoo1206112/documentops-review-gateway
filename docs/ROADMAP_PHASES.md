# 남은 구현 로드맵 — 인수자·LLM 공용

최신화: 2026-11-27 (Phase 17-I 완료, Render 데모 재확인 완료, P-001 결정 패킷 추가)

이 문서는 구현 순서를 **약속**하는 것이 아니라, 이미 검증된 안전 계약을 훼손하지 않으면서
다음 인수자가 재개할 수 있게 만드는 권장 실행 경로다. P-001~P-006은 제품·운영 결정이므로,
해당 Gate가 닫히기 전에는 코드·스키마·외부 의존성을 추가하지 않는다.

## 현재 기준선

- 공개 증거: [Release v0.1.0-demo](https://github.com/junwoo1206112/documentops-review-gateway/releases/tag/v0.1.0-demo),
  WebM asset 5,850,941 bytes, SHA-256
  `841e5e92990b56fc2c1342d9738c7dfc0c8fe35b888b1aba24415f285ccbe664`.
- 원격 검증: [CI run 45702069278](https://github.com/junwoo1206112/documentops-review-gateway/actions/runs/45702069278) 성공 (`7b2c1ba`).
- 재현 기준선: 174 tests, 각 텍스트 레이아웃 36/36 문서 일치, HOLD 19/19, false HOLD 0/17, 규칙 36/36,
  근거 410/412(의도된 파생 총액 2건).
- 평가 증거: 레이아웃별 리포트 분리(`dataset_name`), `/evaluation` 두 표, CI artifact 2개.
- 불변 계약: 자동 승인 없음, `HOLD → APPROVED` 직접 전이 금지, blocking이면 HOLD,
  근거 span 필수, 감사 append-only. 상세는 [HANDOFF.md](../HANDOFF.md) 1절을 따른다.

## 인수자용 현재 상태와 실행 순서

### 이미 닫힌 페이즈 — 다시 구현하지 않는다

| Phase | 상태 | 인수자가 확인할 증거 |
|---|---|---|
| 13 | 완료 | 사람 청취 기록: [phase-13.md](reviews/phase-13.md) |
| 14 / 14-I | 완료 | 원문 재인용 scalar·기존 품목 셀 수정, 재검증, append-only 감사 |
| 15 | 완료 | 기존 공백 표와 파이프 표의 **독립** 36건 평가 |
| 17 | 완료 | `llm-contract-stub`의 opt-in 계약, span 누락 HOLD, provider 실패 422 |
| 17-I | 완료 | 레이아웃별 리포트 분리, CI·Docker 두 레이아웃 평가, 공개 시드 부분 복구 |

### 아직 구현하면 안 되는 페이즈 — Gate 입력이 먼저다

| 다음 Phase | 목적 | 반드시 먼저 확정할 입력 | 완료 판정 |
|---|---|---|---|
| 16 — OCR | 스캔 이미지/PDF 수용 | [P-001 결정 패킷](decisions/p001-ocr-gate.md)의 실제 입력 형식·OCR 엔진/라이선스·실행 환경·최소 품질 임계값·데이터 보존 정책 | `source_kind=scan` 전용 36건 이상, 별도 지표/CI, 낮은 신뢰도·좌표 없음은 HOLD, 텍스트 기준선 불변 |
| 실제 LLM 연결 (17 후속) | 실제 provider로 추출 보조 | 모델/계정 책임, 전송·보존 정책, 키 보관, 실패 fallback, 독립 평가셋 | 기본 deterministic 불변, 키 없는 CI, evidence 우회 없음, provider 실패 안전 종료 |
| 18 — 인증·권한 | 실제 사용자별 역할/승인 위임 | 역할표, 위임 규칙, 세션 수명, 감사 주체 ID | 401/403·역할별 API/UI·감사 주체 계약 테스트 |
| 19 — Postgres | 다중 인스턴스/동시성 | 동시 검토자 2명 이상 또는 다중 인스턴스/감사 외부화 요구 | migration/rollback, append-only·동시 승인 경쟁 통합 테스트 |
| 20 — 세율 확장 | 10% 고정 규칙 해제 | 관할, 세율표/적용일, 면세·영세율, 반올림 | 기존 10%와 새 세율 fixture·지표를 분리 보고 |

### 새 인수자/LLM의 안전한 재개 절차

1. `HANDOFF.md` → 이 문서 → `docs/decisions/pending.md` 순서로 읽는다.
2. `python -m pytest -q`, `python tools/generate_dataset.py --check`, 두 레이아웃의
   `python -m app.evaluate --dataset ...`를 모두 통과시킨다.
3. 위 표에서 **한 개 Gate만** 사용자와 결정한다. OCR·실제 LLM·운영화를 묶어 시작하지 않는다.
4. 선택한 페이즈는 독립 fixture/지표/테스트와 `docs/reviews/phase-N.md`를 같은 커밋에 남긴다.

## A/B/C 교차 검증과 권장 순서

| 관점 | 판단 | 로드맵 반영 |
|---|---|---|
| A. 업무/제품 전문가 | 현 MVP의 가장 큰 사용성 공백은 `MISSING_REQUIRED`를 안전하게 해소하는 경로다. 스캔·LLM보다 먼저 사람이 근거를 남긴 수정 정책을 정해야 한다. | Gate A → Phase 14를 첫 기능 후보로 둔다. |
| B. 보안/운영 전문가 | 다중 사용자·외부 배포 요구 없이 인증이나 Postgres를 먼저 넣으면 데모의 단순성과 재현성이 나빠진다. | P-004/P-006은 실제 운영 요구가 생긴 뒤, 인증·권한 설계 후 저장소 전환을 검토한다. |
| C. QA/평가 전문가 | 레이아웃·OCR·LLM을 기존 36건 기준선에 섞으면 회귀 원인을 분리할 수 없다. | 각 확장은 독립 fixture·지표·CI job을 먼저 만들고 기본 경로는 오프라인으로 유지한다. |

## 공통 시작 Gate (모든 기능 페이즈 전)

1. `HANDOFF.md`, 이 문서, `docs/decisions/pending.md`를 읽는다.
2. `python -m pytest -q`, `python tools/generate_dataset.py --check`,
   `python -m app.evaluate --dataset fixtures/evaluation`를 모두 통과시킨다.
3. 변경이 계약·규칙·필드·상태에 닿으면 단일 출처와 문서·정답·평가 버전을 같은 커밋에서 갱신한다.
4. 각 Phase 종료 시 `docs/reviews/phase-N.md`에 A/B/C 검토, 실패/개선, 실행 증거를 남긴다.

## Phase 13 — R-007 스크린리더 실사용 검토 (사람 검증)

**목적:** 자동 감사가 대체할 수 없는 실제 보조기술 사용성을 확인한다.

- 선행 조건: 로컬 서버와 demo fixture 4건.
- 절차: NVDA·Narrator·VoiceOver 중 사용 환경의 하나로 키보드만 사용해 업로드 → HOLD 상세 →
  정상 문서 승인 → 감사 이력까지 1회 완주한다.
- 기록: 사용한 도구/브라우저, 성공·실패 단계, 발견한 차단점, 재검증 방법을 `docs/reviews/phase-13.md`에 남긴다.
- 완료 기준: 차단점이 없거나, 발견된 차단점을 수정·테스트·재검증한 기록이 있다.
- 금지: 자동 DOM 검사만으로 완료 처리하지 않는다.

**완료 (2026-11-26):** Windows Narrator와 Chrome에서 격리 DB/포트 8001로 HOLD 문서의 오류 안내,
정상 문서의 승인, 판정·감사 이력을 키보드만으로 청취했다. 기록은 [Phase 13 리뷰](reviews/phase-13.md)에 있다.

## Gate A — P-003 사람 수정 정책 결정

**상태: 닫힘 (2026-11-26).** 아래 네 항목을 다음 값으로 확정했고, Phase 14를 구현했다.

1. 수정값의 근거: **원문 재인용만**. 원문에 없는 값은 만들 수 없다.
2. 수정 후 상태: **항상 재검증**, 자동 승인 없음.
3. 감사: 수정 전/후·근거 span·검토자·사유를 **영구 보존**(append-only).
4. 권한: `reviewer_alias` 유지(P-006 인증은 범위 밖).

상세 결정과 기각 대안은 [ADR 0003](adr/0003-human-correction.md), 구현 결과는
[Phase 14 리뷰](reviews/phase-14.md)에 있다.

## Phase 14 — 필드 단위 사람 수정 (완료, 스칼라 필드)

- 구현: `field_corrections`(append-only), `POST /api/documents/{id}/corrections`,
  상세 화면 수정 폼·이력, `fields`(추출 원본)와 `effective_fields`(수정 반영) 분리.
- 검증: 정상 수정, 원문에 없는 값 차단, 값-인용 불일치 차단, 모호한 인용 span 요구,
  종료 상태 409, 수정 이력 UPDATE/DELETE 차단, 재검증 후 수정 유지, 기존 36건 기준선 불변.
- 남은 범위: 수정 이력 필터/내보내기(누구에게 어떤 형식으로 노출할지 결정 후).

## Gate D — 품목(`items[]`) 수정 정책 결정

**상태: 닫힘 (2026-11-26).** 이번 구현은 아래 권장 기본안을 Gate D 결정으로 채택한다.

1. **행 식별자:** 원본 `ordinal`만 쓸지, `ordinal`과 원본 행 인용을 함께 고정할지.
2. **허용 편집:** `name`·`qty`·`unit_price`·`amount`의 셀 수정만 허용할지, 행 추가·삭제·순서 변경도
   허용할지.
3. **근거 단위:** 수정 셀의 span만 요구할지, 행 전체를 가리키는 anchor도 함께 요구할지.
4. **합계 처리:** 수정으로 생긴 라인 합계·공급가·부가세·총액 불일치를 재검증으로 HOLD할지,
   파생값을 자동으로 다시 계산할지.
5. **감사 표시:** 행 번호가 바뀌지 않도록 원본 ordinal·수정 전/후 셀값·span을 어떻게 보존할지.

결정: **원본 ordinal + 행 anchor를 고정하고, 기존 행의 단일 셀만 원문 재인용으로 수정한다.**
행 추가·삭제·재정렬과 원문에 없는 품목은 재업로드로 제한한다. 수정 뒤에는 현재 Phase 14와 같이
전체 규칙·중복·산술을 재실행하며, 불일치는 자동 보정하지 않고 HOLD로 남긴다.

## Phase 14-I — 품목 수정 (완료)

이 표기는 기존 Phase 15~20의 번호와 순서를 바꾸지 않는 Phase 14의 확장이다.

- 구현: `items[{ordinal}].name|qty|unit_price|amount`의 quote-backed correction, 행 anchor,
  append-only 이력, `effective_items` 분리, 재검증 UI/API.
- 비범위: 행 추가·삭제·정렬 변경, 원문에 없는 신규 품목, 자동 금액 보정, 자유 입력.
- 검증: 잘못된 ordinal/anchor 차단, 셀 인용 불일치 차단, 산술·중복 재검증, 과거 수정 이력 불변,
  기존 스칼라 correction과 36건 기준선 불변.
- 검증: 행 anchor 없는 수정·모호한 셀 인용을 차단하고, 유효 수정은 `effective_items`에만 반영한다.

## Phase 15 — 두 번째 텍스트 레이아웃 (R-006, 완료)

**우선순위:** 실제로 지원할 문서 변형이 제공된 경우에만 진행한다.

- 명세: `작성일:` + `품목 | 수량 | 단가 | 금액`을 고정 표식으로 쓰는 파이프 품목 표.
- 구현: 상호 배타적 detector → 레이아웃별 파서 → 공통 evidence/validation 경로.
- 검증: `fixtures/evaluation_layout2`의 독립 36건·정답·manifest, 혼합/모호 입력 422,
  기존·신규 레이아웃 각각 36/36 기준선.
- 상세: [Phase 15 리뷰](reviews/phase-15.md).

## Gate B — 확장 입력 방식 선택

아래 둘은 서로 독립적이며, 하나를 선택해도 다른 하나를 자동 승인하지 않는다.

- P-001 OCR: [결정 패킷](decisions/p001-ocr-gate.md)의 실제 요구·입력 형식·엔진/라이선스·실행 환경·최소 품질 임계값·보존 정책을 모두 확정한다.
- P-002 LLM: 비결정적 추출을 허용할 업무 범위, 모델/키 관리 책임, 실패 시 deterministic fallback은 무엇인지.

## Phase 16 — 스캔 OCR (조건부: P-001 결정 후)

- 분리 원칙: `source_kind=scan` 36건 이상을 텍스트 평가셋과 분리하고, OCR 지표·실패 사례·CI job을
  별도로 둔다.
- 안전 장치: 신뢰도 임계값 미달 또는 evidence span 미확보 시 자동 HOLD. 기본 CI의 외부 바이너리
  의존은 피하거나 격리한다.
- 완료 기준: 텍스트 기준선 불변, scan 지표표 별도 보고, 낮은 품질 입력이 승인으로 새지 않음.

## Phase 17 — LLM 추출 어댑터 계약 하네스 (완료)

- 순서: 네트워크 없는 contract stub → `ExtractionProvider` 계약 테스트 → evidence 적용 →
  feature flag/명시적 provider 선택 순서로 진행한다.
- 안전 장치: API 키 없이 전체 테스트 통과, 기본 extractor는 deterministic, 모델 출력도
  `apply_evidence`를 우회하지 않음.
- 완료 기준: provider 장애·형식 오류·근거 누락은 HOLD/명시적 오류가 되고 기본 평가 수치는 불변.
- 완료: `llm-contract-stub`을 opt-in으로 구현했다. 외부 모델·키·네트워크 없이
  `ExtractionProvider` 계약, span 누락의 `MISSING_EVIDENCE → HOLD`, provider 실패의 명시적
  422, 문서/감사 provider 버전을 고정했다. 실제 LLM 연결은 별도 Gate다.

## Gate C — 실제 운영 전환 결정

P-004·P-005·P-006은 포트폴리오 품질 개선이 아니라 운영 요구 변화다. 다음 중 하나가 문서화되기 전에는
Phase 18 이후를 시작하지 않는다: 동시 검토자 2명 이상, 다중 인스턴스, 실제 사용자별 권한/승인 위임,
실제 세율 시나리오.

## Phase 18 — 인증·권한 (조건부: P-006 결정 후)

- 먼저 결정: 역할 모델(검토자/승인자/관리자), 승인 위임, 세션 수명, 감사 주체의 불변 식별자.
- 구현: `reviewer_alias`와 실제 subject를 혼동하지 않으며, 권한 없는 결정·감사 조회를 명시적으로
  401/403으로 구분한다.
- 완료 기준: 역할별 API/UI 계약 테스트, 감사의 주체 추적, 기존 로컬 데모 모드의 안전한 유지 또는 명시적 분리.

## Phase 19 — Postgres 및 다중 인스턴스 (조건부: P-004 결정 후)

- 선행 조건: Phase 18의 주체/권한 모델 또는 동시성 요구가 확정됨.
- 구현: SQLite와 동일한 schema·append-only 제약·조건부 상태 전이를 migration으로 재현하고,
  동시 승인 경쟁을 통합 테스트한다.
- 완료 기준: migration rollback/runbook, 동시성·감사 불변성 검증, SQLite 데모 경로 또는 별도 개발 프로필 유지.

## Phase 20 — 부가세 규칙 확장 (조건부: P-005 결정 후)

- Gate: 세율표, 적용일, 면세·영세율·반올림 규칙, 데모할 관할 범위를 확정한다.
- 구현/검증: 규칙·데이터셋·정답·지표 버전을 함께 올리고 각 세율 경계의 synthetic case를 추가한다.
- 완료 기준: 세율을 추측하지 않으며, 기존 10% fixture 결과와 새 시나리오 결과를 분리 보고한다.

## 인수자용 빠른 선택표

| 사용자 요구 | 시작 지점 | 먼저 받아야 할 것 |
|---|---|---|
| 보조기술 품질을 닫고 싶다 | Phase 13 | 사람이 수행한 스크린리더 결과 |
| 누락 필드를 안전하게 고치고 싶다 | Phase 14 (완료) | 품목 수정은 후속 Gate |
| 기존 품목 행의 오인식을 고치고 싶다 | Gate D → Phase 14-I | 행 식별·허용 편집·합계 정책 |
| 다른 텍스트 양식을 받고 싶다 | Phase 15 | 합성 가능한 레이아웃 명세 |
| 스캔 PDF/이미지를 받고 싶다 | Gate B → Phase 16 | OCR 엔진·품질·운영 환경 |
| LLM 계약을 검증하고 싶다 | Phase 17 (완료) | 외부 호출 없는 `llm-contract-stub` |
| 실제 LLM을 연결하고 싶다 | 후속 Gate | 모델 책임·키 관리·fallback·독립 평가 |
| 실제 팀 운영/권한/다중 인스턴스가 필요하다 | Gate C → Phase 18/19 | 역할·배포·동시성 요구 |

## 미해결성 장부

| 트랙 | 상태 | 닫는 조건 |
|---|---|---|
| 접근성 실사용 | **완료** | Phase 13의 실제 스크린리더 기록 |
| P-003 사람 수정 | **완료** | 스칼라·기존 품목 셀의 원문 재인용 수정과 재검증을 제공 |
| 품목 수정 | **완료** | Gate D 결정과 Phase 14-I 구현 완료 |
| 레이아웃 2 | **완료** | 파이프 품목 표의 명세·독립 평가·422 경계 확정 |
| P-001 OCR | 의사결정 대기 | Gate B OCR 항목 확정 |
| P-002 LLM 계약 | **완료** | Phase 17 오프라인 provider 하네스 |
| 실제 LLM 연결 | 의사결정 대기 | 모델·데이터·키·fallback·평가 확정 |
| P-004/P-006 운영화 | 비목표 | Gate C의 운영 요구 발생 |
| P-005 세율 | 비목표 | 세율·관할 시나리오 확정 |
