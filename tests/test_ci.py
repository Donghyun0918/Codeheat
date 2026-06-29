"""ci.py: PR 봇의 순수 로직(변경파일 파싱·온도조립·코멘트 마크다운·upsert) 검증.

git/lizard/오너십/GitHub 호출은 전부 monkeypatch로 대체해 네트워크·저장소
상태에 의존하지 않는다.
"""

from codeheat import ci
from codeheat.ci import FileHeat, build_comment, get_changed_files


def _heat(path, base, head, owner="Alice", score=3.1):
    return FileHeat(path=path, base_ccn=base, head_ccn=head, owner=owner, owner_score=score)


# --- get_changed_files -----------------------------------------------------


def test_get_changed_files_parses_and_uses_three_dot_diff(monkeypatch):
    seen = {}

    def fake_run_git(repo, args):
        seen["args"] = args
        return "a.py\nb/c.py\n\n"  # 빈 줄은 무시돼야 함

    monkeypatch.setattr(ci, "_run_git", fake_run_git)
    files = get_changed_files("/repo", "base", "head")
    assert files == ["a.py", "b/c.py"]
    # base...head(three-dot) + 삭제 제외 옵션이 들어가야 한다.
    assert "base...head" in seen["args"]
    assert "--diff-filter=d" in seen["args"]


def test_get_changed_files_empty(monkeypatch):
    monkeypatch.setattr(ci, "_run_git", lambda repo, args: None)
    assert get_changed_files("/repo", "b", "h") == []


# --- _is_code_file ----------------------------------------------------------


def test_is_code_file_filters_non_code():
    assert ci._is_code_file("a.py")
    assert ci._is_code_file("src/b.js")
    assert not ci._is_code_file("README.md")
    assert not ci._is_code_file("pyproject.toml")
    assert not ci._is_code_file("data.json")


# --- FileHeat 델타/영향도 ---------------------------------------------------


def test_delta_and_impact():
    assert _heat("f", 10, 16).delta == 6
    assert _heat("f", 10, 16).impact == 6
    # 신규 파일: 델타 없음, 영향도는 전체 복잡도
    new = _heat("f", None, 12)
    assert new.delta is None
    assert new.impact == 12


# --- build_comment ----------------------------------------------------------


def test_build_comment_marks_rise_new_and_sorts_by_impact():
    heats = [
        _heat("small.py", 8, 8, owner="Bob", score=1.2),  # ±0
        _heat("hot.py", 10, 18, owner="Alice", score=3.1),  # +8 (최대 영향)
        _heat("new.py", None, 5, owner=None, score=None),  # 신규
    ]
    # build_comment는 정렬을 가정하므로 호출부처럼 미리 정렬해 넣는다.
    heats.sort(key=lambda h: h.impact, reverse=True)
    body = build_comment(heats)

    assert "🔺 +8" in body
    assert "🆕 신규" in body
    assert "▪️ ±0" in body
    # 가장 뜨거워진 파일은 hot.py이고 Alice를 지목해야 한다.
    assert "가장 뜨거워진 파일: **`hot.py`**" in body
    assert "Alice" in body
    # 오너 없는 신규 파일은 히스토리 부족 표시.
    assert "히스토리 부족" in body
    assert ci.MARKER in body


def test_build_comment_no_rise():
    body = build_comment([_heat("a.py", 10, 7, owner="Bob", score=1.0)])  # 🔻 -3
    assert "더 뜨거워진 코드 파일은 없습니다" in body
    assert "🔻 -3" in body


def test_build_comment_empty():
    body = build_comment([])
    assert "분석할 코드 변경이 없습니다" in body
    assert ci.MARKER in body


# --- compute_file_heats (조립 + 오너 매칭) ----------------------------------


def test_compute_file_heats_assembles_and_matches_owner(monkeypatch):
    from codeheat.models import ContributorScore, FileOwnershipReport

    monkeypatch.setattr(ci, "_resolve_sha", lambda repo, ref: f"sha-{ref}")

    # base/head 시점별 max CCN을 path+commit으로 흉내낸다.
    ccn = {("sha-base", "hot.py"): 10, ("sha-head", "hot.py"): 18,
           ("sha-base", "new.py"): None, ("sha-head", "new.py"): 5,
           ("sha-head", "data.json"): None}

    def fake_max_ccn(repo, commit, path):
        return ccn.get((commit, path))

    monkeypatch.setattr(ci, "_max_ccn_at", fake_max_ccn)
    monkeypatch.setattr(
        ci,
        "build_ownership_reports",
        lambda repo, files, top_n, use_complexity_delta: [
            FileOwnershipReport(
                "hot.py", 3, [ContributorScore("Alice", 3.1, 3, 1)]
            ),
            FileOwnershipReport("new.py", 0, []),
            FileOwnershipReport("data.json", 0, []),
        ],
    )

    heats = ci.compute_file_heats(
        "/repo", ["hot.py", "new.py", "data.json"], "base", "head"
    )
    # data.json은 비코드(_is_code_file=False)라 제외. 영향도 내림차순 정렬.
    assert [h.path for h in heats] == ["hot.py", "new.py"]
    assert heats[0].delta == 8
    assert heats[0].owner == "Alice"
    assert heats[1].base_ccn is None  # new.py는 base에 없음


# --- upsert_comment (PATCH vs POST) -----------------------------------------


def test_upsert_creates_when_no_existing(monkeypatch):
    calls = []

    def fake_request(method, url, token, body=None):
        calls.append((method, url))
        return [] if method == "GET" else {"id": 1}

    monkeypatch.setattr(ci, "_github_request", fake_request)
    assert ci.upsert_comment("https://api", "o/r", 7, "tok", "body") == "created"
    assert ("POST", "https://api/repos/o/r/issues/7/comments") in calls


def test_upsert_updates_when_marker_found(monkeypatch):
    calls = []

    def fake_request(method, url, token, body=None):
        calls.append((method, url))
        if method == "GET":
            return [{"id": 42, "body": f"old\n{ci.MARKER}"}]
        return {}

    monkeypatch.setattr(ci, "_github_request", fake_request)
    assert ci.upsert_comment("https://api", "o/r", 7, "tok", "new body") == "updated"
    assert ("PATCH", "https://api/repos/o/r/issues/comments/42") in calls
    # 기존 코멘트를 갱신했으니 새 코멘트 POST는 없어야 한다.
    assert all(m != "POST" for m, _ in calls)


# --- resolve_pr_context (이벤트 페이로드 파싱) ------------------------------


def test_resolve_pr_context_reads_event(monkeypatch, tmp_path):
    import argparse

    event = tmp_path / "event.json"
    event.write_text(
        '{"pull_request": {"number": 12, '
        '"base": {"sha": "BASE"}, "head": {"sha": "HEAD_SHA"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    args = argparse.Namespace(base=None, head=None, pr=None, repo_slug=None)
    base, head, number, repo = ci.resolve_pr_context(args)
    assert (base, head, number, repo) == ("BASE", "HEAD_SHA", 12, "o/r")


def test_resolve_pr_context_cli_overrides_event(monkeypatch):
    import argparse

    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    args = argparse.Namespace(
        base="b", head="h", pr=99, repo_slug="x/y"
    )
    assert ci.resolve_pr_context(args) == ("b", "h", 99, "x/y")
