"""insights.py: 병합·프롬프트 안전성·파싱·정규화·백엔드 경로 검증.

핵심 불변식: LLM 프롬프트에는 코드 본문이 절대 들어가지 않는다(메타데이터만).
"""

import json

import pytest

from codeheat import insights
from codeheat.insights import (
    _normalize_risk,
    _parse_response,
    build_user_prompt,
    generate_insights,
    load_and_merge,
)


def _write_reports(tmp_path):
    smell = {
        "repo_path": ".",
        "file_count": 2,
        "files": [
            {
                "file": "pkg/big.py",
                "complexity": 12,
                "avg_complexity": 5.0,
                "function_count": 7,
                "loc": 140,
                "todos": [{"line": 3, "text": "TODO refactor", "age_days": 30}],
                "duplication_ratio": 0.0,
                "oldest_todo_days": 30,
            },
            {
                "file": "pkg/small.py",
                "complexity": 3,
                "avg_complexity": 1.5,
                "function_count": 2,
                "loc": 20,
                "todos": [],
                "duplication_ratio": 0.0,
                "oldest_todo_days": None,
            },
        ],
    }
    ownership = {
        "repo_path": ".",
        "files": [
            {
                "file": "pkg/big.py",
                "total_commits": 5,
                "top_contributors": [
                    {"name": "Alice", "score": 9.1, "commit_count": 3, "last_commit_days": 2}
                ],
            }
        ],
    }
    sp = tmp_path / "smell.json"
    op = tmp_path / "own.json"
    sp.write_text(json.dumps(smell), encoding="utf-8")
    op.write_text(json.dumps(ownership), encoding="utf-8")
    return str(sp), str(op)


def test_load_and_merge_attaches_owners(tmp_path):
    sp, op = _write_reports(tmp_path)
    merged = load_and_merge(sp, op)
    assert len(merged) == 2
    big = merged[0]
    assert big["file"] == "pkg/big.py"
    assert big["todo_count"] == 1
    assert big["oldest_todo_days"] == 30
    assert big["top_contributors"][0]["name"] == "Alice"
    # 오너십 없는 파일은 빈 리스트
    assert merged[1]["top_contributors"] == []


def test_load_and_merge_without_ownership(tmp_path):
    sp, _ = _write_reports(tmp_path)
    merged = load_and_merge(sp, None)
    assert all(m["top_contributors"] == [] for m in merged)


def test_prompt_contains_metadata_not_code(tmp_path):
    """가장 중요한 불변식: 프롬프트에 코드 본문/식별 텍스트가 새면 안 된다."""
    sp, op = _write_reports(tmp_path)
    merged = load_and_merge(sp, op)
    prompt = build_user_prompt(merged, top_k=10)
    # 메타데이터는 들어있다
    assert "pkg/big.py" in prompt
    assert "12" in prompt  # complexity
    assert "Alice" in prompt
    # TODO 본문 텍스트(코드/주석 내용)는 프롬프트에 들어가지 않는다
    assert "TODO refactor" not in prompt


def test_build_user_prompt_respects_top_k(tmp_path):
    sp, op = _write_reports(tmp_path)
    merged = load_and_merge(sp, op)
    prompt = build_user_prompt(merged, top_k=1)
    assert "pkg/big.py" in prompt
    assert "pkg/small.py" not in prompt


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("high", "high"),
        ("HIGH", "high"),
        ("  Low ", "low"),
        (8, "high"),
        (5, "medium"),
        (2, "low"),
        ("garbage", "medium"),
    ],
)
def test_normalize_risk(raw, expected):
    assert _normalize_risk(raw) == expected


def test_parse_response_recovers_wrapped_json():
    raw = '설명 텍스트... {"priorities": [], "summary": "ok"} 끝'
    assert _parse_response(raw) == {"priorities": [], "summary": "ok"}


def test_generate_insights_dry_run(tmp_path):
    sp, op = _write_reports(tmp_path)
    result = generate_insights(sp, op, dry_run=True)
    assert result["dry_run"] is True
    assert "pkg/big.py" in result["prompt"]


def test_generate_insights_ollama_path(tmp_path, monkeypatch):
    sp, op = _write_reports(tmp_path)
    fake = json.dumps(
        {
            "priorities": [
                {
                    "file": "pkg/big.py",
                    "risk": 9,  # 숫자 → 정규화되어 high
                    "reason": "복잡도 높음",
                    "ask_who": "Alice",
                    "ask_what": "이 로직을?",
                }
            ],
            "summary": {"total": 1},  # 객체 → 문자열로 강제
        }
    )
    monkeypatch.setattr(
        insights, "_generate_ollama", lambda system, user, model, host: fake
    )
    result = generate_insights(sp, op, backend="ollama", model="x")
    assert result["backend"] == "ollama"
    assert result["insights"][0]["risk"] == "high"
    assert isinstance(result["summary"], str)


def test_generate_insights_unknown_backend(tmp_path):
    sp, op = _write_reports(tmp_path)
    with pytest.raises(ValueError):
        generate_insights(sp, op, backend="nope")
