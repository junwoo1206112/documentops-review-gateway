# HANDOFF — DocumentOps Review Gateway

- 작성일: 2026-11-26
- 대상: 다음 인수자(사람)와 다음 LLM 세션
- 현재 브랜치 상태: `main`, 작업 트리 클린, Phase 0~5 완료
- 최신 커밋: `feat(phase5): docker/compose, ci workflow, packaging checks and final readme`
  (이 문서는 `docs(handoff)` 커밋이다. 커밋 해시는 이동하므로 `git log --oneline`으로 확인한다)

이 문서 하나로 **무엇을 만들었고, 무엇이 검증됐고, 무엇이 남았고, 어떻게 이어서 하는지**를
알 수 있게 하는 것이 목적이다. README는 외부 독자용, 이 문서는 인수자용이다.

---

## 0. 30초 요약

| 항목 | 내용 |
|---|---|
| 제품 | 합성 한국어 거래 문서를 추출→근거→규칙→사람 승인→감사→평가로 처리하는 검토 게이트 |
| 핵심 주장 | "AI가 답한다"가 아니라 **근거 없는 값은 승인 불가, blocking 오류는 HOLD, 판정은 사람만** |
| 스택 | Python 3.12, FastAPI, SQLite, Jinja2 서버 렌더링, pytest, Docker, GitHub Actions |
| 실행 | `uvicorn app.asgi:app` (주의: `app.main:app` 아님) |
| 테스트 | **132 passed** (2026-11-26, Python 3.12.10, Windows 11) |
| 평가 | 36건 기준 문서 EM 36/36, HOLD 재현 19/19, 오보류 0/17, 규칙 일치 36/36, 근거 410/412 |
| Docker | `docker compose up --build` → `healthy`, 데모 4건 처리, 컨테이너 내 평가 동일 |
| 원격 CI | 워크플로 파일만 존재. **GitHub에서 실행된 적 없음 → 배지 없음** |
| 남은 일 | R-001(원격 CI·배지), R-002(데모 영상), 이후 결정 대기 항목 → 6절 |

3개 명령으로 상태를 확인할 수 있다.

```bash
python -m pytest -q
python tools/generate_dataset.py --check
python -m app.evaluate --dataset fixtures/evaluation
```

---

## 1. 절대 바뀌면 안 되는 계약 (invariants)

아래 5가지는 이 프로젝트의 정체성이다. 바꾸려면 ADR + 사용자 결정이 먼저다.

1. **자동 승인 없음.** `APPROVED`는 `POST /decision`에서 사람 별칭+사유가 있을 때만 된다.
2. **`HOLD → APPROVED` 직접 전이 금지.** `app/domain/statuses.py`의 `TRANSITIONS`와
   `FORBIDDEN_TRANSITIONS`가 단일 출처다.
3. **blocking 이슈 1건 이상이면 `HOLD`.** `severity`는 `blocking`만 판정에 센다.
4. **모든 추출 값은 원문 span을 가진다.** `verified`가 아니면 `MISSING_EVIDENCE`(blocking).
   파생값은 `derived`, 위치 없음은 `missing`.
5. **감사는 append-only.** 애플리케이션에 UPDATE/DELETE 경로가 없고, SQLite 트리거가 막는다.
   (`app/db.py`의 `audit_events_no_update`, `audit_events_no_delete`)

추가로 지켜야 하는 것:

- 실제 개인정보·실제 고객 문서를 넣지 않는다. 데이터는 `tools/generate_dataset.py`만 만든다.
- 기본 경로는 외부 LLM API 키 없이, 네트워크 없이 재현되어야 한다.
- OCR은 MVP 범위가 아니다(`docs/adr/0001-text-first.md`, `P-001`).
- `fixtures/evaluation`은 테스트·평가 중 수정하지 않는다.

---

## 2. 완료된 범위와 증거

| Phase | 한 일 | 커밋 제목 | 증거 |
|---|---|---|---|
| 0 | 상태·필드·규칙·평가 계약, 단일 출처 모듈, 문서↔코드 드리프트 테스트 | `feat(phase0): …` | `tests/test_contracts.py` 14개 |
| 1 | 합성 36건 + 정답 36 + manifest SHA-256 + 재생성 검사 + PII 패턴 검사 | `feat(phase1): …` | `python tools/generate_dataset.py --check` → 78 files 일치 |
| 2 | 결정론적 파서, span 검증, 8개 규칙, `app.inspect` CLI | `feat(phase2): …` | 평가셋 36건 규칙·상태 100% 일치 |
| 3 | SQLite 스키마, ReviewService, API 8개, JS 없는 검토 UI, 감사 트리거 | `feat(phase3): …` | 승인 422/409, 감사 변조 차단, 브라우저 확인 |
| 4 | 평가 엔진·리포트·CLI·실패 사례 3건·회귀 게이트 | `feat(phase4): …` | `artifacts/evaluation_report.json`, `tests/test_evaluation.py` 9개 |
| 5 | Dockerfile/Compose, CI 워크플로, 패키징 검사, 최종 README·스크린샷 | `feat(phase5): …` | 이미지 207MB, healthy, 컨테이너 평가 동일 |

