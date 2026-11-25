# Phase 11 전문가 A·B·C 교차 검증 — 대비·반응형 자동 감사

대상: R-007의 색 대비, 태블릿 폭 레이아웃, 자동 접근성 표식.

| 관점 | 판정 | 근거 |
|---|---|---|
| A. 사용성 | 통과 | 실제 768px·1024px 캡처에서 업로드 폼, 상태 필터, 문서 표, 안내문과 footer가 겹치지 않고 읽힌다. |
| B. 접근성 | 통과(자동 범위) | 본문·muted·accent·warning·danger·button의 6개 핵심 조합이 6.27:1~15.54:1로 WCAG AA 일반 텍스트 기준을 통과했다. |
| C. QA | 개선 반영 | `tools/audit_accessibility.py`가 임시 DB·로컬 서버에서 캡처, 대비 계산, skip link·landmark·현재 필터·caption 표식을 JSON으로 재현한다. |

## 생성물

- `artifacts/accessibility_audit.json`
- `artifacts/accessibility-768.png`
- `artifacts/accessibility-1024.png`

## 남은 사람 검토

스크린리더로 업로드→판정 흐름을 실제로 한 번 완주해야 R-007을 완전히 닫을 수 있다.
자동 DOM 검사·스크린샷은 이 실사용 검토를 대체하지 않는다.
