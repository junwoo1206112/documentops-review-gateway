# 포트폴리오 개선 실행 로그 — 2026-11-25

상위 계획: [README.md](README.md)  
원칙: 기존 저장소의 검증 가능한 사실만 강화하며, 검증되지 않은 성능·운영 효과·팀원 기여를 추가하지 않는다.

## Phase 0 — 현재 증거 기준선 확정

### 확인한 저장소

| 저장소 | 현재 확인 사실 | 변경 위험 | Phase 1 조치 |
|---|---|---|---|
| `C:\AI\Evidence-Gated-Work-Agent` | GitHub Actions `verify`가 Python 3.12, pytest, 고정 평가를 실행한다. README에 Render 데모·156 passed·14/14·한계 고지가 있다. | 작업 트리는 깨끗하다. | README 첫 화면에 실제 `verify` 배지를 추가한다. |
| `C:\AI\manufacturing-ml-portfolio` | GitHub Actions `CI`가 Python 3.12와 pytest를 실행한다. README에 Docker·SQLite·테스트·한계가 있다. | `01_...` 미추적 폴더가 있다. 해당 폴더는 건드리지 않는다. | README 첫 화면에 실제 `CI` 배지를 추가한다. |
| `C:\AI\steel-surface-defect-classification` | README는 128 테스트·데이터 누수 방지·한계를 명시한다. | `data-quality.json`, `manifest.csv`가 사용자 변경 상태다. | CI가 확인되기 전에는 배지를 추가하지 않는다. 영상·실행 문서만 후속으로 검토한다. |
| `C:\AI\MultiplayFishingGame-master` | 팀 프로젝트·개인 기여·서버 낚시 판정·입력 구조를 README가 상세히 설명한다. | 씬/에셋/코드/문서 등 대량 미커밋 변경이 있다. | 기존 파일을 수정하지 않는다. 영상 검증과 정리 범위를 별도 변경 단위로 분리한다. |

### 전문가 A·B·C 판정

- **A (채용·포트폴리오)**: Agent와 제조 ML의 README가 이미 사실·한계를 잘 구분한다. 첫 화면의 CI 증거와 짧은 시연 링크가 부족하다.
- **B (AI 시스템)**: Agent는 “결정론적 evidence gate”라는 차별점이 명확하다. 제조 ML은 단일 지표보다 최신 지표 문서와 합성 데이터 한계를 유지해야 한다.
- **C (QA·인수인계)**: Unity와 Steel 저장소는 작업 트리가 더럽기 때문에 현 시점에 광범위한 문서 갱신 또는 커밋을 섞으면 검증 경계가 무너진다.

### Phase 0 결정

1. Evidence-Gated Agent와 Manufacturing ML만 README 배지를 추가한다.
2. 영상은 새로 만들어 실제 시연이 끝난 다음에만 README에 링크한다.
3. Unity는 현재 대량 변경을 별도 정리·검증하기 전까지 AI 포트폴리오 사이트에 보조 카드 문구만 준비하며, 원본 README를 추가 수정하지 않는다.

## Phase 1 — README 신뢰 증거 보강

### 목표

GitHub Actions가 존재하는 두 저장소의 README 첫 화면에 실제 워크플로 배지를 추가한다.

### 수용 기준

- Agent README는 `verify.yml`이 아니라 실제 파일 `.github/workflows/ci.yml`, 워크플로 이름 `verify`, 기본 브랜치 `main`과 일치하는 배지를 가진다.
- Manufacturing README는 실제 워크플로 이름 `CI`, 기본 브랜치 `master`와 일치하는 배지를 가진다.
- 배지 추가 외의 성능 수치·기능 주장·기존 README 본문은 변경하지 않는다.
- 각 저장소의 `git diff --check`가 통과한다.

### 실행 결과

- 2026-11-25에 `Evidence-Gated-Work-Agent/README.md`에 `verify` 워크플로 배지를 추가했다.
- 같은 날 `manufacturing-ml-portfolio/README.md`에 `CI` 워크플로 배지를 추가했다.
- 두 배지는 각 저장소의 실제 `.github/workflows/ci.yml`과 기본 브랜치(`main`, `master`)를 기준으로 만들었다.
- 두 저장소에서 `git diff --check`를 실행했으며 공백 오류는 없었다. Agent 저장소에서는 기존 줄바꿈 정책에 대한 CRLF 경고만 표시됐다.
- 아직 커밋·push하지 않았다. CI가 원격에서 실제 통과한 뒤 저장소별 독립 커밋으로 처리한다.