### 기준선 수치 (재현 가능)

`dataset_version=synth-2026-11-26.2`, `ruleset=rules-1.0.0`, `extractor=deterministic-1.0.0`

| 지표 | matched / total | 값 |
|---|---|---|
| 문서 완전 일치 | 36 / 36 | 1.000 |
| HOLD 재현율 | 19 / 19 | 1.000 |
| 오보류율 | 0 / 17 | 0.000 |
| 규칙 일치 | 36 / 36 | 1.000 |
| 근거 유효율 | 410 / 412 | 0.995 |
| 규칙 회귀 | 0건 | — |

- 필드 EM은 10개 필드 모두 1.000 (품목 셀 51/51 포함).
- 410/412의 부족 2건은 **의도된 파생 총액**(값은 맞지만 span 없음 → HOLD)이다. 버그가 아니다.
- p50/p95는 환경 의존이므로 성과 수치로 쓰지 않는다. 리포트의 `measurement`에만 둔다.
- 수치를 바꾸려면 데이터셋/규칙/파서 버전을 올리고 `tests/test_evaluation.py`의 기대값,
  README 표, 이 문서를 함께 갱신한다.

### Docker 검증 기록 (2026-11-26)

| 항목 | 결과 |
|---|---|
| `docker build` | 성공, 207MB, 종료 코드 0 |
| 실행 사용자 | `appuser` uid 10001 (비루트) |
| 헬스체크 | `/api/health` → `healthy` |
| `docker compose up -d --build` | `gateway Up (healthy)` |
| `scripts/seed_demo.py` → 8000 | 2건 `PENDING_REVIEW`, 2건 `HOLD`(`LINE_TOTAL_MISMATCH`, `DUPLICATE_DOCUMENT`) |
| `docker compose exec -T gateway python -m app.evaluate …` | 위 기준선과 동일 |
| 데이터 | named volume `documentops-data`에 유지 |

---

## 3. 실행·검증 런북

### 3.1 클린 환경에서 처음 실행

```bash
git clone <repo-url> documentops-review-gateway
cd documentops-review-gateway
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev]"
python -m pytest -q
```

기대 결과: `132 passed`.

> `uv`와 Node.js는 필요 없다. UI는 Jinja2 서버 렌더링이다(ADR 0002).
> Python은 3.12 이상이어야 한다.

### 3.2 계약·데이터·평가 검증

```bash
python tools/generate_dataset.py --check
# 기대: "데이터셋 일치: dataset_version=synth-2026-11-26.2 … evaluation_docs=36 demo_docs=4"

python -m app.evaluate --dataset fixtures/evaluation
# 기대: document_em=1.0, hold_recall=1.0 (19/19), false_hold_rate=0.0 (0/17),
#       rule_match=1.0, evidence_validity=0.995, exit code 0
```

### 3.3 화면·API 데모

```bash
uvicorn app.asgi:app --reload          # http://127.0.0.1:8000
python scripts/seed_demo.py            # 별도 터미널, 데모 4건 순서 접수
```

확인할 것:

1. 목록에 4건, 검토 대기 2 / 보류 2.
2. `DEMO-0002` 상세: `LINE_TOTAL_MISMATCH`, 원문 노란 하이라이트, 승인 버튼 비활성.
3. `DEMO-0004` 상세: `DUPLICATE_DOCUMENT`, `duplicate_of` 표시.
4. `DEMO-0001`에서 별칭+사유 승인 → `APPROVED`, 감사 이벤트 3건.
5. 사유 없이 승인 → 422, `HOLD` 직접 승인 → 409.

### 3.4 Docker

전제: Docker Desktop 또는 Docker Engine이 실행 중이어야 한다. (Windows에서 Docker Desktop이
꺼져 있으면 `docker build`가 `npipe:////./pipe/dockerDesktopLinuxEngine` 오류로 실패한다.)

```bash
docker compose up -d --build
docker compose ps                          # healthy 확인
python scripts/seed_demo.py
docker compose exec -T gateway python -m app.evaluate --dataset fixtures/evaluation
docker compose down                        # 볼륨 유지. 초기화는 down -v
```

