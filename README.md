# CodeHeat 🔥

코드 복잡도와 git 히스토리를 분석해서 **"어떤 파일을 먼저 리팩토링해야 하고, 누구에게 물어보면 좋을지"** 를 알려주는 오픈소스 CLI 툴.

핵심 철학: *"누가 이 코드를 쌌나(blame)"* 가 아니라 *"누가 이 코드를 가장 잘 해결할 수 있나(매칭)"*.

## 전체 파이프라인

1. **정적 분석** (구현됨) — 복잡도 + TODO/FIXME + 나이
2. **오너십 분석** (구현됨) — 복잡도 급증 시점 기여자 매칭
3. **LLM 인사이트** (구현됨) — 숫자/메타데이터만으로 우선순위·질문 대상 제안
4. 출력 레이어 — **GitHub Action PR 봇 (구현됨)** / 대시보드 / VS Code 확장

> ⚠️ LLM 레이어에는 **코드 본문을 절대 넘기지 않고 숫자/메타데이터만** 전달한다. 1단계 JSON 출력도 이를 염두에 둔 구조다.

## 설치

```bash
pip install -e .
```

`lizard`(다언어 복잡도 분석)에 의존하며, TODO 나이 계산에는 `git`이 필요하다.

## 사용법

```bash
# 기본 스캔 (복잡도 + TODO + TODO 나이)
codeheat scan <repo_path>

# 출력 경로 지정
codeheat scan <repo_path> --output report.json

# git log 기반 TODO 나이 계산 생략 (대규모 레포에서 속도 우선)
codeheat scan <repo_path> --no-todo-age
```

모듈로 직접 실행도 가능:

```bash
python -m codeheat.cli scan <repo_path>
```

### 오너십 분석 (`own`)

파일별로 "복잡도가 급증한 시점에 커밋한 사람"에게 가중치를 줘서 도메인 지식 점수가 높은 기여자를 뽑는다. blame이 아니라 매칭이다.

```bash
# 1단계 리포트의 파일들만 분석 (복잡도 우선순위 그대로 이어받음)
codeheat own <repo_path> --from-report smell_report.json

# git 추적 파일 전체 (--from-report 없이), 상위 N명, 파일 수 상한
codeheat own <repo_path> --top 2 --limit 30

# 복잡도 델타 계산 생략, churn(변경 라인)만으로 가중 (속도 우선)
codeheat own <repo_path> --churn-only
```

점수 = Σ(최근성 가중치 × 변화량 가중치). 최근성은 반감기 1년으로 감쇠하고, 변화량은 그 커밋이 끌어올린 복잡도 델타(불가 시 churn 폴백)로 잰다.

### LLM 인사이트 (`insights`)

1+2단계 JSON을 묶어 LLM에 넘기고 리팩토링 우선순위와 "누구에게 무엇을 물어볼지"를 받는다. **코드 본문은 절대 안 넘기고 숫자/메타데이터만** 전달한다.

```bash
# 무료 로컬 백엔드 (Ollama). 먼저 `ollama pull llama3.1` 필요
codeheat insights smell_report.json --ownership-report ownership_report.json

# 모델/상위 파일 수/서버 주소 지정
codeheat insights smell_report.json --backend ollama --model llama3.1:8b --top-k 10

# Anthropic API 백엔드 (pip install codeheat[llm], ANTHROPIC_API_KEY 필요)
codeheat insights smell_report.json --backend anthropic

# LLM 호출 없이 넘어갈 프롬프트만 확인 (키/네트워크 불필요)
codeheat insights smell_report.json --dry-run
```

`ollama` 백엔드는 stdlib만 쓰므로 추가 설치가 없고, `anthropic` 백엔드는 `claude-opus-4-8` + 구조화 출력으로 스키마를 엄격 강제한다. 출력은 `insights_report.json`(파일별 risk/reason/ask_who/ask_what + 전체 summary).

### GitHub Action PR 봇 (`python -m codeheat.ci pr-comment`)

PR이 건드린 코드 파일들의 **히트맵 온도(max CCN)** 가 base→head로 얼마나 변했는지 표로 만들어 PR에 코멘트로 단다. 온도가 오른 파일 옆에는 "막히면 물어볼 사람"(오너십 top 기여자)을 함께 보여준다 — blame이 아니라 매칭.

```bash
# 로컬에서 두 ref를 비교해 코멘트 본문만 확인 (게시 안 함)
python -m codeheat.ci pr-comment --base main --head HEAD --no-post

# 오너십 점수를 churn 기준으로(복잡도 델타 생략) 빠르게
python -m codeheat.ci pr-comment --base main --head HEAD --no-post --churn-only
```

