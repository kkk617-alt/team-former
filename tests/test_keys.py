"""화면 요소 이름이 공고 2.7절의 표와 같은지 확인한다.

이름이 틀리면 자동 채점 프로그램이 요소를 찾지 못해 멈추고 5점이 깎인다
(공고 6.3절 15번). 표의 값을 여기에 직접 적어 두고 맞대어 본다.
"""

from __future__ import annotations

import re

from app.ui import keys

# 공고 2.7절 표에서 그대로 옮긴 값
EXPECTED = {
    "LOGIN_STUDENT_NO": "login_student_no",
    "LOGIN_PASSWORD": "login_password",
    "LOGIN_SUBMIT": "login_submit",
    "WHOAMI": "whoami",
    "RESULT": "result",
    "ADMIN_ROSTER_FILE": "admin_roster_file",
    "ADMIN_TEAM_COUNT": "admin_team_count",
    "ADMIN_START": "admin_start",
    "ADMIN_CLOSE": "admin_close",
    "UNASSIGNED": "unassigned",
    "ADMIN_ASSIGN": "admin_assign",
    "ASSIGN_STATUS": "assign_status",
    "ADMIN_CONFIRM": "admin_confirm",
    "REFRESH": "refresh",
}


def test_every_fixed_key_matches_the_table():
    actual = {name: getattr(keys, name) for name in EXPECTED}
    assert actual == EXPECTED


def test_team_container_keys():
    assert keys.team(1) == "team_1"
    assert keys.team(2) == "team_2"
    assert keys.team(4) == "team_4"


def test_apply_button_keys():
    assert keys.apply(1) == "apply_1"
    assert keys.apply(3) == "apply_3"


def test_vote_keys_use_the_applicants_student_no():
    """공고 2.7절의 예: vote_yes_2026306"""
    assert keys.vote_yes("2026306") == "vote_yes_2026306"
    assert keys.vote_no("2026306") == "vote_no_2026306"


def test_keys_contain_only_ascii_letters_digits_and_underscores():
    """한글 key 는 채점 프로그램이 찾지 못한다 (공고 2.7절)."""
    pattern = re.compile(r"^[A-Za-z0-9_]+$")

    generated = [
        keys.team(1),
        keys.apply(1),
        keys.vote_yes("2026306"),
        keys.vote_no("2026306"),
    ]
    for value in list(EXPECTED.values()) + generated:
        assert pattern.match(value), value
