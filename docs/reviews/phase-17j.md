# Phase 17-J 전문가 A·B·C 교차 검증 — 인수 문서·증거 정합성 자동 가드

대상: `HANDOFF.md`, `handoff.seed.yaml`, `NEXT_PHASES_HANDOFF.md`, `ROADMAP_PHASES.md`, README, CI·Docker 리포트 경로
기준: 문서가 말하는 테스트 수·리포트 파일명이 실제 실행과 같고, 다음 변경에서도 자동으로 검증된다.

## 판정 요약

| 관점 | 판정 | 근거 |
|---|---|---|
| A. 제품·인수 | 개선 반영 | 인수 문서마다 테스트 수가 174·175·178로 달랐다. 신규 인수자가 어느 수치를 믿어야 할지 알 수 없었다. |
| B. 정확성 | 개선 반영 | layout2 리포트 파일명이 문서·스크립트마다 짧은 이름/긴 이름으로 갈릴 위험이 있었다. 하나의 이름을 계약으로 고정했다. |
| C. QA·검증 | 개선 반영 | 문서 수치와 리포트 경로가 다시 어긋나지 않도록 pytest가 **전체 수집 수를 실제로 세어** 문서와 비교하고, 파일명 일관성을 검사한다. |

## 실제로 잡힌 결함

| ID | 문제 | 영향 | 조치 | 회귀 방지 |
|---|---|---|---|---|
| P17J-1 | `HANDOFF.md`의 실행 기대값이 175, 테스트 목록이 174, 0절은 178이었다. | 인수자가 "175/174/178 중 무엇이 기준인지" 판단할 수 없다. | 현재 기준선 180으로 통일. | `test_documented_test_counts_match_collected_suite` |
| P17J-2 | 문서 수치가 코드 변경 때마다 손으로 갱신되어 반복적으로 어긋났다. | 같은 드리프트가 다음 페이즈에서 재발한다. | `pytest --collect-only`로 실제 수집 수를 세어 seed·HANDOFF·README·ROADMAP·NEXT에 강제 비교. | 같은 테스트 |
| P17J-3 | layout2 리포트 경로가 `evaluation_report_layout2.json`과 `evaluation_report_evaluation_layout2.json`으로 혼용될 수 있었다. | CI/Docker가 만든 파일과 문서의 명령이 달라 `/evaluation`에서 누락될 수 있다. | 긴 이름 하나를 계약으로 고정하고 CI·Docker·seed·README·HANDOFF·NEXT·evaluation 문서에서 확인. | `test_layout2_report_filename_is_consistent` |
| P17J-4 | seed의 `last_verified`가 26일인데 status는 `deployed_verified`, 문서는 27일 검증을 기록했다. | 공개 데모 검증 시점이 서로 모순. | 27일로 통일. | `test_handoff_seed_is_valid_and_tracks_state` |
| P17J-5 | `NEXT_PHASES_HANDOFF.md`가 특정 과거 커밋(`c772bf6`)을 기준으로 적혀 있었다. | 이후 커밋과의 관계가 불명확. | "main (2026-11-27, Phase 17-J)" 기준으로 변경. | 문서 링크·수치 가드 |

## A. 제품·인수

| # | 발견 | 조치 |
|---|---|---|
| A-1 | "현재 검증"이 178, 실행 명령 아래 기대값이 175면 신뢰가 떨어진다. | 한 수치(180)로 통일하고, 자동 가드가 재발을 막는다. |
| A-2 | 리포트 파일명이 두 가지면 독자가 `ls artifacts` 결과와 문서를 대조할 수 없다. | 긴 이름 하나로 통일하고 7개 파일에서 검사. |

## B. 정확성

| # | 발견 | 조치 |
|---|---|---|
| B-1 | 수집 테스트 수는 파라미터화로 쉽게 바뀐다. | 하드코딩 대신 `pytest --collect-only` 결과를 사용. |
| B-2 | 문서 수치를 코드에서 유도하지 않으면 반드시 어긋난다. | CI와 동일한 전체 수집을 테스트 안에서 수행. |
| B-3 | `/evaluation`은 glob이라 파일명이 달라도 보이지만, CI artifact와 문서 명령은 정확한 이름이 필요하다. | 이름 일관성 테스트로 고정. |

## C. QA·검증

| # | 발견 | 조치 |
|---|---|---|
| C-1 | 가드 테스트 자체가 파라미터/서브프로세스에 취약할 수 있다. | `--collect-only -q`의 "N tests collected" 패턴만 사용하고, 실패 시 마지막 출력을 보여 준다. |
| C-2 | 공개 데모는 무료 인스턴스라 상태가 변한다. | 27일 health 200을 재확인하고, 문서에는 확인 시점을 명시. |
| C-3 | 다른 문서(리뷰)의 과거 수치는 역사 기록이므로 현재 값으로 덮지 않는다. | 현재 기준선 문서 5개만 가드 대상으로 삼는다. |

## 실행 증거

| 명령/검사 | 결과 |
|---|---|
| `python -m pytest -q` | **180 passed** |
| 수집 수 가드 | `pytest --collect-only` 180 == seed/README/HANDOFF/ROADMAP/NEXT |
| layout2 경로 가드 | 7개 파일에서 `evaluation_report_evaluation_layout2.json` 확인 |
| 데이터셋 | 151 files, 두 레이아웃 각 36건 |
| 평가 | 두 레이아웃 모두 문서 EM 36/36, HOLD 19/19, 오보류 0/17, 규칙 36/36, 근거 410/412 |
| 공개 데모 | 2026-11-27 `/api/health` 200 재확인 |

## 남은 위험

- 테스트 수 가드는 `pytest --collect-only`를 한 번 더 실행하므로 스위트가 약 1초 느려진다.
- 문서에 적힌 **과거 페이즈의 수치**(예: Phase 17-I 당시 175)는 역사 기록으로 남기며 현재 값과 다를 수 있다.
- 공개 데모 상태는 외부 인프라에 의존하므로 자동 테스트하지 않는다. 확인 시점과 방법을 문서에 남긴다.
