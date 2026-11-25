# Phase 5 전문가 A·B·C 교차 검증

대상: Dockerfile, docker-compose, GitHub Actions, 패키징(pyproject/wheel), README, 반응형 화면
기준: `docker compose up --build` 뒤 예제 문서를 처리할 수 있고, CI가 린트·데이터·테스트·평가를 실행

## 판정 요약

| 관점 | 판정 | 근거 |
|---|---|---|
| A. 채용·실무 | 통과 | 첫 화면에서 가치·60초 시나리오·실측 지표·한계·실행법을 순서대로 읽을 수 있다. 스크린샷은 실제 실행 화면이다. |
| B. AI/ML 시스템 | 통과 | 컨테이너 안에서 같은 평가 명령이 같은 지표(36/36, 19/19, 410/412)를 낸다. |
| C. QA·신뢰성 | 개선 필요 → 반영 | Docker 빌드가 대화형 `adduser` 프롬프트를 타고 경고를 냈고, 좁은 화면에서 표가 깨졌다. |

## 실제로 고친 결함

| # | 결함 | 영향 | 조치 |
|---|---|---|---|
| D-1 | `docker build`의 `adduser`가 `--gecos` 없이 실행돼 대화형 프롬프트·경고를 냈다. | CI/로컬 빌드 로그가 오염되고, 자동화에서 비정상 종료로 보일 수 있다. | `--gecos ""` 추가. 재빌드 종료 코드 0 확인. |
| D-2 | `pip install .` 시 `app.templates`·`app.static`이 패키지 목록에 없어 setuptools 경고가 났다. | 휠에 파일은 들어가지만, 경고를 방치하면 이후 패키지 데이터가 조용히 빠질 수 있다. | `packages`에 두 디렉터리를 명시하고, 휠 내용 검사로 템플릿·CSS 포함을 확인. |
| D-3 | 좁은 Review 패널(600px)에서 문서 표가 두 줄로 깨져 읽기 어려웠다. | 60초 데모를 작은 창에서 하면 첫인상이 나빠진다. | 표 최소 폭 + 가로 스크롤, 760px 이하에서 `blocking` 열 숨김. 스크린샷 재확인. |
| D-4 | 상세 화면의 "규칙 재검증" 버튼이 좁은 폭에서 두 줄로 접혔다. | 버튼 라벨이 깨져 보인다. | `.doc-head form { flex: 0 0 auto }` + 버튼 nowrap. |
| D-5 | CI 배지를 README에 넣고 싶지만, 이 저장소는 아직 원격에서 워크플로를 실행한 적이 없다. | 검증되지 않은 배지는 포트폴리오 신뢰를 떨어뜨린다. | 배지를 넣지 않았다. README에는 로컬 동등 검증 명령과 "원격 실행은 push 후 확인"을 명시. |

## C. QA·신뢰성 검증 기록

| 항목 | 방법 | 결과 |
|---|---|---|
| 이미지 빌드 | `docker build -t documentops-review-gateway:test .` | 성공, 이미지 207MB |
| 비루트 실행 | Dockerfile `USER appuser` | 컨테이너 내 프로세스 uid 10001 |
| 헬스체크 | `/api/health` | `healthy` |
| Compose 기동 | `docker compose up -d --build` | `gateway Up (healthy)` |
| 데모 4건 | `scripts/seed_demo.py` → 8000 | 2건 `PENDING_REVIEW`, 2건 `HOLD`(`LINE_TOTAL_MISMATCH`, `DUPLICATE_DOCUMENT`) |
| 컨테이너 평가 | `docker compose exec -T gateway python -m app.evaluate …` | `document_em=1.0`, `hold_recall=1.0`, `false_hold_rate=0.0`, `rule_match=1.0`, `evidence_validity=0.995` |
| 데이터 지속성 | named volume `documentops-data` | 재기동 후 문서 유지 |

## B. AI/ML 시스템

| # | 발견 | 조치 |
|---|---|---|
| B-1 | 컨테이너 안에서 평가가 안 돌면 "Docker에서 재현 가능"이 거짓이 된다. | 이미지에 `fixtures/`, `scripts/`, `app/`를 포함하고 실제로 평가 명령을 실행해 확인했다. |
| B-2 | p50/p95는 호스트·컨테이너에서 다르다. | 수치를 README 주장으로 쓰지 않고, 리포트의 `measurement`에만 남긴다. |
| B-3 | 운영 DB가 이미지에 구워지면 데모가 오염된다. | `/app/data`는 named volume, `.dockerignore`는 로컬 DB·아티팩트를 제외. |
| B-4 | OCR을 넣지 않은 이유를 배포 문서에서 다시 설명해야 한다. | README·ADR 0001·pending(P-001)에 동일한 결정을 유지. |

## A. 채용·실무

| # | 발견 | 조치 |
|---|---|---|
| A-1 | 지표가 좋아도 "무엇을 클릭하면 보이는가"가 없으면 데모가 어렵다. | README 첫 화면에 60초 시나리오 5단계와 실행 명령을 유지하고, 스크린샷 3장을 추가. |
| A-2 | "Docker 지원"과 "Docker에서 확인함"은 다르다. | 확인한 사실만 적고, 실행 날짜와 결과(healthy, 4건 처리)를 함께 적었다. |
| A-3 | CI 배지가 없으면 미완성처럼 보일 수 있다. | 대신 로컬에서 CI와 같은 6단계를 통과했다는 명령 목록을 README에 둔다. 원격 실행 후 배지를 추가하는 절차를 남긴다. |

## 남은 위험

- GitHub Actions 워크플로는 파일로만 존재하며, 원격 저장소에서 실행된 적이 없다.
  첫 push 후 `ci` 실행 결과를 확인하고, 성공했을 때만 배지를 붙인다.
- Docker Desktop이 꺼져 있으면 `docker build`가 실패한다. README에 전제 조건을 적었다.
- 이미지 크기 207MB는 python:3.12-slim + FastAPI 기준이다. 추가 최적화는 범위 밖이다.
- 반응형 검증은 600px·데스크톱 두 폭만 확인했다. 태블릿 중간 폭은 자동 검증이 없다.
