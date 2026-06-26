# CodeHeat — 작업 현황 (클로드 코드 인계용)

## 프로젝트 한 줄 요약
코드 복잡도 + git 히스토리를 분석해서 "어떤 파일을 먼저 리팩토링해야 하고, 누구에게 물어보면 좋을지"를 알려주는 오픈소스 CLI 툴. 핵심 철학: **"누가 쌌나"(blame)가 아니라 "누가 해결할 수 있나"(매칭)**.

전체 파이프라인 설계는 `code-smell-radar-pipeline.md` 참고.

---

## 기술 스택
- 언어: Python 3.10+
- 복잡도 분석: `lizard` (다언어 지원, 무료)
- 오너십 분석: git CLI 서브프로세스 래핑
- LLM (예정): Ollama 로컬 또는 API (숫자/메타데이터만 전달, 코드 본문은 절대 안 넘김)
- 대시보드 (예정): Next.js + D3.js
- 전부 무료 스택 지향

---

## 현재까지 완료된 것 — 1단계(정적 분석) + 2단계(오너십)

### 디렉토리 구조
```
codeheat/
├── codeheat/
│   ├── __init__.py
│   ├── models.py          # 완료: dataclass 데이터 모델 (+ ContributorScore, FileOwnershipReport)
│   ├── static_scan.py     # 완료: 복잡도 + TODO 분석
│   ├── cli.py             # 완료: `codeheat scan|own <path>` 진입점
│   ├── ownership.py       # 완료: 2단계 오너십 분석
│   └── insights.py        # 미작성 (3단계, LLM)
├── pyproject.toml         # 완료
└── README.md              # 완료
```

### 각 파일 역할
- **models.py**: `FileSmellReport`, `TodoItem` dataclass 정의. `FileSmellReport.oldest_todo_days`는 property로 계산. `duplication_ratio` 필드는 2차(jscpd 연동)용으로 비워둠(기본값 0.0).
- **static_scan.py**:
  - `scan_complexity()`: lizard로 파일별 함수 CCN 수집
  - `find_todos()`: 정규식으로 TODO/FIXME 라인 탐지
  - `get_todo_age_days()`: `git log -S`로 해당 TODO가 처음 등장한 커밋 찾아 나이(일) 계산
  - `build_smell_reports()`: 위를 묶어서 복잡도 내림차순 정렬된 리스트 반환
- **cli.py**: argparse 기반. `scan` 서브커맨드, `--output`, `--no-todo-age` 옵션.

### 동작 확인됨
```bash
python -m codeheat.cli scan <repo_path> --output smell_report.json
python -m codeheat.cli scan <repo_path> --no-todo-age   # git log 생략(속도)
```
출력: 복잡도 내림차순 정렬된 `smell_report.json`

### 작업 중 발견/해결한 이슈 (반복 방지용 메모)
1. `lizard.analyze()`의 인자명은 `exclude_pattern` (문서에 종종 나오는 `exclude_pattern_list` 아님)
2. TODO 정규식은 반드시 단어 경계(`\b`) 필요 — 안 그러면 `todos`, `TODO_PATTERN` 같은 변수명까지 오탐

### 알려진 한계 (1단계 기준)
- TODO 탐지가 정규식 기반이라 docstring/주석에 설명용으로 쓴 "TODO" 단어도 잡힐 수 있음 (실코드선 드물어 MVP는 무시)
- `duplication_ratio` 미구현 (2차 jscpd 예정)
- `git log -S`는 TODO 텍스트 앞 40자만 사용 — 너무 일반적 문구면 오매칭 가능

---

## 완료된 것 — 2단계 (오너십 분석 `ownership.py`)

목표 달성: 파일별로 "도메인 지식 점수"가 높은 기여자 1~2명 추출.
- `git log --follow --numstat --format=%H|%an|%at -- <file>` 한 번으로 메타데이터+churn 수집
- 핵심 정의대로 단순 최다 수정자가 아니라 **복잡도가 급증한 시점에 커밋한 사람**에 가중치
- 점수 = Σ(최근성 가중치 × 변화량 가중치)
  - 최근성: 반감기 1년 지수 감쇠 (`_recency_weight`)
  - 변화량: `git show <commit>:<path>`를 lizard로 분석한 max CCN 델타. 실패 시 `log1p(churn)` 폴백
- CLI: `codeheat own <repo>` (`--from-report`, `--top`, `--limit`, `--churn-only`)
- 출력: `ownership_report.json` (파일별 top_contributors 리스트)
- 동작 확인: 이 레포에 `scan → own` 파이프라인으로 검증 완료

### 작업 중 발견/해결한 이슈 (반복 방지용 메모)
1. `git log --numstat`은 최신→과거 순으로 나오므로, 복잡도 델타를 시간순으로 누적하려면 `reverse()` 필요
2. `--from-report` 입력은 1단계가 이미 복잡도 내림차순 정렬해둔 순서를 그대로 보존(우선순위 승계)
3. LLM 레이어 제약대로 `FileOwnershipReport`도 이름/점수/메타데이터만 담고 코드 본문은 안 넘김

---

## 다음 할 일 (우선순위 순)

### 3단계 — LLM 인사이트 (`insights.py`)
- 입력: 1+2단계 JSON (숫자/메타데이터만, **코드 본문 절대 금지**)
- 출력: 리팩토링 우선순위 + "누구에게 무엇을 물어볼지" 가이드
- Ollama(무료) 또는 API 선택 가능하게

### 4단계 — 출력 레이어
- 4-1: Next.js + D3 트리맵 대시보드
- 4-2: GitHub Action PR 봇 ("이 PR로 checkout.py 히트맵 온도 상승")
- 4-3: VS Code 확장 (가장 나중, 반응 보고 결정)

---

## 클로드 코드에서 시작하는 법
1. 이 `codeheat/` 폴더를 작업 디렉토리로 열기
2. `pip install -e .` 로 설치
3. 다음 작업은 `insights.py` 작성부터 (3단계, LLM 레이어)
