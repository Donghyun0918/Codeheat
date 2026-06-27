"""3단계 LLM 인사이트 레이어.

1+2단계 JSON(복잡도/TODO + 오너십)을 묶어 LLM에 넘기고, "어떤 파일을 먼저
리팩토링해야 하고, 누구에게 무엇을 물어보면 좋을지"를 받아온다.

핵심 제약 (반복 강조):
- LLM에는 **숫자/메타데이터만** 넘긴다. 코드 본문은 절대 넘기지 않는다.
  1+2단계 리포트가 이미 메타데이터만 담고 있으므로(`to_dict`), 그 JSON에서
  추린 값만 프롬프트에 들어간다. 파일 *경로*는 식별용으로 넘기지만 *내용*은 안 넘긴다.

백엔드 두 가지 (HANDOFF의 "Ollama 또는 API 선택"):
- ollama: 로컬·무료. 추가 의존성 없이 stdlib urllib로 HTTP 호출.
- anthropic: 공식 SDK 사용. `pip install codeheat[llm]` 또는 `pip install anthropic` 필요.
  기본 모델 claude-opus-4-8 + adaptive thinking.

`--dry-run`이면 LLM 호출 없이 조립된 프롬프트만 출력한다(네트워크/키/의존성 불필요).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .models import RefactorInsight

# LLM이 따라야 할 출력 스키마. 두 백엔드 모두 이 모양의 JSON을 돌려주도록 강제한다.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "priorities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "risk": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                    "ask_who": {"type": "string"},
                    "ask_what": {"type": "string"},
                },
                "required": ["file", "risk", "reason", "ask_who", "ask_what"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["priorities", "summary"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "너는 코드베이스 리팩토링 우선순위를 잡아주는 도구다. "
    "철학: 'who wrote it(blame)'가 아니라 'who can fix it(매칭)'. "
    "단순 최다 수정자가 아니라, 복잡도가 급증한 시점에 커밋해 도메인 지식 점수가 "
    "높은 사람에게 물어보라고 안내한다.\n"
    "입력은 파일별 정적 분석(복잡도/TODO 나이)과 오너십 점수 메타데이터다. "
    "코드 본문은 주어지지 않으니, 숫자가 말해주는 것 이상으로 코드 내용을 지어내지 마라.\n"
    "지정된 JSON 스키마(priorities[], summary)로만 답한다. "
    "priorities는 위험도 내림차순으로 정렬하고, ask_what에는 그 파일에서 막혔을 때 "
    "오너에게 던질 구체적이고 실행 가능한 질문을 적는다."
)

# 기본값
DEFAULT_OLLAMA_MODEL = "llama3.1"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
_HTTP_TIMEOUT = 120  # seconds


def load_and_merge(smell_path: str, ownership_path: str | None) -> list[dict]:
    """1단계(+2단계) 리포트를 파일 기준으로 병합.

    smell_report는 이미 복잡도 내림차순이므로 그 순서를 우선순위로 보존한다.
    ownership_report가 있으면 같은 파일의 top_contributors를 붙인다.
    """
    with open(smell_path, "r", encoding="utf-8") as fh:
        smell = json.load(fh)

    own_by_file: dict[str, dict] = {}
    if ownership_path:
        with open(ownership_path, "r", encoding="utf-8") as fh:
            own = json.load(fh)
        own_by_file = {f["file"]: f for f in own.get("files", [])}

    merged: list[dict] = []
    for f in smell.get("files", []):
        entry = {
            "file": f["file"],
            "complexity": f.get("complexity"),
            "avg_complexity": f.get("avg_complexity"),
            "function_count": f.get("function_count"),
            "loc": f.get("loc"),
            "todo_count": len(f.get("todos", [])),
            "oldest_todo_days": f.get("oldest_todo_days"),
            "duplication_ratio": f.get("duplication_ratio", 0.0),
        }
        # 파일명을 정규화해 매칭 (smell은 절대/상대 섞일 수 있고 own은 상대경로).
        own = own_by_file.get(f["file"]) or own_by_file.get(
            os.path.basename(f["file"])
        )
        if own:
            entry["top_contributors"] = [
                {
                    "name": c["name"],
                    "score": c["score"],
                    "commit_count": c["commit_count"],
                    "last_commit_days": c.get("last_commit_days"),
                }
                for c in own.get("top_contributors", [])
            ]
            entry["total_commits"] = own.get("total_commits")
        else:
            entry["top_contributors"] = []
        merged.append(entry)
    return merged


def build_user_prompt(merged: list[dict], top_k: int) -> str:
    """병합된 메타데이터를 LLM 입력 텍스트로 직렬화.

    top_k개 파일만 추려서(이미 복잡도순) 토큰을 아낀다. 코드 본문은 들어가지 않는다.
    """
    facts = merged[:top_k]
    return (
        f"다음은 분석 대상 상위 {len(facts)}개 파일의 메타데이터다 "
        "(복잡도 내림차순, 코드 본문 없음).\n\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
        "각 파일에 대해 리팩토링 위험도(risk)와 이유(reason), 누구에게(ask_who) "
        "무엇을(ask_what) 물어볼지 판단해 JSON으로 답하라.\n"
        "- risk: 반드시 \"high\", \"medium\", \"low\" 중 하나의 문자열 (숫자 금지).\n"
        "- ask_who: top_contributors 중 score가 가장 높은 사람 이름. "
        "비어 있으면 '오너 불명(히스토리 부족)'.\n"
        "- summary: 전체를 요약하는 한국어 한두 문장 (객체 아님, 문자열)."
    )


def _generate_ollama(
    system: str, user: str, model: str, host: str
) -> str:
    """Ollama 로컬 서버 호출. stdlib만 사용. JSON 모드 강제."""
    body = json.dumps(
        {
            "model": model,
            "system": system,
            "prompt": user,
            "stream": False,
            "format": "json",  # Ollama JSON 모드
            "options": {"temperature": 0.2},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama 호출 실패 ({host}). 서버가 켜져 있고 모델 '{model}'이 "
            f"받아져 있는지 확인하세요 (ollama pull {model}). 원인: {e}"
        ) from e
    return payload.get("response", "")


def _generate_anthropic(system: str, user: str, model: str) -> str:
    """Anthropic 공식 SDK 호출. opus-4-8 + adaptive thinking + 구조화 출력."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "anthropic 패키지가 없습니다. `pip install codeheat[llm]` 또는 "
            "`pip install anthropic` 후 ANTHROPIC_API_KEY를 설정하세요."
        ) from e

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수에서 키 로드
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": user}],
    )
    # output_config.format이 첫 text 블록을 유효한 JSON으로 보장한다.
    return next((b.text for b in response.content if b.type == "text"), "")


