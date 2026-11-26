# DocumentOps Review Gateway — 포트폴리오 사례 요약

## 한 줄 소개

합성 한국어 거래 문서에서 추출값의 **원문 근거를 검증**하고, 차단 오류는 `HOLD`로 멈춘 뒤
**사람만 승인**할 수 있게 만든 문서 검토 게이트웨이입니다.

> Evidence-gated document review: values without verifiable source evidence cannot be approved.

## 포트폴리오 카드용 문구

**DocumentOps Review Gateway**는 문서 자동화 결과를 바로 실행하지 않고, 원문 span·명시 규칙·사람
승인·append-only 감사 이력으로 검토하는 FastAPI 프로젝트입니다. 두 합성 텍스트 레이아웃을 독립
평가하고, 오류 문서는 자동 승인 대신 `HOLD`로 분리합니다. 공개 데모·56.8초 영상·CI·평가 리포트로
동작 범위와 한계를 재현 가능하게 공개했습니다.

## 해결하려는 문제

문서에서 금액·거래처·날짜를 읽는 것만으로는 안전하지 않습니다. 추출값이 원문 어디에 있었는지,
합계·형식·중복 규칙을 만족하는지, 누가 어떤 근거로 최종 승인했는지가 남아야 합니다.

이 프로젝트는 다음 원칙으로 그 문제를 다룹니다.

1. 모든 직접 추출값은 원문 span과 발췌문으로 다시 검증한다.
2. blocking 이슈가 하나라도 있으면 문서는 `HOLD`다.
3. 승인·반려는 사람만 할 수 있고, 사유와 별칭이 append-only 감사 이력에 남는다.

## 설계와 구현 범위

| 영역 | 구현한 내용 | 의도 |
|---|---|---|
| Ingestion | `.txt` UTF-8·크기·SHA-256 검증, 중복 탐지 | 입력과 원문을 바꾸지 않음 |
| Extraction | 결정론적 두 텍스트 레이아웃 파서, 선택형 오프라인 LLM 계약 스텁 | API 키 없이 재현 가능한 기본 경로 |
| Evidence | 값·span·발췌문 재대조, `verified/derived/missing` 상태 | 근거 없는 값을 신뢰하지 않음 |
| Validation | 8개 blocking 규칙, `HOLD` 상태 전이 | 오류를 자동 승인으로 흘리지 않음 |
| Human review | 원문 재인용 수정, 승인/반려, append-only 감사 | 사람 판단과 변경 근거를 분리·추적 |
| Evaluation | 레이아웃별 독립 합성 36건, CI artifact·화면 리포트 | 파서·규칙 회귀를 공개적으로 확인 |

## 검증 근거

| 항목 | 확인한 결과 | 직접 확인 |
|---|---|---|
| 회귀 테스트 | 181개 테스트 통과(2026-11-27 기준) | [CI 워크플로](https://github.com/junwoo1206112/documentops-review-gateway/actions/workflows/ci.yml) |
| 레이아웃 평가 | 각 36/36 문서 일치, 규칙 일치 36/36 | [평가 화면](https://documentops-review-gateway-demo.onrender.com/evaluation) |
| HOLD 안전성 | HOLD 재현 19/19, 오보류 0/17 | [평가 정의](../evaluation.md) |
| 근거 검사 | 410/412 verified; 부족 2건은 의도된 파생 총액 | [평가 정의](../evaluation.md) |
| 사용자 흐름 | 정상·HOLD·중복·승인·서버 차단·감사 이력 | [56.8초 데모 영상](https://github.com/junwoo1206112/documentops-review-gateway/releases/download/v0.1.0-demo/documentops-demo.webm) |
| 공개 시연 | 합성 데이터만 보이는 읽기 전용 Render 데모 | [공개 데모](https://documentops-review-gateway-demo.onrender.com) |

공개 데모는 2026-11-27에 health `200`, 문서 4건, 쓰기 요청 `403`, 두 평가 리포트를 확인했다.
무료 인스턴스는 비활성 후 첫 응답이 늦을 수 있다.

## 60초 면접 설명

“이 프로젝트는 문서를 읽는 AI 자체보다 **읽은 결과를 안전하게 업무에 넣는 게이트**에 초점을 둔
프로젝트입니다. 값마다 원문 근거를 다시 확인하고, 합계·형식·중복 같은 blocking 오류가 있으면
자동 승인하지 않고 HOLD로 보냅니다. 사람이 승인하거나 원문을 재인용해 수정한 모든 과정은
append-only 감사 이력에 남습니다. 두 가지 텍스트 레이아웃을 각각 36건씩 평가해, 파서 변경이
기존 경로를 깨지 않는지도 CI와 공개 리포트로 확인했습니다.”

## 의도적으로 하지 않은 것

- 실제 고객 문서·개인정보를 사용하지 않았다. 모든 데이터는 합성 데이터다.
- OCR·이미지/PDF 입력은 현재 릴리스에서 채택하지 않았다.
- 실제 LLM 호출, API 키, 외부 데이터 전송을 기본 경로에 넣지 않았다.
- 자동 승인, 실제 ERP/메일/결제 실행, 인증·멀티테넌시·다중 인스턴스 운영을 주장하지 않는다.
- SQLite 단일 프로세스 데모이므로 실제 운영 규모·OCR 품질·실제 업무 효과를 측정했다고 주장하지 않는다.

확장 요구가 생기면 [남은 페이즈 실행 안내](../NEXT_PHASES_HANDOFF.md)의 Gate를 하나씩 열어
독립 fixture·지표·CI 증거부터 추가한다.

## 더 읽을 자료

- [README](../../README.md) — 실행 방법, 공개 데모, API, 범위
- [평가 문서](../evaluation.md) — 지표 분모·한계·리포트 스키마
- [보안 정책](../security.md) — 합성 데이터·읽기 전용 공개 데모 정책
- [인수 자료](../../HANDOFF.md) — 재현 명령, 계약, 상태
- [남은 페이즈 실행 안내](../NEXT_PHASES_HANDOFF.md) — 조건부 확장 경로
