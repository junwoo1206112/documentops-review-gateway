# 남은 구현 페이즈 — 인수자·LLM 실행 안내

최신화: 2026-11-27  
기준: `main` (2026-11-27, Phase 17-J)  
현재 검증: 로컬 `181 passed`, dataset integrity 통과, 원격 CI 성공.

## 한눈에 보는 상태

| 구분 | 상태 | 지금 할 일 |
|---|---|---|
| Phase 13~15, 17, 17-I, 17-J | 완료 | 다시 구현하지 말고 회귀만 확인 |
| Phase 16 OCR | 현재 릴리스 미도입 | 실제 스캔 문서 요구가 생길 때만 P-001 Gate를 새로 연다 |
| 실제 LLM 연결 | 결정 대기 | 모델·데이터·키·fallback·독립 평가를 먼저 결정한다 |
| Phase 18 인증·권한 | 결정 대기 | 실제 사용자별 역할·승인 위임 요구가 생길 때만 시작한다 |
| Phase 19 Postgres | 결정 대기 | 동시 검토자 2명 이상·다중 인스턴스·감사 외부화 중 하나가 생길 때만 시작한다 |
| Phase 20 세율 확장 | 결정 대기 | 관할·세율표·면세·반올림 시나리오가 확정될 때만 시작한다 |

## 단일 재개 매트릭스 — 인수자·LLM이 따라야 할 목록

**현재 즉시 구현 가능한 기능은 없다.** 아래 행은 실제 요구가 생겨 Gate 입력이 확정될 때만
한 번에 하나씩 연다. `첫 구현 단위`보다 앞의 열이 비어 있으면 코드를 추가하지 않는다.

| 페이즈 | 상태·시작 신호 | 오너가 먼저 확정할 값 | 첫 구현 단위 | 검증·완료 기준 | 절대 하지 말 것 |
|---|---|---|---|---|---|
| 14-II 수정 이력 조회·내보내기 | 후보. 누가 어떤 수정 이력을 보거나 내보내야 할 때 | 대상 역할, 필터 범위, CSV/JSON 형식, 보존·개인정보 정책 | read-only 필터와 내보내기 계약 | 결과가 `field_corrections`·감사 이벤트와 일치, 공개 데모는 export 비노출 | append-only 원본 변경, 권한 없는 export, 공개 데모에 민감 경로 노출 |
| 15-II 추가 텍스트 레이아웃 | 후보. 실제 샘플·명세가 제공될 때 | 고정 표식, 허용/거부 경계, 품목 표 형식 | 상호 배타 detector와 전용 parser | 새 합성 36건·정답·manifest·CI 리포트, 기존 2개 기준선 불변 | 기존 fixture에 섞기, 모호한 입력 추측 처리 |
| 16 OCR | 미도입. 실제 스캔 문서 요구가 생길 때 | MIME·크기·페이지 수, 엔진/라이선스, 실행 위치·외부 전송, confidence·좌표, 보존/삭제 | scan 전용 ingestion/provider 경계 | scan 36건 이상, 독립 지표·CI, 저신뢰/근거 누락 `HOLD` | 이미지/PDF 허용·원본 보관·외부 OCR 호출을 Gate 전 추가 |
| 17-II 실제 LLM | Gate 대기. 실제 모델 보조 요구가 생길 때 | 모델/계정·비용, 키 회전, 전송·보존/DPA, egress allowlist, fallback, 독립 평가 | 명시 opt-in provider 어댑터 | 키 없는 기본 CI, evidence 우회 없음, 장애 명시 종료/fallback, 독립 평가 | 키·원문을 로그/저장소/오류에 남기기, 자동 승인 |
| 18 인증·권한 | Gate 대기. 실제 역할·위임 요구가 생길 때 | IdP/세션, 역할표, 위임, 세션 만료·로그아웃, 감사 subject | subject와 `reviewer_alias` 분리 | 역할별 401/403·CSRF·rate limit·위임 감사 테스트 | alias를 인증 주체로 사용, 권한 없이 승인·감사 조회 허용 |
| 19 Postgres·다중 인스턴스 | Gate 대기. 동시 검토자 2명 이상·다중 인스턴스·감사 외부화 중 하나 발생 | 배포 토폴로지, 백업/복구 RTO, DB 역할·비밀값, migration/rollback | SQLite 호환 migration과 최소권한 DB 역할 | backup/restore 리허설, append-only trigger, 동시 승인 경쟁·rollback 통합 테스트 | 백업 없는 migration, SQLite 데모 경로 제거, 감사 제약 누락 |
| 20 세율 확장 | Gate 대기. 실제 관할·세율 시나리오가 확정될 때 | 관할, 세율표·적용일, 면세/영세율, 반올림, 과거 문서 재계산 | versioned tax rules + 전용 synthetic fixture | 세율 경계 fixture·감사 규칙 버전, 기존 10% 결과와 분리 리포트 | 세율 추측, 법률 자문처럼 표현, 기존 결과 덮어쓰기 |

### Gate 결정 기록 템플릿

선택한 행을 시작할 때 아래를 이슈·ADR·결정 문서에 그대로 채운다.

```text
선택 페이즈:
실제 사용자 요구/시작 신호:
오너 결정값:
처리하는 데이터와 보존·삭제 정책:
외부 서비스·키·라이선스 책임(없으면 없음):
기본 경로와 실패 fallback:
독립 fixture·평가·CI artifact:
명시적 비범위:
완료 판정 담당자와 증거 링크:
```

