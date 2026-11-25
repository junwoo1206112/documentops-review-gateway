# DocumentOps Review Gateway — 55초 연속 데모 촬영 가이드

목표: 합성 `.txt` 문서가 **원문 근거 → 규칙 검증 → HOLD → 사람 승인 → append-only 감사**를
통과하는 모습을 한 번의 연속 녹화로 보여 준다. 이 문서는 다른 프로젝트용
`PORTFOLIO_DEMO_AND_SITE_COPY.md`를 대체하지 않으며, 이 저장소의 R-002 전용 대본이다.

## 자동 녹화(권장)

Playwright와 Chromium이 있는 Python에서는 실제 로컬 UI를 조작해 1280×720 WebM을 자동 생성할 수 있다.
이 도구는 임시 SQLite DB·로컬 uvicorn만 사용하고, `data/`의 기존 DB와 외부 서비스는 건드리지 않는다.

```powershell
C:\Users\junwo\AppData\Local\Programs\Python\Python312\python.exe `
  tools\record_demo.py --output artifacts\documentops-demo.webm
```

생성본은 2026-11-26에 56.8초로 검증했다. 첫 장면의 합성·mock 고지, 정상·HOLD·중복·승인,
422와 409 서버 차단 장면을 모두 포함한다. 공개 전에는 아래 체크리스트로 다시 검토한다.

## 수동 촬영 전 준비

PowerShell 두 창을 사용한다. 기존 개발 DB를 건드리지 않도록 전용 데모 DB를 쓴다.

```powershell
# 창 1 — 저장소 루트
$env:DOCUMENTS_DB_PATH = "$PWD\data\documentops-demo.db"
$env:RATE_LIMIT_PER_MINUTE = "0"
uvicorn app.asgi:app --port 8000
```

`data/documentops-demo.db`가 이전 촬영에서 남아 있으면, **서버를 종료한 뒤 이 전용 파일만**
삭제하고 같은 명령으로 다시 시작한다. 기본 `data/documentops.db`나 실제 데이터는 삭제하지 않는다.

첫 자막은 다음 문구를 그대로 쓴다.

> 합성 데이터 · 외부 시스템 실행 없음(mock) · 사람만 승인 가능

## 55초 촬영 대본

| 시간 | 조작 | 화면에 남겨야 할 증거 | 내레이션 예시 |
|---|---|---|---|
| 0–5초 | `/` 첫 화면과 첫 자막 | 합성 데이터 고지, 업로드 제한 | “원문 근거가 없는 값은 승인되지 않는 문서 검토 게이트입니다.” |
| 5–13초 | `DEMO-0001.txt` 업로드 | `PENDING_REVIEW`, 원문 노란 span, 필드 근거 | “정상 문서는 필드별 원문 위치와 함께 검토 대기로 들어갑니다.” |
| 13–21초 | `DEMO-0002.txt` 업로드 | `HOLD`, `LINE_TOTAL_MISMATCH`, 승인 버튼 비활성 | “총액이 맞지 않으면 자동으로 보류되고 UI에서 승인할 수 없습니다.” |
| 21–31초 | `DEMO-0003.txt`, 이어 `DEMO-0004.txt` 업로드 | 첫 문서 `PENDING_REVIEW`, 둘째 `HOLD`, `DUPLICATE_DOCUMENT`, `duplicate_of` | “같은 문서번호의 두 번째 접수는 중복 근거와 함께 보류됩니다.” |
| 31–41초 | `DEMO-0001` 상세에서 `reviewer-a`, `원문 대조 완료` 후 승인 | `APPROVED`, 판정 이력, 감사 3건 | “승인은 사람 별칭과 사유가 있어야만 기록됩니다.” |
| 41–49초 | 새 정상 문서에서 사유를 비운 채 승인 시도 | 오류와 HTTP 422 | “사유가 빠진 판정은 서버가 422로 거부합니다.” |
| 49–55초 | 아래 409 요청을 터미널에서 실행 | HTTP 409, `HOLD → APPROVED` 금지 메시지 | “UI 우회 요청도 서버 상태 전이 규칙이 409로 차단합니다.” |

## 409 서버 차단 장면

UI의 비활성화 버튼은 보조 안전장치다. 서버 규칙을 직접 보이려면 `DEMO-0002`의 문서 ID를
브라우저 주소에서 복사하고 다음 요청을 실행한다.

```powershell
curl.exe -i -X POST "http://127.0.0.1:8000/api/documents/<HOLD_DOCUMENT_ID>/decision" `
  -H "Content-Type: application/json" `
  -d '{"decision":"APPROVE","reviewer_alias":"reviewer-a","reason":"영상용 서버 차단 확인"}'
```

기대 결과는 `HTTP/1.1 409 Conflict`와 `E_CONFLICT`다. 문서 상태가 바뀌지 않았는지 브라우저에서
다시 확인한다.

## 촬영 후 공개 전 점검

- [ ] 첫 자막에 “합성 데이터 · mock” 고지가 있다.
- [ ] 정상, 금액 불일치, 중복, 승인, 422, 409, 감사 이력이 모두 같은 연속 녹화에 있다.
- [ ] 실제 고객 문서·개인정보·API 키·로컬 파일 경로가 영상에 노출되지 않는다.
- [ ] 영상은 Git에 직접 커밋하지 않고 Release asset 또는 일부공개 YouTube 링크로 공개한다.
- [ ] 공개한 뒤에만 README에 URL과 촬영 날짜를 추가한다. 현재는 미촬영이므로 링크를 넣지 않는다.
