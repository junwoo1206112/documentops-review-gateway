# fixtures/evaluation — 읽기 전용

- 이 디렉터리의 `.txt`, `manifest.jsonl`, `expected/*.json`은 `tools/generate_dataset.py`만 만든다.
- 테스트·평가·데모 실행 중에는 **수정하지 않는다.**
- 파일을 바꾸려면 생성기를 고치고 `DATASET_VERSION`을 올린 뒤, `python tools/generate_dataset.py`로
  전체를 다시 만든다. 일부만 손으로 고치면 `tests/test_dataset_manifest.py`가 실패한다.
- `manifest.jsonl`의 줄 순서가 접수 순서다. 중복 판정이 순서에 의존하므로 순서를 바꾸지 않는다.

구성: 정상 16, 필수값 누락 5, 날짜 2, 금액 형식 1, 금액 불일치 6, 중복 2, 알 수 없는 거래처 2, 근거 없음 2.
