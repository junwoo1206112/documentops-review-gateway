# Phase 6 전문가 A·B·C 교차 검증

대상: 2026-11-26 현재 `main`의 운영 안전성, 검증 재현성, 인수 문서.

## 판정 요약

| 관점 | 판정 | 검증 근거 |
|---|---|---|
| A. 제품·인수 | 통과 | `HANDOFF.md`와 `handoff.seed.yaml`에 완료 범위, 결정 대기 항목, 재개 순서가 있다. 원격 CI와 데모 영상은 아직 증거가 없어 완료로 표시하지 않았다. |
| B. 보안·운영 | 개선 반영 | rate limiter가 대량의 일회성 클라이언트 버킷을 보존할 수 있던 문제를 만료 버킷 전체 정리로 수정했다. 기본 경로와 정책은 유지된다. |
| C. QA·재현성 | 통과 | 데이터셋 재생성 테스트의 자식 프로세스에 UTF-8 출력을 고정해 Windows 콘솔 코드페이지 경고를 제거했다. 전체 pytest를 다시 실행해 **133 passed, exit 0**을 확인했다. |

## 반영한 결함

| ID | 문제 | 영향 | 조치 | 회귀 방지 |
|---|---|---|---|---|
| P6-1 | 10,000개를 넘는 rate-limit 버킷에서, 이전 구현은 현재 요청 클라이언트 외의 만료 버킷을 제거하지 않았다. | 고카디널리티 요청 후 프로세스 메모리가 불필요하게 유지될 수 있다. | 버킷 수가 10,000개를 넘을 때 모든 버킷에서 60초 초과 타임스탬프를 정리하고 빈 버킷을 제거한다. | `test_rate_limiter_prunes_stale_high_cardinality_buckets` |
| P6-2 | 데이터셋 재생성 테스트가 자식 Python의 Windows 기본 콘솔 인코딩을 UTF-8로 해석했다. | 종료 코드는 0이어도 pytest reader-thread 경고가 CI 로그에 남을 수 있다. | 자식 프로세스의 `PYTHONIOENCODING=utf-8`을 명시했다. | `test_dataset_regenerates_identically` |

## 변경하지 않은 의도적 경계

- `TRUST_PROXY_HEADERS=false`가 기본값이다. 프록시 신뢰 범위를 구성하지 않은 배포에서 이를 켜지 않는다.
- OCR, LLM 추출, 사람 필드 수정, 인증·권한은 `docs/decisions/pending.md`의 선행 결정을 받기 전에는 구현하지 않는다.
- `reviewer_alias`는 인증이 아니라 감사 식별자다.

## 검증 기록

| 명령/검사 | 결과 |
|---|---|
| `.venv\\Scripts\\ruff.exe format --check .` | 통과 |
| `.venv\\Scripts\\ruff.exe check .` | 통과 |
| `.venv\\Scripts\\python.exe -m pytest -q` | **133 passed, exit 0** (2026-11-26 재실행) |
| `python tools/generate_dataset.py --check` | 78 파일, 데이터셋 `synth-2026-11-26.2` 일치 |
| `python -m app.evaluate --dataset fixtures/evaluation --report artifacts/evaluation_report.json` | document EM 1.000, HOLD recall 19/19, false HOLD 0/17, rule match 1.000, evidence validity 0.995 |

> 이전 검토 환경에서 관측된 Windows `socketpair` 차단은 이 실행 환경에서 재현되지 않았다.
> 전체 테스트는 일반 셸에서 통과했으므로, 이를 이유로 남은 작업을 만들지 않는다.

## 다음 인수자 실행 순서

1. 완료: 전체 `pytest -q` 133 passed, exit 0을 확인했다.
2. R-001: 원격 저장소 push 후 `ci` 성공을 확인하고 그때만 README 배지를 추가한다.
3. R-002: 합성 데이터·mock 고지와 함께 45~60초 연속 데모 영상을 제작·연결한다.
4. 그 다음에만 P2 결정 항목(P-003 → P-001/P-002/P-004~P-006)을 명시적 승인과 계약 변경 절차에 따라 진행한다.
