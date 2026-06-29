"""ownership.py: git 로그 파싱·최근성 가중치·빈 히스토리 처리 검증.

git 서브프로세스는 monkeypatch로 대체해 네트워크/저장소 상태에 의존하지 않는다.
"""

from datetime import datetime, timezone

from codeheat import ownership
from codeheat.ownership import (
    _RECENCY_HALFLIFE_DAYS,
    _recency_weight,
    compute_ownership,
    get_commit_history,
)


def test_recency_weight_decays_by_halflife():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 지금 시점 커밋 → 가중치 1.0
    assert _recency_weight(int(now.timestamp()), now) == 1.0
    # 정확히 반감기 전 커밋 → 0.5 근처
    one_halflife_ago = now.timestamp() - _RECENCY_HALFLIFE_DAYS * 86400
    w = _recency_weight(int(one_halflife_ago), now)
    assert abs(w - 0.5) < 0.01


def test_get_commit_history_parses_and_reverses(monkeypatch):
    # git log는 최신→과거 순. churn은 numstat 합.
    fake_log = (
        "abc123|Alice|2000000000\n"
        "10\t5\tfile.py\n"
        "def456|Bob Smith|1000000000\n"
        "3\t2\tfile.py\n"
    )
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: fake_log)

    commits = get_commit_history("/repo", "/repo/file.py")
    # reverse() 적용 → 오래된(Bob) 먼저
    assert [c.author for c in commits] == ["Bob Smith", "Alice"]
    assert commits[0].timestamp == 1000000000
    assert commits[0].churn == 5  # 3 + 2
    assert commits[1].churn == 15  # 10 + 5


def test_get_commit_history_empty_on_no_output(monkeypatch):
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: None)
    assert get_commit_history("/repo", "/repo/file.py") == []


def test_compute_ownership_empty_history(monkeypatch):
    monkeypatch.setattr(ownership, "get_commit_history", lambda repo, f: [])
    report = compute_ownership("/repo", "/repo/missing.py")
    assert report.total_commits == 0
    assert report.top_contributors == []


def test_compute_ownership_churn_only_scores(monkeypatch):
    fake_log = (
        "h1|Alice|2000000000\n"
        "100\t0\tfile.py\n"
        "h2|Bob|1000000000\n"
        "1\t0\tfile.py\n"
    )
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: fake_log)
    report = compute_ownership(
        "/repo", "/repo/file.py", top_n=2, use_complexity_delta=False
    )
    assert report.total_commits == 2
    names = [c.name for c in report.top_contributors]
    # 더 많이 변경 + 더 최근인 Alice가 상위
    assert names[0] == "Alice"
