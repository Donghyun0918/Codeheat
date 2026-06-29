# CodeHeat — 작업 현황 (클로드 코드 인계용)

## 프로젝트 한 줄 요약
코드 복잡도 + git 히스토리를 분석해서 "어떤 파일을 먼저 리팩토링해야 하고, 누구에게 물어보면 좋을지"를 알려주는 오픈소스 CLI 툴. 핵심 철학: **"누가 쌌나"(blame)가 아니라 "누가 해결할 수 있나"(매칭)**.

전체 파이프라인 설계는 `code-smell-radar-pipeline.md` 참고.

---

## 현재 상태 요약 (2026-06-30 기준)

### 커밋된 것 (git 반영 완료, master, 미푸시)
- 1단계 정적 분석 · 2단계 오너십 · 3단계 LLM 인사이트 · TODO 토큰 정밀화 · pytest 스위트
- `fbb1f00 feat: 오너십 기여자 식별을 이메일 키로 정규화` (이메일 합산/`--no-merges`/메모리 분석/churn==0 스킵)
- `bb77b4f feat: PR 복잡도 온도 봇(4단계 GitHub Action)` (`codeheat/ci.py` + 워크플로 + 테스트)
- `c196bbe feat: D3 트리맵 대시보드(4단계 4-1)` (`dashboard/`, Next.js+React+D3, 정적 export)

### 미커밋 작업 (working tree, 사용자 지시로 커밋 보류 중)
- **4단계 4-3 VS Code 확장 신설** — `vscode-extension/` (사이드바 히트맵 트리뷰 + 상태바), `README.md`/`HANDOFF.md` 갱신.
  - 리포트 JSON 재사용, 워크스페이스 스캔 명령. 자세한 내용은 아래 "완료된 것 — 4단계 4-3" 절.

> 검증: 백엔드 `pytest` 51 passed. 대시보드 `npm run build` 통과. 확장 `cd vscode-extension && npm install && npm run compile` 통과(타입에러 0) + `reports.js` 샘플 단위검증. CLI 동작 확인.

> **4단계(출력 레이어) 4-1·4-2·4-3 전부 구현 완료.** 남은 것은 백로그(함수 단위 매칭, duplication_ratio, insights 풀데모)뿐.

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
- `git log --no-merges --follow --numstat --format=%H|%aN|%aE|%at -- <file>` 한 번으로 메타데이터+churn 수집. `%aN`/`%aE`는 `.mailmap` 반영, `--no-merges`로 머지 제외.
- 핵심 정의대로 단순 최다 수정자가 아니라 **복잡도가 급증한 시점에 커밋한 사람**에 가중치
- **동일인 합산은 이메일(`%aE`) 키 기준**. 표시 이름은 그 이메일의 가장 최근 커밋 이름.
- 점수 = Σ(최근성 가중치 × 변화량 가중치)
  - 최근성: 반감기 1년 지수 감쇠 (`_recency_weight`)
  - 변화량: `git show <commit>:<path>`를 `lizard.analyze_file.analyze_source_code`로 **메모리 분석**(임시파일 IO 없음)한 max CCN 델타. churn==0이면 git show 생략. 실패 시 `log1p(churn)` 폴백
- CLI: `codeheat own <repo>` (`--from-report`, `--top`, `--limit`, `--churn-only`)
- 출력: `ownership_report.json` (파일별 top_contributors 리스트)
- 동작 확인: 이 레포에 `scan → own` 파이프라인으로 검증 완료

### 작업 중 발견/해결한 이슈 (반복 방지용 메모)
1. `git log --numstat`은 최신→과거 순으로 나오므로, 복잡도 델타를 시간순으로 누적하려면 `reverse()` 필요
2. `--from-report` 입력은 1단계가 이미 복잡도 내림차순 정렬해둔 순서를 그대로 보존(우선순위 승계)
3. LLM 레이어 제약대로 `FileOwnershipReport`도 이름/점수/메타데이터만 담고 코드 본문은 안 넘김
4. **헤더 파싱은 고정 위치 기준**: 이름에 `|`가 들어갈 수 있으니 `hash=처음`, `email=끝-1`, `ts=끝`으로 자르고 가운데를 이름으로 되붙인다.
5. 남은 한계: 복잡도 델타가 파일 단위 max CCN이라 그 작성자가 만진 함수가 아니어도 가중됨(함수 단위 매칭은 향후). git show는 커밋마다 1회라 초대형 히스토리는 여전히 느릴 수 있음(`--churn-only`/`--limit`로 완화).

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

