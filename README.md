# CodeHeat 🔥

코드 복잡도와 git 히스토리를 분석해서 **"어떤 파일을 먼저 리팩토링해야 하고, 누구에게 물어보면 좋을지"** 를 알려주는 오픈소스 CLI 툴.

핵심 철학: *"누가 이 코드를 쌌나(blame)"* 가 아니라 *"누가 이 코드를 가장 잘 해결할 수 있나(매칭)"*.

## 전체 파이프라인

1. **정적 분석** (구현됨) — 복잡도 + TODO/FIXME + 나이
2. **오너십 분석** (구현됨) — 복잡도 급증 시점 기여자 매칭
3. **LLM 인사이트** (구현됨) — 숫자/메타데이터만으로 우선순위·질문 대상 제안
4. 출력 레이어 — 대시보드 / PR 봇 / VS Code 확장

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

- **TODO 탐지가 정규식 기반**이라 docstring/주석에 설명용으로 쓴 "TODO" 단어도 잡힐 수 있다. (단어 경계 `\b`로 변수명 오탐은 제거했지만 의미 판별은 못 함)
- **`duplication_ratio`는 미구현** (기본값 0.0). 2단계에서 jscpd 등 연동 예정.
- **`git log -S`(pickaxe)는 TODO 텍스트 앞 40자만 사용**한다. 문구가 너무 일반적이면 오매칭 가능. git 미설치/타임아웃/미추적 파일이면 `age_days`는 `null`.
- `exclude`는 디렉토리 단위(node_modules/.git/venv/.venv)만 고정 제외.

## 라이선스

MIT