## 다음 페이즈 (아직 실행 전)

### Phase 2 — 45~60초 증빙 영상

- Agent: 충분 근거 → 승인 전 409 차단 → 승인 → mock 실행 → audit.
- Manufacturing: 데이터 검증 → 예측/이상 징후 → 결과의 한계 → 최신 증빙 문서.
- 동영상 링크는 촬영·확인 이후만 README에 추가한다.

준비 완료: `PORTFOLIO_DEMO_AND_SITE_COPY.md`에 두 프로젝트의 촬영 순서, 사실 기반 내레이션, 촬영 전 체크리스트를 기록했다. 실제 녹화와 링크 삽입은 아직 미완료다.

### Phase 3 — 포트폴리오 사이트 카드 정리

- Agent, 제조 ML, Steel 카드의 한 줄 가치·검증 수치·한계를 같은 형식으로 정리한다.
- Unity는 AI 주력 카드가 아닌 `C#·Unity 팀 프로젝트` 보조 카드로 배치한다.
- Unity 역할은 “Excel 데이터 관리, 멀티플레이 흐름 통합, 캐릭터 이동, 도감·상점 기능” 범위로만 표기한다.

실행 완료: 공개 포트폴리오 사이트에 `보조 프로젝트` 섹션을 추가해 Unity `Multiplay Fishing Game`을 AI 주력 카드와 분리했다. 개인 기여는 Excel 데이터 관리·멀티플레이 흐름 통합·캐릭터 이동·도감/상점 기능 범위로만 적었고, 영구 서버 경제·100인 성능·검증되지 않은 흐름을 주장하지 않았다.

- 사이트 버전: 16
- 배포 상태: succeeded (2026-11-25)
- 공개 URL: `https://kimjunwoo-ai-portfolio.kimjunwoo1206112.chatgpt.site`

### Phase 4 — 안전한 마감

- 저장소별 독립 커밋·push 전에 CI 실행 결과와 공개 배지 상태를 확인한다.
- Unity의 빌드·영상·2인 접속 검증은 대량 변경을 정리한 뒤 별도 체크리스트로 진행한다.

#### 실행 결과

- `Evidence-Gated-Work-Agent`: README 배지 변경을 커밋 `b7c230d` (`docs: add CI status badge`)으로 `main`에 push했다.
- `manufacturing-ml-portfolio`: README 배지 변경을 커밋 `684f9bf` (`docs: add CI status badge`)으로 `master`에 push했다. 기존 미추적 `01_...` 폴더는 커밋에 포함하지 않았다.
- GitHub 상태 API는 확인 시점에 두 커밋의 legacy status를 반환하지 않았다. 이 값은 Actions 성공/실패의 증거가 아니므로, 배지 화면 또는 Actions 탭에서 실제 실행 결과를 다음 확인 항목으로 둔다.
- Unity·Steel은 기존 사용자 변경을 보존하기 위해 커밋·push 대상에서 제외했다.

#### 원격 CI 확인 결과

- `Evidence-Gated-Work-Agent`의 `verify`는 커밋 `b7c230d62efe04fe42fdd4fae6d2574c631ed156`에서 **success**로 완료됐다. [실행 결과](https://github.com/junwoo1206112/Evidence-Gated-Work-Agent/actions/runs/45518421693)
- `manufacturing-ml-portfolio`의 `CI`는 커밋 `684f9bf09bef5051e4bce5acf200d4d956e8223f`에서 **success**로 완료됐다. [실행 결과](https://github.com/junwoo1206112/manufacturing-ml-portfolio/actions/runs/45518476898)
- 따라서 두 README의 CI 배지는 실제 성공한 워크플로를 가리킨다.

#### 영상 상태

- Agent·Manufacturing ML의 45~60초 시연 영상 파일 또는 공개 링크는 현재 확인되지 않았다.
- `PORTFOLIO_DEMO_AND_SITE_COPY.md`의 촬영 순서대로 녹화한 뒤, 공개 가능한 URL을 각 README의 라이브 데모 근처에 추가한다.