## 완료된 것 — 4단계 4-2 (GitHub Action PR 봇 `ci.py`)

목표 달성: PR이 건드린 코드 파일들의 "히트맵 온도(max CCN)"가 base→head로 얼마나 올랐는지 표로 만들어 PR에 코멘트로 단다("이 PR로 checkout.py 온도 상승"). 온도 오른 파일 옆에 오너십 top 기여자를 "막히면 물어볼 사람"으로 함께 표시 — blame 아니라 매칭.
- `get_changed_files()`: `git diff --name-only --diff-filter=d base...head`(three-dot, 삭제 제외)로 변경 파일 수집.
- 온도/델타: **`ownership._max_ccn_at`를 그대로 재사용**해 base/head 각 시점 파일의 max CCN을 구해 뺀다(임시파일 IO 없음, 1·2단계와 같은 복잡도 정의). 비코드(.md/.json 등)는 `lizard.get_reader_for`로 사전 필터 → 오너십/git show 호출도 절약.
- 오너: `build_ownership_reports(..., top_n=1)` 재사용, `os.path.normpath(rel)` 키로 매칭.
- 코멘트 게시: **stdlib urllib만** (ollama 백엔드와 동일 정책, 추가 의존성 0). 숨김 마커(`<!-- codeheat:pr-comment -->`)로 기존 코멘트를 찾아 **upsert**(push마다 중복 코멘트 방지).
- PR 컨텍스트: `GITHUB_EVENT_PATH` 페이로드 + `GITHUB_*` 환경변수에서 base/head/PR번호/repo 자동 해석. CLI 인자가 우선.
- CLI: `python -m codeheat.ci pr-comment [--repo --base --head --pr --repo-slug --churn-only --output --no-post]`. `--no-post`로 로컬 본문 확인.
- 워크플로: `.github/workflows/codeheat.yml` (pull_request 트리거, `fetch-depth: 0`, `pull-requests: write`).
- 검증: `tests/test_ci.py` 12개(변경파일 파싱/비코드필터/델타·영향도/코멘트 마크다운/조립·오너매칭/upsert PATCH·POST/이벤트 파싱). 이 레포에서 `--base HEAD~2 --head HEAD --no-post` 스모크 OK. 전체 51 passed.

### 작업 중 발견/해결한 이슈 (반복 방지용 메모)
1. lizard는 **미지원 확장자에 예외가 아니라 빈 결과(→max CCN 0)** 를 준다. `_max_ccn_at`의 None 가드만으론 .md/.toml이 온도 0으로 표에 새어들어옴 → `lizard.get_reader_for(path) is None`으로 사전 필터해야 한다.
2. PR diff는 반드시 `base...head`(three-dot). two-dot이면 base 브랜치의 무관한 커밋까지 끌고 온다. 정확한 델타엔 체크아웃 `fetch-depth: 0` 필수.
3. 코멘트 upsert는 마커 문자열을 본문 끝에 심고 issues 코멘트 목록에서 검색 → 있으면 PATCH, 없으면 POST. per_page=100 페이지네이션.

## 완료된 것 — 4단계 4-1 (D3 트리맵 대시보드 `dashboard/`)

목표 달성: CLI 리포트(JSON)를 트리맵 히트맵으로 시각화. 면적=LOC, 색=복잡도 온도(max CCN). 파일 클릭 시 복잡도·TODO·오너십·LLM 인사이트를 옆 패널에 표시.
- 스택: Next.js 15(App Router) + React 19 + TS. D3는 `d3-hierarchy`(트리맵 레이아웃 계산)만, 렌더는 React가 SVG로(D3가 DOM 직접 조작 안 함). 의존성 최소(설치 29패키지).
- **백엔드 없음**: `output: "export"` 정적 빌드. 데이터는 브라우저에서만 처리(코드/리포트 서버 미전송) — LLM 미전달 철학과 일관.
- 데이터 입력: ① 번들 샘플(이 레포 scan+own 결과, `app/sample-data/`) 열자마자 표시 ② 드롭존 업로드(smell/ownership/insights, 모양으로 자동 판별 `classifyReport`). 병합은 CLI `load_and_merge`와 같은 규칙(경로→basename 폴백).
- 구조: `lib/`(types·merge·treemap 순수로직), `components/`(Treemap·FileDetail·UploadDropzone), `app/`(layout·page·globals.css).
- 검증: `npm run build` 타입체크+정적 export 통과. 트리맵 레이아웃을 실제 샘플로 검증(12파일→12 leaf, 음수면적 0, 오너 12/12 매칭). `out/` 정적 서빙 200.

