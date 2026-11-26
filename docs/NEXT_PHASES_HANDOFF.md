# 남은 구현 페이즈 — 인수자·LLM 실행 안내

최신화: 2026-11-27  
기준 커밋: `c772bf6` 이후 `main`  
현재 검증: 로컬 `178 passed`, dataset integrity 통과, 원격 CI 성공.

## 한눈에 보는 상태

| 구분 | 상태 | 지금 할 일 |
|---|---|---|
| Phase 13~15, 17, 17-I | 완료 | 다시 구현하지 말고 회귀만 확인 |
| Phase 16 OCR | 현재 릴리스 미도입 | 실제 스캔 문서 요구가 생길 때만 P-001 Gate를 새로 연다 |
| 실제 LLM 연결 | 결정 대기 | 모델·데이터·키·fallback·독립 평가를 먼저 결정한다 |
| Phase 18 인증·권한 | 결정 대기 | 실제 사용자별 역할·승인 위임 요구가 생길 때만 시작한다 |
| Phase 19 Postgres | 결정 대기 | 동시 검토자 2명 이상·다중 인스턴스·감사 외부화 중 하나가 생길 때만 시작한다 |
| Phase 20 세율 확장 | 결정 대기 | 관할·세율표·면세·반올림 시나리오가 확정될 때만 시작한다 |

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
