# Phase 17-I 전문가 A·B·C 교차 검증 — 평가·CI 증거 격리

대상: 두 번째 레이아웃 평가, CI artifact, Docker 이미지, 공개 데모 시드, 인수 문서
기준: "레이아웃별 독립 평가"가 파일·API·CI·화면에서 실제로 분리되어야 한다.

## 판정 요약

| 관점 | 판정 | 근거 |
|---|---|---|
| A. 제품·인수 | 개선 반영 | `/evaluation`이 마지막에 실행한 리포트 하나만 보여 주던 문제를 고쳤다. 이제 데이터셋 이름과 파일명을 붙여 두 레이아웃을 함께 보여 준다. 공개 데모 503도 문서에 사실대로 남겼다. |
| B. 정확성 | 개선 반영 | 두 데이터셋이 같은 `dataset_version`과 같은 기본 리포트 경로를 써서 결과가 서로를 덮어썼다. 리포트에 `dataset_name`을 추가하고 기본 경로를 데이터셋별로 분리했다. |
| C. QA·검증 | 개선 반영 | CI가 layout1만 평가하고 artifact도 하나만 올렸다. 두 레이아웃 평가·artifact·Docker 베이크를 추가하고, 회귀 테스트로 고정했다. |

## 실제로 잡힌 결함

| ID | 문제 | 영향 | 조치 | 회귀 방지 |
|---|---|---|---|---|
| P17I-1 | `python -m app.evaluate --dataset fixtures/evaluation_layout2`가 `artifacts/evaluation_report.json`을 덮어썼다. | layout1 결과가 사라지고, 리포트만으로 어느 형식인지 알 수 없다. "독립 평가" 주장이 성립하지 않는다. | 리포트에 `dataset_name` 추가, 기본 출력 경로를 데이터셋별로 분리(`evaluation_report_evaluation_layout2.json`), `/evaluation`이 모든 리포트를 렌더링. | `test_layout_reports_are_distinguishable`, `test_api_lists_reports_per_layout`, `test_cli_uses_layout_specific_default_report` |
| P17I-2 | CI는 `fixtures/evaluation`만 평가하고 artifact 이름도 하나였다. | layout2는 pytest에만 의존해 **평가 증거·artifact가 CI에 남지 않는다**. | 두 레이아웃 평가 단계와 `artifacts/evaluation_report*.json` 업로드로 변경. | `test_ci_runs_tests_dataset_and_evaluation_without_secrets` |
| P17I-3 | Docker 이미지에 `artifacts/`가 없어 공개 데모 `/evaluation`이 빈 화면이 된다. | 공개 포트폴리오에서 "공개 평가" 약속이 깨진다. | 이미지 빌드 시 두 레이아웃 리포트를 생성해 포함. | `test_dockerfile_is_non_root_and_healthchecked` |
| P17I-4 | 공개 시드가 "문서가 1건이라도 있으면" 전체를 건너뛰었다. | 시드 중단 시 2/4건만 있는 상태로 고정되고 재기동해도 복구되지 않는다. | 파일명 기준으로 누락분만 순서대로 시드. | `test_public_demo_seed_recovers_partial_database` |
| P17I-5 | HANDOFF/seed가 Render 데모를 "live"로 표기했지만 2026-11-27 `/api/health`가 503이었다. | 인수자가 실제 상태를 오해한다. | "2026-11-26 마지막 확인, 2026-11-27 503, 재배포 후 재검증"으로 하향. | `test_handoff_seed_is_valid_and_tracks_state` |
| P17I-6 | 구형 리포트에는 `dataset_name`이 없고 layout2 파일명이 여러 형태였다. | 화면의 레이아웃 표시와 CI/Docker/런북 경로가 엇갈릴 수 있다. | 구형 두 파일명을 호환 매핑하고, layout2의 정식 경로를 `evaluation_report_evaluation_layout2.json`으로 통일했다. | `test_legacy_report_filenames_keep_layout_identity` |

## A. 제품·인수