## 항상 먼저 할 검증

새 인수자나 LLM은 기능을 추가하기 전에 아래를 모두 통과시킨다.

```bash
python -m pytest -q
python tools/generate_dataset.py --check
python -m app.evaluate --dataset fixtures/evaluation --report artifacts/evaluation_report.json
python -m app.evaluate --dataset fixtures/evaluation_layout2 --report artifacts/evaluation_report_evaluation_layout2.json
```

기준선은 두 텍스트 레이아웃 각각 문서 일치 36/36, HOLD 재현 19/19, 오보류 0/17,
규칙 일치 36/36, 근거 유효 410/412이다. 새 트랙은 이 기준선과 fixture·지표·CI 리포트를
공유하거나 덮어쓰면 안 된다.

## Phase 16 — OCR (재개 조건부)

현재 결정: **미도입.** 현 릴리스는 합성 `.txt`와 `source_kind=text`만 지원한다.

재개 조건은 실제 스캔 문서 요구이며, [P-001 결정 패킷](decisions/p001-ocr-gate.md)의 다음 값을
모두 확정해야 한다.

1. 입력 형식(PNG/JPEG, 이미지 PDF 등)
2. OCR 엔진·라이선스와 실행 위치
3. 외부 전송 여부와 원본 보존·삭제 정책
4. 최소 confidence, evidence span/좌표 형식

구현 시 완료 기준은 scan 전용 합성 36건 이상, 독립 지표·CI, 저신뢰/근거 누락 자동 `HOLD`,
두 텍스트 기준선 불변이다. 이미지/PDF 확장자나 OCR provider를 이 결정 전에는 추가하지 않는다.

## Phase 17 후속 — 실제 LLM 연결 (조건부)

현재 완료 범위는 네트워크 없는 `llm-contract-stub`뿐이다. 실제 모델 연결은 다음을 결정한 뒤에만
시작한다.

1. 허용 모델과 계정·비용 책임
2. 문서 데이터의 외부 전송·보존 정책 및 키 관리
3. provider 장애 시 동작(명시적 오류 또는 결정론 parser fallback)
4. 기존 평가와 분리된 독립 평가셋·성공/실패 기준

수용 기준은 기본 `deterministic` 경로와 키 없는 CI가 불변이고, 모델 결과도 evidence 검증을
우회하지 않으며, 실패가 자동 승인으로 이어지지 않는 것이다.

## Phase 18 — 인증·권한 (조건부)

시작 신호: 실제 사용자별 역할 또는 승인 위임 요구.

먼저 역할표(검토자·승인자·관리자), 위임 규칙, 세션 수명, 감사에 남길 불변 subject ID를 정한다.
그 후 역할별 API/UI 계약, 401/403 구분, 감사 주체 추적을 구현한다. 기존 `reviewer_alias` 데모
모드와 인증 subject를 혼동하지 않는다.

## Phase 19 — Postgres·다중 인스턴스 (조건부)

시작 신호: 동시 검토자 2명 이상, 다중 인스턴스 배포 또는 감사 로그 외부화 요구.

Phase 18의 주체 모델 또는 동시성 요구를 먼저 고정한다. SQLite와 같은 상태 전이·append-only
감사 제약을 migration으로 재현하고, 동시 승인 경쟁·rollback·복구 runbook을 통합 테스트한다.
로컬 SQLite 데모는 별도 개발 프로필로 유지한다.

## Phase 20 — 세율 확장 (조건부)

시작 신호: 실제 데모할 관할과 세율 시나리오 확정.

세율표·적용일·면세/영세율·반올림을 먼저 문서화한다. 그 다음 규칙·합성 fixture·정답·지표 버전을
함께 추가하며, 기존 10% 결과와 새 시나리오 결과는 분리 보고한다.

## Phase 14-II — 수정 이력 필터·내보내기 (후속 후보)

Phase 14/14-I의 원문 재인용 수정과 품목 셀 수정은 완료됐다. 남은 후보는 수정 이력을
누구에게 어떤 형식으로 보일지다. 역할·내보내기 형식·보존 정책이 확정될 때만 read-only
필터/내보내기를 추가하며, append-only 원본·감사 이벤트와 결과가 일치해야 한다.

## Phase 15-II — 추가 텍스트 레이아웃 (후속 후보)

현재 지원 범위는 공백 표와 파이프 표 두 가지다. 실제 샘플과 고정 표식 명세가 제공될 때만
새 detector·parser를 추가한다. 새 레이아웃은 독립 합성 36건·정답·manifest·CI 리포트를 가지며,
혼합·모호 입력은 계속 422여야 한다.

## 실행 원칙

1. 한 번에 Gate 하나만 연다. OCR·실제 LLM·운영화를 묶지 않는다.
2. 새로운 입력/모델/인증/DB는 사용자 결정과 ADR을 먼저 남긴다.
3. 각 페이즈는 독립 fixture·기대 결과·실패 사례·CI 리포트·`docs/reviews/phase-N.md`를 같은 변경에 포함한다.
4. 자동 승인, `HOLD → APPROVED` 직접 전이, 근거 없는 값, 감사 수정/삭제는 어떤 페이즈에서도 허용하지 않는다.

## 먼저 읽을 자료

1. [HANDOFF.md](../HANDOFF.md)
2. [전체 로드맵](ROADMAP_PHASES.md)
3. [결정 장부](decisions/pending.md)
4. 선택한 Gate의 ADR 및 결정 패킷