GitHub Actions에서는 `.github/workflows/codeheat.yml`이 `pull_request` 이벤트마다 실행한다. PR 컨텍스트(base/head SHA·PR 번호·repo)는 이벤트 페이로드와 `GITHUB_*` 환경변수에서 자동으로 읽고, `GITHUB_TOKEN`으로 코멘트를 단다. 같은 PR에 push가 쌓여도 **숨김 마커로 기존 코멘트를 찾아 갱신(upsert)** 하므로 코멘트가 중복되지 않는다. 코멘트 게시는 stdlib `urllib`만 쓴다(추가 의존성 0).

```yaml
# .github/workflows/codeheat.yml (요약)
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
  pull-requests: write
# checkout은 fetch-depth: 0 (base...head 델타 계산에 전체 히스토리 필요)
```

### 출력 (`smell_report.json`)

복잡도(파일 내 최대 CCN) 내림차순 정렬:

```json
{
  "repo_path": ".",
  "file_count": 3,
  "files": [
    {
      "file": "codeheat/static_scan.py",
      "complexity": 6,
      "avg_complexity": 2.5,
      "function_count": 7,
      "loc": 90,
      "todos": [{ "line": 42, "text": "TODO: ...", "age_days": 3 }],
      "duplication_ratio": 0.0,
      "oldest_todo_days": 3
    }
  ]
}
```

## 알려진 한계 (1단계)

- **TODO 탐지는 토큰 기반**이다. Pygments로 소스를 토큰화해 **진짜 주석(Comment 토큰)만** 추린 뒤, 그 안에서 마커 형태(주석 시작 직후의 `TODO`/`FIXME`, 단어 경계 `\b`)를 확인한다. 덕분에 docstring 산문, 정규식 정의, 인자명, 코드 문장은 물론 **코드 문자열 리터럴 속 가짜 주석(`s = "# TODO"`)까지 배제**된다. 다언어(`.py`/`.js`/`.c` 등) 주석 문법을 각 언어 렉서가 처리한다. Pygments가 없거나 렉서를 못 찾으면 라인-앵커 정규식 폴백으로 강등되는데, **이 폴백도 한 줄 안의 문자열 리터럴을 마스킹**해 가짜 주석을 거른다. 폴백의 잔여 한계는 *여러 줄에 걸친 문자열* 안의 가짜 주석뿐이며, 주류 언어는 Pygments 경로라 해당되지 않는다.
- **`duplication_ratio`는 미구현** (기본값 0.0). 2단계에서 jscpd 등 연동 예정.
- **`git log -S`(pickaxe)는 TODO 텍스트 앞 40자만 사용**한다. 문구가 너무 일반적이면 오매칭 가능. git 미설치/타임아웃/미추적 파일이면 `age_days`는 `null`.
- `exclude`는 디렉토리 단위(node_modules/.git/venv/.venv)만 고정 제외.

## 알려진 한계 (2단계 오너십)

- **기여자는 이메일(`%aE`) 기준으로 합산**한다. `%aN`/`%aE`는 `.mailmap`을 반영하므로, 한 사람이 여러 이름/메일로 쪼개지는 걸 막으려면 레포 루트에 `.mailmap`을 두면 된다. 표시 이름은 그 이메일의 가장 최근 커밋 이름을 쓴다.
- **머지 커밋은 `--no-merges`로 제외**한다(churn/점수 왜곡 방지).
- **복잡도 델타는 파일 단위 max CCN 기준**이다. 그 커밋이 실제로 건드린 함수가 아니어도 파일 전체 복잡도가 오르면 가중된다. (함수 단위 매칭은 향후 과제)
- 델타 계산은 커밋마다 `git show`를 1회 한다. 임시파일 IO는 없앴지만(`analyze_source_code`로 메모리 분석), 커밋이 매우 많은 파일은 여전히 느릴 수 있다 — `--churn-only`로 끄거나 `--limit`으로 파일 수를 줄이면 빠르다.

## 알려진 한계 (4단계 PR 봇)

- **온도는 파일 단위 max CCN**이다(1단계 `complexity`와 같은 정의). 함수 단위 증감이 아니라 파일 최대치라, 함수가 쪼개져도 다른 함수가 더 복잡하면 온도가 안 내려갈 수 있다.
- **비코드 파일(.md/.json/.toml 등)은 표에서 제외**한다(`lizard.get_reader_for`가 인식하는 언어만). 복잡도 개념이 없는 파일을 노이즈로 올리지 않기 위해서다.
- **base가 없으면(=완전한 신규 파일) 델타 대신 "🆕 신규"** 로 표시하고, 그 파일의 전체 복잡도를 영향도로 본다.
- `base...head`(three-dot) diff라 base 브랜치에 쌓인 무관한 커밋은 끌고 오지 않는다. 단, 정확한 델타를 위해 Action 체크아웃은 `fetch-depth: 0`이어야 한다.

## 라이선스

MIT
