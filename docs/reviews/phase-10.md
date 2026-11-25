# Phase 10 전문가 A·B·C 교차 검증 — 실제 UI 데모 녹화

대상: R-002의 실제 애플리케이션 화면 녹화, 장면 충족 여부, 공개 전 안전성.

| 관점 | 판정 | 근거 |
|---|---|---|
| A. 포트폴리오 | 통과(공개 전) | `tools/record_demo.py`가 실제 UI를 조작해 1280×720, 56.8초 연속 WebM을 생성했다. 45~60초 기준을 충족한다. |
| B. 보안·운영 | 통과 | 임시 SQLite DB와 로컬 uvicorn만 사용했다. 기존 `data/` DB, 외부 API, 실제 문서·개인정보는 사용하지 않았다. |
| C. QA·증거 | 통과 | 2초 프레임에서 합성·mock 고지, 20초 프레임에서 `LINE_TOTAL_MISMATCH`와 원문 span, 51초 프레임에서 `HOLD → APPROVED` 서버 차단을 확인했다. |

## 생성물

- 로컬 파일: `artifacts/documentops-demo.webm`
- 길이: 56.8초
- 형식: WebM VP9, 1280×720, 25fps
- 포함: 정상 문서, 금액 불일치 HOLD, 중복 HOLD, 사람 승인, 사유 없는 422, HOLD 직접 승인 409, 감사 흐름

## 남은 외부 단계

영상은 아직 외부에 올리지 않았다. 사용자 계정으로 YouTube 일부공개 또는 GitHub Release asset에 업로드한 뒤,
공개 URL과 촬영 날짜를 README에 추가해야 R-002가 완료된다.
