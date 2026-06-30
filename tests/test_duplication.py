"""duplication.py: 파일 내부 중복률(type-1/type-2 클론, 폴백, 통합) 검증."""

from codeheat.duplication import (
    compute_duplication,
    duplication_ratio,
    normalized_logical_lines,
)
from codeheat.static_scan import build_smell_reports


def test_detects_type1_copy_paste():
    """완전히 동일한 블록이 2번 → 중복률 > 0."""
    block = (
        "alpha = compute()\n"
        "beta = alpha + 1\n"
        "gamma = beta * 2\n"
        "delta = gamma - 3\n"
    )
    src = block + "\n" + block
    assert duplication_ratio(src, "m.py") > 0.5


def test_detects_type2_renamed_clone():
    """변수명만 바꾼 복붙(type-2)도 토큰 정규화로 잡는다."""
    src = (
        "def a(x):\n"
        "    acc = 0\n"
        "    for i in range(x):\n"
        "        acc += i\n"
        "    return acc\n"
        "\n"
        "def b(y):\n"
        "    total = 0\n"
        "    for j in range(y):\n"
        "        total += j\n"
        "    return total\n"
    )
    assert duplication_ratio(src, "m.py") > 0.5


def test_no_duplication_is_zero():
    """서로 다른 라인뿐이면 0.0."""
    src = (
        "import os\n"
        "import sys\n"
        "def main():\n"
        "    print(os.getcwd())\n"
        "    return sys.argv\n"
        "class Foo:\n"
        "    value = 42\n"
    )
    assert duplication_ratio(src, "m.py") == 0.0


def test_short_file_is_zero():
    """window보다 짧은 파일은 0.0."""
    assert duplication_ratio("a = 1\nb = 2\n", "m.py") == 0.0


def test_comments_excluded_from_logical_lines():
    """반복되는 주석은 논리 라인이 아니므로 중복으로 세지 않는다."""
    src = "# the same note repeated\n" * 8 + "x = 1\ny = 2\n"
    assert duplication_ratio(src, "m.py") == 0.0
    # 논리 라인엔 주석이 없어야 한다
    lines = normalized_logical_lines(src, "m.py")
    assert all("note" not in norm for _, norm in lines)


def test_fallback_unknown_extension_type1():
    """렉서 없는 확장자도 폴백(공백 정규화)으로 type-1 클론을 잡는다."""
    block = (
        "alpha beta gamma\n"
        "delta epsilon\n"
        "zeta eta theta\n"
        "iota kappa\n"
    )
    src = block + block
    assert duplication_ratio(src, "notes.xyz") > 0.5


def test_compute_duplication_reads_file(tmp_path):
    block = (
        "p = step_one()\n"
        "q = step_two(p)\n"
        "r = step_three(q)\n"
        "s = step_four(r)\n"
    )
    f = tmp_path / "dup.py"
    f.write_text(block + "\n" + block, encoding="utf-8")
    assert compute_duplication(str(f)) > 0.5


def test_compute_duplication_missing_file_is_zero(tmp_path):
    assert compute_duplication(str(tmp_path / "nope.py")) == 0.0


def test_build_smell_reports_sets_duplication(tmp_path):
    """스캔 리포트에 중복률이 실려야 한다(죽은 필드 부활)."""
    block = (
        "def f{n}():\n"
        "    a = 0\n"
        "    for i in range(10):\n"
        "        a += i\n"
        "    return a\n"
    )
    (tmp_path / "dup.py").write_text(
        block.format(n=1) + "\n" + block.format(n=2), encoding="utf-8"
    )
    (tmp_path / "clean.py").write_text(
        "import os\n\n\ndef main():\n    return os.getcwd()\n", encoding="utf-8"
    )
    reports = build_smell_reports(
        str(tmp_path), compute_todo_age=False, compute_dup=True
    )
    by_file = {r.file: r for r in reports}
    assert by_file["dup.py"].duplication_ratio > 0.0
    assert by_file["clean.py"].duplication_ratio == 0.0


def test_build_smell_reports_can_skip_duplication(tmp_path):
    """compute_dup=False면 계산을 생략하고 0.0으로 둔다."""
    block = (
        "x = first()\n"
        "y = second(x)\n"
        "z = third(y)\n"
        "w = fourth(z)\n"
    )
    (tmp_path / "dup.py").write_text(block + "\n" + block, encoding="utf-8")
    reports = build_smell_reports(
        str(tmp_path), compute_todo_age=False, compute_dup=False
    )
    assert reports[0].duplication_ratio == 0.0
