# Phase 7 전문가 A·B·C 교차 검증

대상: Phase 6 이후 `main`의 평가 리포트 정확성, 접근성, 인수 문서의 증거 정합성
기준: "문서가 말하는 상태"와 "실행으로 확인한 상태"가 같고, 키보드 사용자가 전체 흐름을 쓸 수 있음

## 판정 요약

| 관점 | 판정 | 근거 |
|---|---|---|
| A. 제품·인수 | 개선 반영 | 랜드마크·skip link·표 헤더·현재 필터·오류 알림을 추가했다. 키보드 첫 Tab으로 본문 건너뛰기가 잡히는 것을 브라우저에서 확인했다. |
| B. 정확성 | 개선 반영 | 평가 리포트가 `--dataset`과 무관하게 전역 `DATASET_VERSION`을 기록하던 버그를 수정했다. 이제 manifest에서 버전을 읽고, 불일치·빈 manifest는 실패한다. |
| C. QA·증거 | 개선 반영 | Phase 6 문서의 "전체 pytest 미실행" 기록이 사실과 달라 정정했다. 133 passed를 재확인한 뒤, Phase 7 추가 테스트를 포함해 **140 passed**를 기록했다. |

## 실제로 잡힌 결함

| ID | 문제 | 영향 | 조치 | 회귀 방지 |
|---|---|---|---|---|
| P7-1 | `evaluate_dataset`가 manifest의 `dataset_version`을 읽지 않고 `app.version.DATASET_VERSION`을 리포트에 썼다. | 다른 데이터셋 경로로 평가해도 리포트가 현재 상수 버전을 주장한다. 지표의 데이터 버전 추적이 거짓이 된다. | manifest의 모든 줄에서 버전을 모아 하나로 일치할 때만 사용한다. 빈 manifest·불일치는 `ValueError`(CLI exit 2). | `test_report_uses_manifest_dataset_version`, `test_inconsistent_manifest_versions_are_rejected`, `test_empty_manifest_is_rejected` |
| P7-2 | Phase 6 문서가 "이 환경에서는 TestClient가 멈춘다"는 전제로 전체 pytest를 보류로 기록했다. | 인수자가 이미 통과한 상태를 실패로 오해하고 불필요한 R-008 작업을 한다. | 133 passed, exit 0을 재확인하고 Phase 6 문서·HANDOFF·seed의 상태를 정정했다. R-008을 제거했다. | `test_handoff_seed_is_valid_and_tracks_state`(상태·수치) |
| P7-3 | 문서 페이지에 skip link, 표 `scope`, 필터 `aria-current`, 오류 `role="alert"`, 포커스 표시가 없었다. | 키보드·스크린리더 사용자가 표 구조와 오류를 놓치고, 첫 포커스가 메뉴에 갇힌다. | 4개 템플릿과 CSS를 보강하고, 접근성 토큰을 테스트로 고정했다. | `test_landmarks_skip_link_and_table_semantics`, `test_active_filter_reports_current_page`, `test_detail_page_has_accessible_raw_text_and_tables`, `test_error_message_has_alert_role` |
| P7-4 | README가 "Phase 0~5 완료"라고만 적어, 공개 마감(R-001/R-002)이 남았는데도 완료처럼 읽혔다. | 인수자·채용 담당자가 미완료 증거를 완료로 오해한다. | "Phase 0~7 구현 완료 + 공개 마감 남음"으로 분리하고, 남은 항목을 명시했다. | `test_readme_documents_runbook_and_limits`, `test_handoff_document_covers_resume_and_backlog` |
| P7-5 | 보안 문서에 인증 부재와 CSRF의 관계가 없었다. | 폼 POST를 공개 배포하면 "CSP가 있으니 안전하다"는 오해가 생긴다. | 위협 모델에 "인증 없음 → CSRF 토큰은 신뢰 경계가 아님, 공개 배포 전 인증/세션+CSRF 도입"을 명시했다. | `test_security_policy_states_synthetic_data_and_limits` |

## A. 제품·인수

| # | 발견 | 조치 |
|---|---|---|
| A-1 | 첫 Tab이 메뉴 링크로 가서 매 페이지마다 3개 링크를 지나야 한다. | `본문으로 건너뛰기` 링크를 추가하고 `main#main tabindex="-1"`로 포커스 대상이 되게 했다. |
| A-2 | 표가 시각적으로만 구분되고 헤더-셀 관계가 없다. | 모든 `th`에 `scope="col"`, 표에 `caption.sr-only`를 넣었다. |
| A-3 | 필터 칩이 "현재 어느 필터인지"를 색으로만 알린다. | 활성 칩에 `aria-current="page"`를 준다. |
| A-4 | 폼 오류가 화면에만 뜨고 스크린리더에 알려지지 않는다. | 오류 문단에 `role="alert"`를 준다(업로드·판정·재검증·평가). |

## B. 정확성

| # | 발견 | 조치 |
|---|---|---|
| B-1 | 리포트의 `dataset_version`과 `documents` 수가 실행 대상과 어긋날 수 있다. | 버전은 manifest에서 유도하고, 문서 수는 실제 처리 수로 기록한다. |
| B-2 | 빈 manifest에서 `documents=0`, 모든 비율 0.0인 "성공" 리포트가 나올 수 있다. | 빈 manifest를 오류로 만든다. 0건 평가는 성과가 아니다. |
| B-3 | 버전 불일치 manifest를 조용히 섞으면 지표 해석이 불가능하다. | 버전 집합이 2개 이상이면 실패한다. |

## C. QA·증거

| # | 발견 | 조치 |
|---|---|---|
| C-1 | 문서 상태가 실제 실행 결과보다 보수적으로 낮게 기록됐다. | 실행 결과를 근거로 상향 정정하고, 날짜·테스트 수를 함께 남겼다. |
| C-2 | 접근성 개선이 "느낌"으로 끝날 수 있다. | HTML 토큰과 오류 응답을 테스트로 고정했다. 키보드 Tab은 브라우저에서 직접 확인했다. |
| C-3 | 평가 버전 수정이 기존 기준선을 바꾸지 않는지 확인해야 한다. | 기본 데이터셋 지표(36/36, 19/19, 0/17, 410/412)가 그대로임을 전체 테스트와 CLI로 확인했다. |

## 남은 접근성 작업 (R-007 부분 완료)

- 완료: 랜드마크, skip link, 표 semantics, `aria-current`, `role="alert"`, `:focus-visible`, 내부 링크 점검.
- 남음: 색 대비 자동 측정, 태블릿(768/1024px) 스크린샷, 스크린리더로 전체 판정 흐름 1회 점검.
- 이 항목은 `handoff.seed.yaml`의 R-007에 `state: partial`로 남긴다. 완료로 과장하지 않는다.