| # | 발견 | 조치 |
|---|---|---|
| A-1 | 평가 화면에 데이터셋 이름이 없어 공백 표/파이프 표를 구분할 수 없다. | `dataset_name`과 `report_file`을 화면 상단에 표시. |
| A-2 | "최신" 리포트라는 표현이 어느 데이터셋인지 오해를 만든다. | `/api/evaluation/latest`는 기본 데이터셋(`evaluation`) 우선임을 문서화하고, 전체 목록 API를 추가. |
| A-3 | 공개 데모 상태가 실제와 다르면 포트폴리오 신뢰가 깎인다. | 503 관측을 HANDOFF·seed·리뷰에 기록하고, 재배포 후 확인 항목을 명시. |

## B. 정확성

| # | 발견 | 조치 |
|---|---|---|
| B-1 | 리포트 식별자가 `dataset_version`뿐인데 두 데이터셋이 같은 버전을 쓴다. | `dataset_name`을 1차 식별자로 추가. `dataset_version`은 생성기/파일 계약으로 유지. |
| B-2 | 기본 경로가 하나면 사용자가 두 번째를 실행할 때 첫 결과를 잃는다. | 데이터셋별 기본 경로 + 명시 `--report` 지원. CI/Docker는 항상 명시 경로. |
| B-3 | 리포트 목록이 깨진 JSON 하나로 500이 될 수 있다. | `load_reports`가 손상 파일을 건너뛰고 나머지를 보여 준다. |

## C. QA·검증

| # | 발견 | 조치 |
|---|---|---|
| C-1 | layout2 평가가 CI artifact로 남지 않는다. | 두 레이아웃 평가 + wildcard artifact 업로드. |
| C-2 | Docker와 로컬 평가 경로가 다르면 공개 화면이 비어도 테스트가 통과한다. | Dockerfile에서 두 리포트를 생성하고, 패키징 테스트가 문자열을 검사. |
| C-3 | 부분 시드 복구가 테스트되지 않았다. | 2건만 있는 DB에서 공개 앱을 기동해 4건으로 복구되는지 검증. |
| C-4 | 새 API/리포트 목록이 문서에 없다. | `docs/schema.md`, `docs/evaluation.md`, README, HANDOFF, ROADMAP에 반영. |
| C-5 | Compose artifact bind mount가 이미지의 baked report를 가린다. | 로컬 `/evaluation`이 평가 전에는 비어 보일 수 있다. | README/HANDOFF에 두 평가 명령을 먼저 실행해야 함을 명시했다. |

## 실행 증거

| 명령/검사 | 결과 |
|---|---|
| `python -m pytest -q` | **174 passed** |
| `python tools/generate_dataset.py --check` | 151 files, 두 레이아웃 각 36건 |
| layout1 평가 | 문서 EM 36/36, HOLD 19/19, 오보류 0/17, 규칙 36/36, 근거 410/412 |
| layout2 평가 | 위와 동일, `dataset_name=evaluation_layout2` |
| `/evaluation` | 두 리포트와 파일명을 함께 렌더 |
| `docker build` | 성공, 208MB, `healthy`, 이미지 내 `/api/evaluation/reports` 2건 |
| 공개 URL | 2026-11-27 `/api/health` 503 — **재배포 후 재확인 필요** |

## 남은 위험

- CI의 두 레이아웃 job은 다음 push에서 실제 실행을 확인해야 한다.
- Render 무료 인스턴스는 슬립/중단될 수 있다. "live" 주장은 재확인 전까지 하지 않는다.
- 두 데이터셋의 `dataset_version`이 같다. 식별은 `dataset_name`으로 하며, 파일 내용 계약을
  바꾸면 `DATASET_VERSION`을 올리는 기존 규칙을 따른다.
- 리포트가 여러 개일 때 `/api/evaluation/latest`는 기본 데이터셋만 반환한다. 클라이언트가
  특정 레이아웃을 원하면 `/api/evaluation/reports`를 써야 한다.