### 작업 중 발견/해결한 이슈 (반복 방지용 메모)
1. 정적 export(`output: "export"`)라 샘플 JSON은 `app/sample-data/`에서 **직접 import**(resolveJsonModule). public/fetch 대신 import라 빌드에 번들되고 정적 배포에서 동작.
2. D3 treemap leaf 면적은 LOC. `__init__.py`처럼 LOC=0이면 면적 0이 되니 `Math.max(loc,1)`로 최소 슬라이버 보장.
3. 첫 업로드 시 샘플과 섞이지 않게, `usingSample` 플래그로 첫 패치 때 샘플을 비우고 업로드분으로 시작.
4. 트리맵은 클라이언트 측정(ResizeObserver) 후 그려지므로, 정적 HTML엔 rect가 없다(JS 실행 후 렌더). 빌드 검증은 타입체크+레이아웃 단위검증으로 갈음(헤드리스 브라우저 미설치).

## 완료된 것 — 4단계 4-3 (VS Code 확장 `vscode-extension/`)

목표 달성: 복잡도 히트맵을 에디터 사이드바·상태바로. (사용자가 인터랙션 방식으로 "사이드바 트리뷰 + 상태바" 선택.)
- **사이드바 트리뷰**(`codeheat.heatmap`, 활동막대 🔥): 파일을 복잡도 내림차순으로. 핫파일=빨간 불꽃(`ThemeIcon('flame')` + `charts.red/orange/yellow/green` 내장색). 클릭=`vscode.open`, 호버=오너/위험도/TODO MarkdownString.
- **상태바**: 활성 파일의 `🔥 CCN N · 오너`. 리포트에 없으면 숨김. 클릭=`codeheat.heatmap.focus`.
- 데이터: 워크스페이스 루트의 `smell/ownership/insights_report.json`(경로 설정 가능)을 읽어 병합(경로→basename 폴백, CLI `load_and_merge`와 동일). 없으면 `viewsWelcome`에서 스캔 유도.
- 명령: `codeheat.runScan`(CLI `scan`+`own`을 child_process로 실행해 리포트 생성), `codeheat.refresh`(디스크 재로드). 설정 `codeheat.cliCommand`로 CLI 교체(예: `python -m codeheat.cli`).
- 구조: `src/extension.ts`(activate/wire), `reports.ts`(로드+병합, vscode 비의존 순수), `heatProvider.ts`(TreeDataProvider), `status.ts`, `scan.ts`. `tsc -p ./` → `out/`.
- 검증: `npm run compile` 타입에러 0. `reports.js`(vscode 비의존)를 샘플로 단위검증(12파일, 복잡도 내림차순, 오너 12/12, 경로 정규화). 확장 호스트 실행(F5)은 환경상 미실행 — `vscode` 모듈은 런타임 주입이라 호스트 밖 require 불가.

### 작업 중 발견/해결한 이슈 (반복 방지용 메모)
1. `vscode` 모듈은 npm이 아니라 VS Code 런타임이 주입한다. `out/extension.js`를 node로 require하면 "Cannot find module 'vscode'" — 정상. 검증은 vscode 비의존 로직(`reports.ts`)을 분리해 단위테스트 + `tsc` 타입체크로 갈음.
2. 리포트 `file` 경로가 절대/상대 섞일 수 있어, 로드 시 워크스페이스 루트 기준 `rel`(슬래시 정규화)로 통일해 트리/상태바/열기 매칭에 쓴다.
3. 트리 아이템 색은 커스텀 색 등록 없이 내장 `charts.*` ThemeColor로. 상태바 클릭 점프는 `{viewId}.focus`(VS Code 자동 제공).

## 다음 할 일

### 백로그
- insights 업로드까지 합친 대시보드 풀 데모(현재 샘플엔 insights 미포함; LLM 호출 필요해 번들 제외).
- 함수 단위 복잡도 매칭(2단계/PR봇 공통 한계), `duplication_ratio` 구현(jscpd).

---

## 클로드 코드에서 시작하는 법
1. 이 `codeheat/` 폴더를 작업 디렉토리로 열기
2. `pip install -e .` 로 설치
3. 다음 작업은 4단계 출력 레이어(대시보드/PR 봇)부터. 1~3단계는 모두 구현·검증 완료.
