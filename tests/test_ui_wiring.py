"""화면 코드가 공고 2.7절의 key 를 실제로 쓰고 있는지 소스에서 확인한다.

key 를 표와 다르게 지정했거나 지정하지 않아 자동 채점 프로그램이 멈추면 5점이
깎인다 (공고 6.3절 15번). 실제 화면을 띄우지 않고도 다음을 잡아낸다.

  - 표의 key 가 어느 화면에도 없는 경우
  - 한 화면에서 같은 key 를 두 번 쓴 경우 (Streamlit 이 실행 중에 죽는다)
  - keys.py 를 거치지 않고 문자열을 직접 적은 경우
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.ui import keys

UI_DIR = Path(__file__).resolve().parent.parent / "app" / "ui"

#: keys.py 의 함수로 만드는 key 들. 번호나 학번이 붙으므로 이름만 확인한다.
FAMILIES = {"team", "apply", "vote_yes", "vote_no"}

#: 공고 2.7절 표의 고정 key 전체
REQUIRED_FIXED = {
    "login_student_no",
    "login_password",
    "login_submit",
    "whoami",
    "result",
    "admin_roster_file",
    "admin_team_count",
    "admin_start",
    "admin_close",
    "unassigned",
    "admin_assign",
    "assign_status",
    "admin_confirm",
}


def collect(path: Path) -> tuple[list[str], list[str], list[str]]:
    """(고정 key, 함수로 만든 key 의 이름, 직접 적은 문자열 key)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fixed: list[str] = []
    families: list[str] = []
    literals: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "key":
                continue
            value = kw.value

            # keys.LOGIN_SUBMIT 처럼 상수를 참조한 경우
            if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
                if value.value.id == "keys":
                    fixed.append(getattr(keys, value.attr))
                continue

            # keys.team(n) 처럼 함수로 만든 경우
            if isinstance(value, ast.Call):
                func = value.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id == "keys":
                        families.append(func.attr)
                continue

            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                literals.append(value.value)

    return fixed, families, literals


SCREENS = {
    "common.py": UI_DIR / "common.py",
    "student.py": UI_DIR / "student.py",
    "admin.py": UI_DIR / "admin.py",
}


def test_every_key_in_the_table_is_wired_somewhere():
    used: set[str] = set()
    for path in SCREENS.values():
        fixed, _, _ = collect(path)
        used.update(fixed)

    missing = REQUIRED_FIXED - used
    assert missing == set(), f"화면에 없는 key: {sorted(missing)}"


def test_all_four_dynamic_key_families_are_wired():
    used: set[str] = set()
    for path in SCREENS.values():
        _, families, _ = collect(path)
        used.update(families)

    assert FAMILIES <= used, f"쓰이지 않은 key 함수: {sorted(FAMILIES - used)}"


@pytest.mark.parametrize("name", sorted(SCREENS), ids=lambda n: n)
def test_no_fixed_key_is_used_twice_in_one_module(name):
    """같은 화면에서 key 가 겹치면 Streamlit 이 DuplicateWidgetID 로 죽는다."""
    fixed, _, _ = collect(SCREENS[name])
    duplicates = sorted({k for k in fixed if fixed.count(k) > 1})
    assert duplicates == [], f"{name} 에서 겹친 key: {duplicates}"


@pytest.mark.parametrize("name", sorted(SCREENS), ids=lambda n: n)
def test_keys_are_never_written_as_bare_strings(name):
    """key 는 반드시 app/ui/keys.py 를 거친다. 표와 어긋날 여지를 없애려는 것이다."""
    _, _, literals = collect(SCREENS[name])
    assert literals == [], f"{name} 에 직접 적은 key: {literals}"


def test_student_screen_wires_the_student_side_keys():
    fixed, families, _ = collect(SCREENS["student.py"])
    assert "team" in families
    assert "apply" in families
    assert "vote_yes" in families
    assert "vote_no" in families


def test_admin_screen_wires_every_admin_key():
    fixed, families, _ = collect(SCREENS["admin.py"])
    admin_keys = {
        keys.ADMIN_ROSTER_FILE,
        keys.ADMIN_TEAM_COUNT,
        keys.ADMIN_START,
        keys.ADMIN_CLOSE,
        keys.UNASSIGNED,
        keys.ADMIN_ASSIGN,
        keys.ASSIGN_STATUS,
        keys.ADMIN_CONFIRM,
    }
    assert admin_keys <= set(fixed), sorted(admin_keys - set(fixed))


def test_login_and_shared_keys_live_in_common():
    fixed, _, _ = collect(SCREENS["common.py"])
    shared = {
        keys.LOGIN_STUDENT_NO,
        keys.LOGIN_PASSWORD,
        keys.LOGIN_SUBMIT,
        keys.WHOAMI,
        keys.RESULT,
        keys.REFRESH,
    }
    assert shared <= set(fixed), sorted(shared - set(fixed))

# =============================================================================
# 화면 한 번에 드는 왕복 (공고 4.2절)
# =============================================================================


def _function(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{path.name} 에 {name} 이 없음")


def _store_calls(func: ast.FunctionDef) -> list[str]:
    """함수 안에서 store.<무엇>(...) 을 부른 이름들."""
    return [
        node.func.attr
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "store"
    ]


def test_one_student_screen_asks_the_store_once():
    """화면 한 번에 저장소를 한 번만 부른다 (공고 4.2절).

    따로 물으면 왕복이 다섯 번이고, 배포한 앱에서는 화면 한 번이 6.3초가 되어
    fragment 의 5초 간격을 넘겼다. 그러면 모든 세션이 쉬지 않고 화면을 그리는
    상태가 되어, 누른 단추의 처리가 채점 프로그램이 기다리는 7초를 넘긴다.
    """
    calls = _store_calls(_function(UI_DIR / "student.py", "_read"))
    assert calls == ["student_screen"], f"저장소를 {len(calls)} 번 부름: {calls}"


def test_the_refresh_button_does_not_read_twice():
    """새로 고침이 st.rerun 을 또 부르면 같은 읽기를 두 번 한다.

    단추를 누르는 것만으로 Streamlit 이 fragment 를 처음부터 다시 돌리고, 그
    처음에서 DB 를 이미 다시 읽는다.
    """
    func = _function(UI_DIR / "common.py", "render_refresh_button")
    reruns = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rerun"
    ]
    assert reruns == [], "새로 고침이 st.rerun 을 부르고 있음"
