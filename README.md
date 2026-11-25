# DocumentOps Review Gateway

> 합성 한국어 업무 문서를 **원문 근거 → 규칙 검증 → 사람 승인 → 감사 이력 → 공개 평가** 흐름으로
> 안전하게 처리하는 포트폴리오 프로젝트입니다.

이 프로젝트가 증명하려는 역량은 "AI가 답을 낸다"가 아니라,
**AI 산출물을 실제 업무에 투입하기 전에 검증·보류·승인·추적하는 방법**입니다.

## 핵심 계약 (바뀌지 않는 3가지)

1. **근거 없는 값은 승인될 수 없다.** 모든 추출 필드는 `page / char_start / char_end / evidence_excerpt`를 가진다.
2. **blocking 검증 오류가 1건이라도 있으면 `HOLD`다.** 자동 승인 경로는 존재하지 않는다.
3. **승인·반려는 사람만, 사유와 검토자 별칭을 필수로 남긴다.** 모든 상태 변경은 append-only 감사 이력에 기록된다.

## 60초 데모 시나리오 (Phase 3에서 화면으로 확인)

1. 정상 문서 업로드 → 필드 6개와 각 원문 span이 나란히 보인다. 상태 `PENDING_REVIEW`.
2. 금액이 어긋난 문서 업로드 → `LINE_TOTAL_MISMATCH` 1건, 상태 `HOLD`. 승인 버튼이 비활성.
3. 같은 문서 재업로드 → `DUPLICATE_DOCUMENT`로 `HOLD`.
4. 정상 문서에 별칭+사유를 입력해 승인 → `APPROVED` + 감사 이벤트 3건.
5. 사유 없이 승인 시도 → 422. `HOLD` 문서 직접 승인 시도 → 409.

용어: **HOLD(보류)** = blocking 검증 오류가 있어 사람이 먼저 확인해야 하는 상태.
`APPROVED`/`REJECTED`는 사람이 판정한 종료 상태다.

## 아키텍처

```text
합성 .txt 문서 업로드
  → Ingestion        파일 SHA-256, UTF-8 검증, 크기 제한
  → Extraction       결정론적 파서 (기본) / LLM 어댑터 (선택, 미구현)
  → Evidence Mapper  필드별 원문 span·발췌문 검증
  → Validation       7개 명시 규칙 → blocking issue
  → Review Queue     HOLD 또는 PENDING_REVIEW
  → 사람 판정         승인 / 반려 + 별칭 + 사유
  → Audit + Eval     append-only 이력, 고정 데이터셋 평가 리포트
```

## 데이터·범위 정책

- 실제 고객 문서, 주민번호·계좌·연락처 등 개인정보를 **사용하지 않는다.** 모든 문서·거래처·번호는 생성기가 만든 합성값이다.
- 외부 LLM API 키 없이, 네트워크 없이 전체 테스트와 평가가 재현되어야 한다.
- 외부 전송·결제·ERP 쓰기·자동 승인은 비목표다.
- OCR은 MVP 범위가 아니다. [ADR 0001](docs/adr/0001-text-first.md)과 [보류 결정](docs/decisions/pending.md)을 참고한다.

## 현재 상태

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | 계약 고정(상태·필드·규칙·평가 정의) | 완료 |
| 1 | 합성 문서 36건 + 정답 manifest + SHA-256 | 완료 |
| 2 | 추출·근거·규칙 검증 MVP | 완료 |
| 3 | 검토 UI/API + 감사 이력 | 예정 |
| 4 | 고정 평가 + 실패 사례 공개 | 예정 |
| 5 | Docker·CI·README 마감 (OCR 제외) | 예정 |

Phase 2 기준 확인된 사실: 평가셋 36건에서 8개 규칙 판정과 정답이 전부 일치하고,
`HOLD` 19건 / `PENDING_REVIEW` 17건이 재현된다. 아직 DB·화면은 없다.

## 실행

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -e ".[dev]"

pytest                            # 전체 테스트

# DB 없이 문서 1건의 추출·검증 결과 보기
python -m app.inspect fixtures/evaluation/DOC-0001.txt
```

Phase 3 이후 추가되는 명령:

```bash
uvicorn app.main:app --reload     # http://127.0.0.1:8000
python -m app.evaluate --dataset fixtures/evaluation
docker compose up --build
```

## 문서

| 문서 | 내용 |
|---|---|
| [docs/schema.md](docs/schema.md) | 입력 형식, 필드, 상태 전이, DB/API 계약 |
| [docs/rules.md](docs/rules.md) | 7개 검증 규칙, 심각도, 연쇄 억제 정책 |
| [docs/evaluation.md](docs/evaluation.md) | 데이터셋 분리, 지표 정의·분모, 리포트 스키마 |
| [docs/security.md](docs/security.md) | 데이터 정책, 위협 모델, 제한 |
| [docs/decisions/pending.md](docs/decisions/pending.md) | 의도적으로 보류한 결정 |
| [docs/reviews/](docs/reviews/) | Phase별 전문가 A·B·C 교차 검증 기록 |
| [docs/reference/](docs/reference/) | 인수인계 원본 계획·실행 로그·데모 원고 |

## 인수인계 원본

- [마스터 구현 계획](docs/reference/PORTFOLIO_IMPROVEMENT_MASTER_PLAN.md)
- [포트폴리오 실행 로그](docs/reference/PORTFOLIO_PHASE_LOG_20261125.md)
- [데모·사이트 원고](docs/reference/PORTFOLIO_DEMO_AND_SITE_COPY.md)
