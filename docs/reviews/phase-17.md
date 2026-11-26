# Phase 17 — 오프라인 LLM 추출 어댑터 계약 하네스

- 날짜: 2026-11-26
- 상태: **완료 (계약 하네스만)**
- 범위: 실제 모델·API 키·네트워크를 추가하지 않고, 선택형 provider가 기존 근거·검증 경로를
  우회하지 못하도록 고정한다.

## A/B/C 교차 검토

| 관점 | 지적 | 반영 |
|---|---|---|
| A. 제품 | 운영 수요가 없는 인증/Postgres보다 이미 존재하는 `ExtractionProvider`의 선택 경계를 먼저 검증하는 편이 되돌리기 쉽다. | `EXTRACTION_PROVIDER=llm-contract-stub`을 명시 opt-in으로 추가하고 기본값은 `deterministic`으로 유지했다. |
| B. 보안/운영 | 외부 모델은 키·개인정보 전송·비결정성·근거 책임이 결정되기 전 연결하면 안 된다. | 모델명, 키, HTTP 호출, 새 의존성을 전혀 넣지 않았다. 지원하지 않는 provider는 앱 시작 시 명시적으로 거절한다. |
| C. QA/평가 | provider 출력도 span 누락이면 기존 `MISSING_EVIDENCE → HOLD`에 도달해야 하고, 실패를 조용히 fallback하면 안 된다. | span 없는 결과의 HOLD와 provider 실패의 422를 계약 테스트로 고정했다. 기존 두 36건 평가셋은 기본 deterministic 경로로 유지한다. |

## 구현

- `app/services/extraction/providers.py`: `deterministic`과 `llm-contract-stub`만 허용하는
  provider 팩토리 및 네트워크 없는 스텁.
- `Settings.extraction_provider` / `EXTRACTION_PROVIDER`: 명시 선택값. 기본은 `deterministic`.
- 파이프라인은 선택 provider 결과에도 반드시 `apply_evidence`와 기존 8개 규칙을 실행한다.
- 문서·감사 메타데이터에는 실제 선택된 provider 버전이 남는다. 실패한 업로드는 문서가 생기지
  않으므로 422 응답으로 끝나며, 성공처럼 fallback하지 않는다.

## 검증

- `python -m pytest tests/test_llm_contract.py -q` → 5 passed
- 전체 회귀·두 레이아웃 평가·생성기 무결성은 이 Phase 종료 전에 다시 실행한다.

## 명시적 비범위 / 다음 Gate

- 이것은 실제 LLM이 아니며 추출 품질·정확도·외부 모델 사용을 주장하지 않는다.
- 실제 LLM 연결은 모델 제공자, 데이터 전송/보존, 키 관리, 실패 fallback 책임, 독립 평가셋을
  사용자가 확정한 뒤의 후속 Gate에서만 진행한다.
