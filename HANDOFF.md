# CodeHeat — 작업 현황 (클로드 코드 인계용)

## 프로젝트 한 줄 요약
코드 복잡도 + git 히스토리를 분석해서 "어떤 파일을 먼저 리팩토링해야 하고, 누구에게 물어보면 좋을지"를 알려주는 오픈소스 CLI 툴. 핵심 철학: **"누가 쌌나"(blame)가 아니라 "누가 해결할 수 있나"(매칭)**.

전체 파이프라인 설계는 `code-smell-radar-pipeline.md` 참고.

---

## 현재 상태 요약 (2026-06-28 기준)

### 커밋된 것 (git 반영 완료, origin/master 푸시됨)
- 1단계 정적 분석(`static_scan.py`) · 2단계 오너십(`ownership.py`) · 3단계 LLM 인사이트(`insights.py`)
- 최근 커밋: `f0964e2 feat: CodeHeat 3단계 LLM 인사이트 레이어 구현`

### 미커밋 작업 (working tree, 아직 commit 안 함)
사용자 지시로 커밋 보류 중. 다음 두 묶음으로 나눠 커밋하면 깔끔함:

1. **TODO 탐지 정밀화** — `codeheat/static_scan.py`, `pyproject.toml`(pygments 의존성), `README.md`, `HANDOFF.md`
   - 정규식 라인 스캔 → **Pygments 토큰화로 진짜 주석만** + 마커 앵커 규칙. 산문/식별자/정규식정의/코드문장/문자열 리터럴 속 가짜 주석(`s = "# TODO"`)까지 전부 배제.
   - 폴백(Pygments 없음/미지원 확장자)도 `_mask_strings`로 한 줄 문자열 마스킹. 셀프 스캔 0 오탐.
2. **테스트 스위트 신설** — `tests/`(4파일, 36개 통과), `pyproject.toml`(pytest 설정 + `dev` extra)
   - models / static_scan / ownership / insights 커버. git·LLM 호출은 monkeypatch로 오프라인 검증.
   - 핵심 불변식 회귀 방지: insights 프롬프트에 코드 본문 미유출, TODO 문자열/산문/코드 음성 케이스.

> 검증: `pip install -e .[dev]` 후 `pytest` → 36 passed. `python -m codeheat.cli scan|own|insights` 동작 확인.

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
│   └── insights.py        # 완료: 3단계 LLM 인사이트
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
2. TODO 정규식: 단어 경계(`\b`)만으론 부족. docstring 산문/정규식 정의/인자명/코드 문장까지 오탐됨. **주석 시작 토큰 뒤** 또는 **라인 시작 `TODO:`(콜론 필수)** 앵커를 둬야 정밀해짐. 라인-시작 분기에 콜론을 안 걸면 `todo.age = ...` 같은 코드 문장이 오탐됨(루프 변수). 검증은 `tests/test_static_scan.py`의 prose/code 음성 케이스 참고.

### TODO 탐지 (1단계) — 토큰 기반으로 정밀화 완료
- Pygments로 토큰화 → Comment 토큰만 추출 → 그 안에서 TODO_PATTERN(주석시작 직후 마커 + `\b`)로 확인.
- 산문/식별자/정규식정의/코드문장은 물론 **문자열 리터럴 속 가짜 주석(`s = "# TODO"`)까지 배제**. 다언어 대응(.py/.js/...).
- Pygments 미설치·렉서 미존재 시 라인-앵커 정규식 폴백(`_iter_comment_lines`). 폴백도 `_mask_strings`로 한 줄짜리 문자열 리터럴을 마스킹해 가짜 주석을 거름. 잔여 한계는 폴백 경로의 *여러 줄* 문자열뿐.
- `_iter_comment_lines`는 (라인번호, 매칭용텍스트, 표시용텍스트) 3-튜플을 산출. 폴백에선 매칭=마스킹본, 표시=원본 라인이라 리포트 텍스트가 깨지지 않음.
- 셀프 스캔 0 오탐 확인. 검증: `tests/test_static_scan.py` (문자열/산문/코드 음성 + 주석/다언어/폴백+마스킹/pygments미설치 양성, `_mask_strings` 단위).
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

## 완료된 것 — 3단계 (LLM 인사이트 `insights.py`)

목표 달성: 1+2단계 JSON을 묶어 LLM에 넘기고 리팩토링 우선순위 + "누구에게 무엇을 물어볼지"를 받는다.
- `load_and_merge()`: smell_report(복잡도순) + ownership_report를 파일 기준 병합. 복잡도 우선순위 순서 보존. 파일명 basename 폴백 매칭.
- `build_user_prompt()`: 병합 메타데이터만 직렬화. **코드 본문 절대 미포함** — 모델 `to_dict`가 메타데이터만 담는 구조라 자연히 보장됨.
- 백엔드 2종 (HANDOFF의 "Ollama 또는 API"):
  - `ollama`: 로컬·무료. stdlib urllib만 사용(추가 의존성 0). `format:"json"` 모드.
  - `anthropic`: 공식 SDK. `claude-opus-4-8` + adaptive thinking + `output_config.format`(json_schema)로 스키마 엄격 강제. `pip install codeheat[llm]` 필요.
- CLI: `codeheat insights smell_report.json [--ownership-report ...] [--backend ollama|anthropic] [--model ...] [--top-k 10] [--dry-run]`
- 출력: `insights_report.json` (파일별 risk/reason/ask_who/ask_what + summary)
- 동작 확인: 이 레포에서 `scan → own → insights`(ollama llama3.1:8b 실호출 + `--dry-run`) 검증 완료

### 작업 중 발견/해결한 이슈 (반복 방지용 메모)
1. Ollama `format:"json"`은 **유효 JSON만 강제하고 스키마는 강제 안 함** — 8b 모델이 risk를 숫자로, summary를 객체로 주기도 함. `_normalize_risk()` + summary 문자열 강제로 방어. anthropic 백엔드는 `output_config.format`로 스키마까지 엄격 강제되니 정규화 불필요(하지만 동일 코드 경로라 무해).
2. `claude-api` 스킬 기준 opus-4-8은 `budget_tokens` 금지(400). `thinking={"type":"adaptive"}` 사용.
3. anthropic SDK는 지연 import(`_generate_anthropic` 내부) — ollama 경로만 쓰면 anthropic 미설치여도 패키지 동작.

## 다음 할 일 (우선순위 순)

### 4단계 — 출력 레이어
- 4-1: Next.js + D3 트리맵 대시보드
- 4-2: GitHub Action PR 봇 ("이 PR로 checkout.py 히트맵 온도 상승")
- 4-3: VS Code 확장 (가장 나중, 반응 보고 결정)

---

## 클로드 코드에서 시작하는 법
1. 이 `codeheat/` 폴더를 작업 디렉토리로 열기
2. `pip install -e .` 로 설치
3. 다음 작업은 4단계 출력 레이어(대시보드/PR 봇)부터. 1~3단계는 모두 구현·검증 완료.
