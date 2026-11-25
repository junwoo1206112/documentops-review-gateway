# fixtures/demo — 시연용 4건

평가 지표에 포함하지 않는다. 시연 순서는 다음과 같다.

| 파일 | 장면 | 기대 결과 |
|---|---|---|
| `DEMO-0001.txt` | 정상 문서 | `PENDING_REVIEW`, 필드 6개 + 원문 근거 |
| `DEMO-0002.txt` | 총액 불일치 | `HOLD`, `LINE_TOTAL_MISMATCH` |
| `DEMO-0003.txt` | 정상 문서(중복 기준) | `PENDING_REVIEW` |
| `DEMO-0004.txt` | `DEMO-0003`과 같은 문서번호 | `HOLD`, `DUPLICATE_DOCUMENT` |

`python scripts/seed_demo.py`가 빈 DB에 이 순서로 접수한다. 생성기는 `tools/generate_dataset.py`다.
