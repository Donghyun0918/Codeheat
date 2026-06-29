"""models.py dataclass 동작 검증."""

from codeheat.models import (
    ContributorScore,
    FileOwnershipReport,
    FileSmellReport,
    RefactorInsight,
    TodoItem,
)


def test_oldest_todo_days_picks_max():
    report = FileSmellReport(
        file="a.py",
        complexity=5,
        avg_complexity=2.0,
        function_count=3,
        loc=40,
        todos=[
            TodoItem(line=1, text="TODO a", age_days=3),
            TodoItem(line=9, text="TODO b", age_days=12),
            TodoItem(line=20, text="TODO c", age_days=None),
        ],
    )
    assert report.oldest_todo_days == 12


def test_oldest_todo_days_none_when_no_ages():
    report = FileSmellReport(
        file="a.py", complexity=1, avg_complexity=1.0, function_count=1, loc=10,
        todos=[TodoItem(line=1, text="TODO", age_days=None)],
    )
    assert report.oldest_todo_days is None


def test_smell_report_to_dict_roundtrip():
    d = FileSmellReport(
        file="a.py", complexity=8, avg_complexity=4.0, function_count=2, loc=30,
        todos=[TodoItem(line=2, text="FIXME x", age_days=1)],
    ).to_dict()
    assert d["file"] == "a.py"
    assert d["complexity"] == 8
    assert d["oldest_todo_days"] == 1
    assert d["duplication_ratio"] == 0.0
    assert d["todos"][0]["text"] == "FIXME x"


def test_ownership_to_dict():
    report = FileOwnershipReport(
        file="a.py",
        total_commits=4,
        top_contributors=[
            ContributorScore(name="Alice", score=3.14, commit_count=2, last_commit_days=5)
        ],
    )
    d = report.to_dict()
    assert d["total_commits"] == 4
    assert d["top_contributors"][0]["name"] == "Alice"
    assert d["top_contributors"][0]["last_commit_days"] == 5


def test_refactor_insight_to_dict():
    d = RefactorInsight(
        file="a.py", risk="high", reason="복잡도 급증",
        ask_who="Alice", ask_what="이 로직을 어떻게 풀까요?",
    ).to_dict()
    assert d == {
        "file": "a.py",
        "risk": "high",
        "reason": "복잡도 급증",
        "ask_who": "Alice",
        "ask_what": "이 로직을 어떻게 풀까요?",
    }