---

## 4. 코드 지도

```text
app/
├─ config.py                 Settings(환경 변수), 기본 경로
├─ version.py                APP/EXTRACTOR/RULESET/DATASET/VENDOR 버전
├─ errors.py                 AppError → {"error":{code,message,details}}
├─ db.py                     SQLite 스키마, 감사 append-only 트리거, 기존 문서 조회
├─ main.py                   create_app(): 미들웨어(보안 헤더·본문 크기·rate limit), 핸들러
├─ asgi.py                   uvicorn 진입점 (app = create_app())
├─ inspect.py                DB 없이 문서 1건 검사 CLI
├─ evaluate.py               고정 데이터셋 평가 + 리포트 + CLI
├─ domain/
│  ├─ statuses.py            상태·전이·금지 전이·라벨 (단일 출처)
│  ├─ fields.py              필드 키·필수 여부·라벨·비교 순서
│  ├─ rules.py               규칙 8개 카탈로그(심각도·메시지 템플릿)
│  └─ models.py              ExistingDocument (중복 판정 입력)
├─ services/
│  ├─ ingestion.py           확장자(.txt)·크기·UTF-8·NUL 검사, SHA-256
│  ├─ textnorm.py            돈/날짜/거래처/문서번호 정규화, 부가세 half-up
│  ├─ extraction/base.py     ExtractedField/Item/ExtractionResult/Provider 계약
│  ├─ extraction/deterministic.py  고정 레이아웃 파서, span 계산, 파생 총액
│  ├─ evidence.py            span 재검증(verified/derived/missing)
│  ├─ validation.py          연쇄 억제 포함 규칙 엔진, 중복 판정
│  ├─ pipeline.py            parse → evidence → validate → status, elapsed_ms
│  ├─ vendors.py             거래처 JSON 로더
│  └─ review.py              ingest/revalidate/decide/list/get/audit + 감사 기록
├─ api/
│  ├─ routes.py              /api/* 8개
│  ├─ schemas.py             DecisionRequest (별칭·사유 필수, 공백 금지)
│  └─ pages.py               HTML 6경로, 원문 하이라이트(escape 후 mark)
├─ templates/                base/index/detail/evaluation.html
├─ static/style.css          다크 테마, 상태 배지, 반응형
tests/                       12개 파일, 130 tests
tools/generate_dataset.py    합성 데이터·정답·manifest·vendors 생성기 (--check)
scripts/seed_demo.py         데모 4건 HTTP 업로드
fixtures/                    vendors.json, demo 4건, evaluation 36건+정답+manifest
docs/                        schema/rules/evaluation/security/adr/decisions/reviews/reference
```

핵심 호출 흐름:

```text
POST /api/documents
  → ReviewService.ingest → ingest_bytes → process_document
      → parse_document → apply_evidence → validate → status_for_issues
  → SQLite 저장 + 감사 2건(INGESTED, VALIDATION_COMPLETED)
POST /api/documents/{id}/decision
  → 상태 전이 검사 → 조건부 UPDATE(rowcount) → 판정 저장 → 감사 1건
POST /api/documents/{id}/revalidate
  → 기존 open 이슈 resolved → 재검증 → 상태 전이(허용 시) → 감사 1건
```

---

## 5. 계약을 바꾸는 절차 (중요)

이 프로젝트는 **문서가 계약**이다. 코드만 고치면 테스트가 막는다.

1. 단일 출처 모듈을 먼저 고친다: `statuses.py`, `fields.py`, `rules.py`, `version.py` 중 해당.
2. 같은 표를 문서에 반영한다: `docs/schema.md`, `docs/rules.md`, `docs/evaluation.md`.
3. `python -m pytest tests/test_contracts.py`를 돌려 드리프트가 없는지 확인한다.
4. 버전을 올린다.
   - 파서 동작 변경 → `EXTRACTOR_VERSION`
   - 규칙·판정 변경 → `RULESET_VERSION`
   - 데이터셋 파일 변경 → `DATASET_VERSION`
5. 데이터셋 변경은 **손으로 파일을 고치지 않는다.** `tools/generate_dataset.py`를 고치고
   `python tools/generate_dataset.py`로 전체 재생성 후, `--check`와 테스트를 통과시킨다.
6. 기대 수치가 바뀌면 README 표, `HANDOFF.md` 2절, `tests/test_evaluation.py`를 함께 고친다.
7. 새 페이즈/의미 있는 변경은 `docs/reviews/phase-N.md`에 A·B·C 검토를 남긴다.

버전별 영향:

| 변경 | 함께 바뀌는 것 |
|---|---|
| 규칙 추가/수정 | `docs/rules.md`, 정답 데이터의 `expected_rule_ids`, 평가 기준선, README |
| 필드 추가 | `docs/schema.md`, 정답 JSON, EM 분모, API 응답, UI 표 |
| 레이아웃 변경 | 파서, 생성기, span 정답, 모든 fixture 해시 |
| 상태/전이 변경 | `statuses.py`, `docs/schema.md` 전이표, `test_contracts`, 리뷰 UI 버튼 |

---

## 6. 남은 작업 백로그

우선순위는 P0(바로), P1(다음), P2(결정 후)다. 각 항목은 **수용 기준**을 만족할 때만 완료다.

### R-001 — GitHub 원격 CI 실행 확인 + 배지 (P0)

- 왜: `.github/workflows/ci.yml`은 있지만 GitHub에서 실행된 적이 없다. 검증 전 배지는 금지.
- 할 일:
  1. 원격 저장소 생성·push (`main`).
  2. Actions에서 `ci` 실행 결과 확인. 실패 시 로그 기반 수정.
  3. 성공한 뒤에만 README 상단에 배지를 추가한다. 배지는 실제 워크플로 이름 `ci`와
     기본 브랜치를 가리켜야 한다.
- 수용 기준: Actions 성공 1회 이상, 배지 클릭 시 해당 실행으로 이동, README 문구와 실제 일치.
- 주의: `render.yaml`·공개 URL은 만들지 않았다. 배포 주장도 하지 않는다.

### R-002 — 45~60초 데모 영상 (P0)

- 왜: 포트폴리오에서 가장 중요한 증거. README의 60초 시나리오가 그대로 스토리보드다.
- 장면: ① 정상 업로드(근거 표시) ② 금액 불일치 HOLD ③ 중복 HOLD ④ 사유 있는 승인
  ⑤ 사유 없음 422 / HOLD 승인 409 ⑥ 감사 이력.
- 수용 기준: 공개 URL(Release asset/YouTube 일부공개), 첫 자막 `합성 데이터·mock`,
  한 번의 연속 녹화, README에 링크+촬영 날짜.
- 주의: `docs/reference/PORTFOLIO_DEMO_AND_SITE_COPY.md`는 **다른 두 프로젝트** 원고다.
  이 프로젝트 원고를 새로 쓰거나 그 문서에 섹션을 추가해야 한다.

### R-003 — 보류 해소용 필드 단위 사람 수정 (P2, 결정 필요: P-003)

- 왜: `MISSING_REQUIRED` HOLD는 현재 "원문 수정 후 새 업로드"만 가능하다.
- 결정할 것: 사람이 고친 값의 근거 모델(원문 재인용? 수정 사유만?), 감사 이벤트 형식,
  승인 가능 여부. "근거 없는 값은 승인 불가" 원칙과 충돌하지 않아야 한다.
- 수용 기준: `docs/decisions/pending.md`의 P-003이 닫히고, API/D B/UI/테스트/감사가 함께 갱신됨.

### R-004 — OCR 확장 (P2, 결정 필요: P-001)

- 왜: 이미지 문서는 현재 415/422로 끝난다.
- 조건: `source_kind=scan` 전용 데이터셋(별도 36건), 별도 지표표, 낮은 신뢰도·span 미확보 시
  자동 HOLD, 텍스트 평가와 혼합 금지.
- 수용 기준: 텍스트 기준선이 변하지 않고, OCR 표가 분리 보고되며, CI에 외부 바이너리 의존을
  넣지 않거나 전용 job으로 격리.

### R-005 — LLM 추출 어댑터 (P2, 결정 필요: P-002)

- 왜: `ExtractionProvider` 인터페이스는 준비됐지만 구현은 없다.
- 조건: 오프라인 스텁으로 계약 테스트, LLM 결과도 `apply_evidence`를 통과, 기본 경로 아님,
  키 없이 전체 테스트 통과.
- 수용 기준: 어댑터 추가 후에도 `pytest`가 네트워크 없이 통과하고 기본 extractor 버전 불변.

### R-006 — 두 번째 문서 레이아웃 (P2)

- 왜: 현재 레이아웃 1종. 실제 문서 변형에 취약하다(의도된 422).
- 조건: 레이아웃별 파서 선택 규칙, 422와 HOLD 경계 유지, 데이터셋 버전 갱신.
- 수용 기준: 두 레이아웃 모두에서 기준선 유지 또는 명시적 하락과 사유 기록.

### R-007 — 접근성·반응형 세부 점검 (P2)