_RISK_LEVELS = {"high", "medium", "low"}


def _normalize_risk(value) -> str:
    """모델이 risk를 숫자/대문자/잡문자로 줘도 enum으로 정규화."""
    s = str(value).strip().lower()
    if s in _RISK_LEVELS:
        return s
    # 숫자로 준 경우(복잡도 등): 대략적 구간 매핑.
    try:
        n = float(s)
        return "high" if n >= 8 else "medium" if n >= 4 else "low"
    except ValueError:
        return "medium"


def _parse_response(raw: str) -> dict:
    """LLM 원문에서 JSON 추출. 앞뒤 잡텍스트가 섞여 있어도 최선으로 회수."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def generate_insights(
    smell_path: str,
    ownership_path: str | None = None,
    backend: str = "ollama",
    model: str | None = None,
    top_k: int = 10,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    dry_run: bool = False,
) -> dict:
    """3단계 인사이트 생성 오케스트레이터.

    반환: {"backend", "model", "insights": [...], "summary": ..., "raw": ...}.
    dry_run이면 LLM 호출 없이 {"prompt": ...}만 반환한다.
    """
    merged = load_and_merge(smell_path, ownership_path)
    user_prompt = build_user_prompt(merged, top_k)

    if dry_run:
        return {"backend": backend, "dry_run": True, "prompt": user_prompt}

    if backend == "ollama":
        model = model or DEFAULT_OLLAMA_MODEL
        raw = _generate_ollama(SYSTEM_PROMPT, user_prompt, model, ollama_host)
    elif backend == "anthropic":
        model = model or DEFAULT_ANTHROPIC_MODEL
        raw = _generate_anthropic(SYSTEM_PROMPT, user_prompt, model)
    else:
        raise ValueError(f"알 수 없는 backend: {backend} (ollama|anthropic)")

    parsed = _parse_response(raw)
    insights = [
        RefactorInsight(
            file=p.get("file", "?"),
            risk=_normalize_risk(p.get("risk", "medium")),
            reason=str(p.get("reason", "")),
            ask_who=str(p.get("ask_who", "")),
            ask_what=str(p.get("ask_what", "")),
        )
        for p in parsed.get("priorities", [])
    ]
    # 일부 모델은 summary를 객체로 줄 수 있으니 문자열로 강제.
    summary = parsed.get("summary", "")
    if not isinstance(summary, str):
        summary = json.dumps(summary, ensure_ascii=False)
    return {
        "backend": backend,
        "model": model,
        "summary": summary,
        "insights": [i.to_dict() for i in insights],
        "raw": raw,
    }
