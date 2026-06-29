"""static_scan.py: TODO 탐지(단어 경계)와 복잡도 정렬 검증."""

from codeheat.static_scan import build_smell_reports, find_todos


def test_find_todos_detects_real_markers(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text(
        "x = 1  # TODO: fix this\n"
        "y = 2  # FIXME urgent\n",
        encoding="utf-8",
    )
    todos = find_todos(str(f))
    assert len(todos) == 2
    assert todos[0].line == 1
    assert "fix this" in todos[0].text


def test_find_todos_ignores_identifiers(tmp_path):
    """단어 경계(\\b) 덕분에 변수명은 오탐하지 않아야 한다."""
    f = tmp_path / "code.py"
    f.write_text(
        "todos = []\n"
        "TODO_PATTERN = 5\n"
        "fixmexyz = 1\n",
        encoding="utf-8",
    )
    assert find_todos(str(f)) == []


def test_find_todos_ignores_prose_and_code(tmp_path):
    """주석/라인-시작 앵커 덕분에 산문·코드 속 'TODO'는 오탐하지 않는다."""
    f = tmp_path / "noise.py"
    f.write_text(
        '"""1단계 분석: 복잡도 + TODO/FIXME 탐지 설명 산문."""\n'
        "todo.age_days = compute()\n"            # 코드 문장 (라인-시작이지만 ':' 없음)
        "for todo in todos:\n"                   # 루프 변수
        'msg = "--no-todo-age"\n'                # 문자열 인자명
        "note = 'TODO 나이 계산'\n",             # 문자열 산문
        encoding="utf-8",
    )
    assert find_todos(str(f)) == []


def test_find_todos_ignores_fake_comment_in_string(tmp_path):
    """핵심: 코드 문자열 리터럴 속 가짜 주석 마커는 토큰화로 배제된다."""
    f = tmp_path / "strlit.py"
    f.write_text(
        'sample = "# TODO: this is inside a string, not a comment"\n'
        "msg = '// FIXME: also fake'\n"
        "real = 1  # TODO: this one is a real comment\n",
        encoding="utf-8",
    )
    todos = find_todos(str(f))
    assert [t.line for t in todos] == [3]  # 진짜 주석 한 줄만


def test_find_todos_detects_comment_markers(tmp_path):
    """주석 마커(콜론 유무 무관, 작성자 표기 포함)는 잡는다."""
    f = tmp_path / "marks.py"
    f.write_text(
        "x = 1  # TODO: refactor\n"          # 주석 + 콜론
        "# FIXME handle error\n"             # 주석, 콜론 없음
        "# TODO(jane): port v2\n",           # 작성자 표기
        encoding="utf-8",
    )
    lines = sorted(t.line for t in find_todos(str(f)))
    assert lines == [1, 2, 3]


def test_find_todos_cross_language(tmp_path):
    """언어별 주석 문법(.js의 // 와 /* */)도 토큰화로 정확히 잡는다."""
    f = tmp_path / "app.js"
    f.write_text(
        'const u = "// TODO: fake in JS string";\n'  # 문자열 → 무시
        "let x = 1; // TODO: real line comment\n"     # 라인 주석 → 탐지
        "/* FIXME: block comment */\n",               # 블록 주석 → 탐지
        encoding="utf-8",
    )
    lines = sorted(t.line for t in find_todos(str(f)))
    assert lines == [2, 3]


def test_find_todos_fallback_unknown_extension(tmp_path):
    """렉서를 못 찾는 확장자는 라인-앵커 폴백으로 주석 마커를 잡는다."""
    f = tmp_path / "notes.xyz"
    f.write_text(
        "# TODO: fallback should still catch this\n"
        "plain text line, no marker\n",
        encoding="utf-8",
    )
    lines = [t.line for t in find_todos(str(f))]
    assert lines == [1]


def test_find_todos_fallback_masks_fake_string_comment(tmp_path):
    """폴백 경로에서도 문자열 리터럴 마스킹으로 한 줄짜리 가짜 주석을 거른다."""
    f = tmp_path / "notes.xyz"  # 렉서 없음 → 폴백 + 마스킹
    f.write_text(
        'log = "# TODO: 문자열 속 가짜"\n'   # 문자열 → 마스킹되어 배제
        "cmd = '// FIXME: 또 가짜'\n"          # 문자열 → 배제
        "real = 1  # TODO: 진짜 주석\n",       # 진짜 주석 → 탐지(표시는 원본 라인)
        encoding="utf-8",
    )
    todos = find_todos(str(f))
    assert [t.line for t in todos] == [3]
    assert todos[0].text == "real = 1  # TODO: 진짜 주석"  # 표시용은 원본 보존


def test_find_todos_pygments_absent(tmp_path, monkeypatch):
    """Pygments 미설치(ImportError) 시에도 폴백+마스킹이 동작한다."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pygments"):
            raise ImportError("simulated: pygments absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    f = tmp_path / "mod.py"  # .py지만 pygments가 없는 셈
    f.write_text(
        'fake = "# TODO: in string"\n'  # 마스킹으로 배제
        "ok = 1  # TODO: real\n",        # 탐지
        encoding="utf-8",
    )
    assert [t.line for t in find_todos(str(f))] == [2]


def test_mask_strings_unit():
    from codeheat.static_scan import _mask_strings

    # 문자열 구간만 공백으로, 길이 보존
    masked = _mask_strings('x = "# TODO" # real')
    assert "# TODO" not in masked.split("#", 1)[0]  # 문자열 속 마커 제거
    assert masked.endswith("# real")                # 실제 주석은 보존
    assert len(masked) == len('x = "# TODO" # real')
    # 짝이 안 맞는 따옴표(아포스트로피)는 건드리지 않음
    assert _mask_strings("# it's fine") == "# it's fine"


def test_build_smell_reports_sorted_by_complexity_desc(tmp_path):
    # 단순 파일 (CCN 1)
    (tmp_path / "simple.py").write_text(
        "def a():\n    return 1\n", encoding="utf-8"
    )
    # 복잡한 파일 (분기 다수 → CCN 높음)
    (tmp_path / "complex.py").write_text(
        "def b(x):\n"
        "    if x > 0:\n"
        "        if x > 10:\n"
        "            return 2\n"
        "        return 1\n"
        "    elif x < -5:\n"
        "        return -1\n"
        "    return 0\n",
        encoding="utf-8",
    )
    reports = build_smell_reports(str(tmp_path), compute_todo_age=False)
    assert len(reports) == 2
    # 복잡도 내림차순 → complex.py가 먼저
    assert reports[0].file.endswith("complex.py")
    assert reports[0].complexity >= reports[1].complexity
    # age 계산 생략 시 모든 todo age는 None (여기선 todo 없음)
    assert all(t.age_days is None for r in reports for t in r.todos)