- 왜: 600px·데스크톱 두 폭만 확인했다. 키보드 포커스·대비·태블릿 폭 자동 검증이 없다.
- 수용 기준: 키보드만으로 업로드→판정 가능, 대비 점검 기록, 최소 3개 폭 스크린샷.

### 명시적 비목표 (요구가 생기기 전에는 시작하지 않는다)

- 로그인·권한·멀티테넌시(P-006), Postgres(P-004), 부가세율 가변(P-005),
  실제 메일·결제·ERP 실행, 자동 승인, 실제 고객 데이터.

---

## 7. 알려진 함정

| 함정 | 증상 | 해결 |
|---|---|---|
| `uvicorn app.main:app` | `AttributeError: module 'app.main' has no attribute 'app'` | `uvicorn app.asgi:app` 사용 |
| Windows 콘솔 한글 깨짐 | 테스트 로그·CLI 출력이 `?`로 보임 | `$env:PYTHONIOENCODING='utf-8'` (PowerShell) |
| CRLF 변환 | fixture SHA-256 불일치 | `.gitattributes`의 `* text=auto eol=lf` 유지. autocrlf로 우회하지 않는다 |
| fixture 직접 수정 | `manifest` 해시/정답 불일치, `--check` 실패 | 생성기를 고치고 전체 재생성 |
| 이전 데모 DB | 업로드가 예상과 다르게 `DUPLICATE_DOCUMENT` | `data/documentops.db` 삭제 또는 `docker compose down -v` |
| Docker Desktop 꺼짐 | `npipe://…dockerDesktopLinuxEngine` 오류 | Docker Desktop 시작 후 재시도 |
| 8000 포트 점유 | compose 기동 실패 | 기존 프로세스 종료 또는 compose 포트 변경 |
| rate limit | 반복 데모에서 429 | `RATE_LIMIT_PER_MINUTE=0`으로 재기동 |
| 평가 수치 비교 | p50/p95가 실행마다 다름 | 시간은 비교하지 않는다. `metrics`/`failures`만 결정론 |
| `app.evaluate` 종료 코드 | 1이면 회귀, 2면 데이터셋 없음 | 리포트의 `regressions` 확인 |

---

## 8. 다음 LLM 세션 재개 체크리스트

1. 이 파일과 `README.md`, `docs/schema.md`, `docs/rules.md`, `docs/evaluation.md`를 읽는다.
2. 3절의 검증 블록을 그대로 실행한다. **하나라도 실패하면 기능 추가를 시작하지 않는다.**
3. `git status`가 깨끗한지 확인한다. 사용자 변경이 있으면 덮어쓰지 않는다.
4. `docs/decisions/pending.md`를 읽고, 요청이 보류 결정을 건드리는지 확인한다.
5. R-001 → R-002 순서로 진행한다. P2 항목은 사용자 결정 없이 시작하지 않는다.
6. 계약을 바꾸면 5절 절차를 지키고, `docs/reviews/phase-N.md`에 A·B·C 검토를 남긴다.
7. 완료 시 `HANDOFF.md` 6절 상태, README 상태/수치, 이 문서의 "최신 커밋" 설명을 갱신한다.
8. 커밋 단위는 페이즈/의미 단위로 유지한다: `feat(phaseN): …`, `docs(handoff): …`.

### 인수 완료 판정 (Definition of Done)

- [ ] 클린 클론에서 `pip install -e ".[dev]"` + `pytest` 통과
- [ ] `tools/generate_dataset.py --check` 통과
- [ ] `app.evaluate` exit 0, 기준선 수치 재현
- [ ] `uvicorn app.asgi:app` + `scripts/seed_demo.py`로 5장면 재현
- [ ] `docker compose up --build` 후 healthy
- [ ] `docs/reviews/phase-0..5.md` 존재
- [ ] 실제 개인정보·실제 문서가 저장소에 없음
- [ ] README의 주장이 테스트/실행 증거보다 강하지 않음

---

## 9. 변경 이력 (요약)

| 커밋 | 내용 |
|---|---|
| `feat(phase0)` | 계약 문서·단일 출처·드리프트 테스트 |
| `feat(phase1)` | 합성 36건·정답·manifest·무결성 테스트 |
| `feat(phase2)` | 파서·근거·8규칙·inspect CLI |
| `feat(phase3)` | SQLite·감사 트리거·API·검토 UI |
| `feat(phase4)` | 평가 엔진·리포트·사례 3건·회귀 게이트 |
| `feat(phase5)` | Docker·CI·패키징·README·스크린샷 |
| `docs(handoff)` | 이 문서와 `handoff.seed.yaml` |

각 페이즈의 발견·수정 이유는 `docs/reviews/phase-0.md` ~ `phase-5.md`에 있다.

