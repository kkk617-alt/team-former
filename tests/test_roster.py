"""명단 CSV 파싱 테스트 (공고 2.6절)."""

from __future__ import annotations

import pytest

from app.roles import PLANNER, PRESENTER, REPORTER, TESTER, WEB_DEV
from app.roster import RosterError, parse_roster

from conftest import EASY_ROWS, FIXTURES, HARD_ROWS, MEDIUM_ROWS, make_roster

HEADER = "student_no,name,main_role,sub_roles"


def csv_bytes(*lines: str, bom: bool = False) -> bytes:
    text = "\n".join([HEADER, *lines]) + "\n"
    return ("﻿" if bom else "") + text


def encode(*lines: str, bom: bool = False) -> bytes:
    return csv_bytes(*lines, bom=bom).encode("utf-8")


# =============================================================================
# 나눠 준 CSV 3개
#
# conftest 의 손으로 적은 명단과 교수가 나눠 준 CSV 가 같은지 맞대어 본다.
# 어긋나면 어느 한쪽이 틀린 것이므로 시나리오 테스트 전체가 의심스러워진다.
# =============================================================================


@pytest.mark.parametrize(
    "filename,rows",
    [
        ("쉬움.csv", EASY_ROWS),
        ("중간.csv", MEDIUM_ROWS),
        ("어려움.csv", HARD_ROWS),
    ],
)
def test_distributed_csv_matches_hand_written_roster(filename, rows):
    parsed = parse_roster((FIXTURES / filename).read_bytes())
    expected = list(make_roster(rows).values())
    assert parsed == expected


def test_distributed_csv_files_have_a_bom():
    """나눠 주는 CSV 는 엑셀에서 한글이 깨지지 않도록 BOM 이 붙은 UTF-8 이다."""
    for filename in ("쉬움.csv", "중간.csv", "어려움.csv"):
        assert (FIXTURES / filename).read_bytes().startswith(b"\xef\xbb\xbf")


# =============================================================================
# BOM
# =============================================================================


def test_reads_file_with_bom():
    students = parse_roster(encode("2026001,가나다,기획자,보고서 작성자", bom=True))
    assert students[0].student_no == "2026001"
    assert students[0].main_role == PLANNER


def test_reads_file_without_bom():
    students = parse_roster(encode("2026001,가나다,기획자,보고서 작성자"))
    assert students[0].student_no == "2026001"


# =============================================================================
# 보조 역할 (공고 2.6절의 예)
# =============================================================================


def test_blank_sub_roles_becomes_empty():
    """없으면 마지막 쉼표 뒤를 비워 둔다."""
    students = parse_roster(encode("2026002,라마바,웹 프로그래머,"))
    assert students[0].main_role == WEB_DEV
    assert students[0].sub_roles == ()


def test_two_sub_roles_split_on_semicolon():
    students = parse_roster(encode("2026003,사아자,테스터,기획자;발표자"))
    assert students[0].main_role == TESTER
    assert students[0].sub_roles == (PLANNER, PRESENTER)


def test_sub_roles_tolerate_spaces_around_semicolon():
    students = parse_roster(encode("2026003,사아자,테스터, 기획자 ; 발표자 "))
    assert students[0].sub_roles == (PLANNER, PRESENTER)


def test_rejects_more_than_two_sub_roles():
    with pytest.raises(RosterError, match="보조 역할"):
        parse_roster(encode("2026003,사아자,테스터,기획자;발표자;보고서 작성자"))


def test_drops_sub_role_identical_to_main_role():
    students = parse_roster(encode("2026004,마바사,테스터,테스터;기획자"))
    assert students[0].sub_roles == (PLANNER,)


# =============================================================================
# 잘못된 파일
# =============================================================================


def test_rejects_unknown_main_role():
    with pytest.raises(RosterError, match="디자이너"):
        parse_roster(encode("2026001,가나다,디자이너,"))


def test_rejects_unknown_sub_role():
    with pytest.raises(RosterError, match="수석 개발자"):
        parse_roster(encode("2026001,가나다,기획자,수석 개발자"))


def test_rejects_missing_column():
    """쉼표를 지우면 열이 3개가 되어 CSV 가 틀린다 (공고 2.6절)."""
    with pytest.raises(RosterError, match="sub_roles"):
        parse_roster("student_no,name,main_role\n2026001,가나다,기획자\n".encode())


def test_rejects_duplicate_student_no():
    with pytest.raises(RosterError, match="2026001"):
        parse_roster(encode("2026001,가나다,기획자,", "2026001,라마바,테스터,"))


def test_rejects_empty_roster():
    with pytest.raises(RosterError, match="비어"):
        parse_roster(encode())


def test_rejects_admin_as_student_no():
    """관리자 계정과 겹치면 안 된다 (공고 2.1절)."""
    with pytest.raises(RosterError, match="admin"):
        parse_roster(encode("admin,관리자,기획자,"))


def test_rejects_blank_name():
    with pytest.raises(RosterError, match="이름"):
        parse_roster(encode("2026001,,기획자,"))


def test_skips_fully_blank_lines():
    students = parse_roster(encode("2026001,가나다,기획자,", "", "2026002,라마바,테스터,"))
    assert [s.student_no for s in students] == ["2026001", "2026002"]


def test_error_message_names_the_offending_line():
    with pytest.raises(RosterError, match="3번째 줄"):
        parse_roster(encode("2026001,가나다,기획자,", "2026002,라마바,사육사,"))


def test_strips_surrounding_whitespace():
    students = parse_roster(encode(" 2026001 , 가나다 , 기획자 , 보고서 작성자 "))
    assert students[0].student_no == "2026001"
    assert students[0].name == "가나다"
    assert students[0].main_role == PLANNER
    assert students[0].sub_roles == (REPORTER,)
