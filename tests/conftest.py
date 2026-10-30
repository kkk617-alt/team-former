"""테스트 공용 도구.

부록의 명단 표기법("학생1(PL;RW)")을 그대로 써서 학생을 만든다. 공고 부록의
표와 테스트 코드를 눈으로 대조할 수 있게 하려는 것이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rules import Student  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# 공고 부록의 약자 (PL 기획자, WP 웹 프로그래머, …)
ABBREV = {
    "PL": "기획자",
    "WP": "웹 프로그래머",
    "FD": "프론트엔드 디자이너",
    "TT": "테스터",
    "RW": "보고서 작성자",
    "PT": "발표자",
}


def make_student(student_no: str, label: str) -> Student:
    """'2026101', '학생1(PL;RW)' → Student.

    괄호 안 첫째가 주 역할이고 나머지가 보조 역할이다. 명단 CSV의 name 열이
    실제로 이 표기이므로 label 을 그대로 이름으로 쓴다.
    """
    codes = label[label.index("(") + 1 : label.rindex(")")].split(";")
    return Student(
        student_no=student_no,
        name=label,
        main_role=ABBREV[codes[0]],
        sub_roles=tuple(ABBREV[code] for code in codes[1:]),
    )


def make_roster(rows: list[tuple[str, str]]) -> dict[str, Student]:
    """[(학번, 표기)] → {표기: Student}. 테스트에서 이름으로 꺼내 쓴다."""
    return {label: make_student(no, label) for no, label in rows}


# --- 부록 1. 쉬움 (팀 3개) -------------------------------------------------
EASY_ROWS = [
    ("2026101", "학생1(PL;RW)"),
    ("2026102", "학생2(PL;PT)"),
    ("2026103", "학생3(PL;TT)"),
    ("2026104", "학생4(WP;FD)"),
    ("2026105", "학생5(WP)"),
    ("2026106", "학생6(WP;TT)"),
    ("2026107", "학생7(FD;PT)"),
    ("2026108", "학생8(TT;RW;PT)"),
]

# --- 부록 2. 중간 (팀 4개) -------------------------------------------------
MEDIUM_ROWS = [
    ("2026201", "학생1(PL;PT;TT)"),
    ("2026202", "학생2(PL;TT)"),
    ("2026203", "학생3(PL;RW)"),
    ("2026204", "학생4(PL)"),
    ("2026205", "학생5(WP;TT)"),
    ("2026206", "학생6(WP;FD)"),
    ("2026207", "학생7(WP)"),
    ("2026208", "학생8(WP;PT)"),
    ("2026209", "학생9(FD;WP)"),
    ("2026210", "학생10(TT;PL)"),
    ("2026211", "학생11(RW)"),
    ("2026212", "학생12(PT;RW;FD)"),
]

# --- 부록 3. 어려움 (팀 4개) -----------------------------------------------
HARD_ROWS = [
    ("2026301", "학생1(PL;RW)"),
    ("2026302", "학생2(PL;PT)"),
    ("2026303", "학생3(PL;TT)"),
    ("2026304", "학생4(WP;PL)"),
    ("2026305", "학생5(WP;FD)"),
    ("2026306", "학생6(WP;RW)"),
    ("2026307", "학생7(FD;PT;TT)"),
    ("2026308", "학생8(FD;TT)"),
    ("2026309", "학생9(FD;WP)"),
    ("2026310", "학생10(TT;RW)"),
    ("2026311", "학생11(TT;PT)"),
    ("2026312", "학생12(TT;PL)"),
    ("2026313", "학생13(RW;PT;FD)"),
    ("2026314", "학생14(RW;TT)"),
    ("2026315", "학생15(PT;FD)"),
    ("2026316", "학생16(PT)"),
]


@pytest.fixture
def easy() -> dict[str, Student]:
    return make_roster(EASY_ROWS)


@pytest.fixture
def medium() -> dict[str, Student]:
    return make_roster(MEDIUM_ROWS)


@pytest.fixture
def hard() -> dict[str, Student]:
    return make_roster(HARD_ROWS)
