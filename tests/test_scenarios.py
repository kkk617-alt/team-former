"""부록 연습용 시나리오 3개를 단계별로 재현한다.

공고 부록의 "하는 일"과 "기대 결과"를 그대로 옮겨, 결과 안내의 첫 단어가 기대
결과와 같은지 확인한다 (공고 6.2절 3항).

지원이 막혔으면 그 지원에 대한 뒤의 투표는 건너뛴다 (공고 부록 머리말).
"""

from __future__ import annotations

import pytest

from app import flow
from app.rules import Student

from conftest import EASY_ROWS, HARD_ROWS, MEDIUM_ROWS, make_roster
from memstore import InMemoryStore

AGREE = "찬성"
REFUSE = "거부"


class Driver:
    """시나리오 단계를 공고의 문장에 가깝게 쓰기 위한 얇은 껍데기."""

    def __init__(self, rows: list[tuple[str, str]], team_count: int) -> None:
        self.roster = make_roster(rows)
        self.store = InMemoryStore()
        self.store.reset(list(self.roster.values()), team_count)

    def no(self, label: str) -> str:
        return self.roster[label].student_no

    def apply(self, label: str, team_no: int) -> str:
        """'<label> 이 팀<team_no> 에 지원' → 결과의 첫 단어."""
        return flow.apply_to_team(self.store, self.no(label), team_no).outcome

    def vote(self, voter: str, applicant: str, vote: str) -> str:
        """'<voter> 가 <applicant> 에 찬성/거부' → 그 지원의 지금 상태."""
        return flow.cast_vote(self.store, self.no(voter), self.no(applicant), vote).outcome

    def close(self) -> str:
        return flow.close_recruiting(self.store).outcome

    def members(self, team_no: int) -> set[str]:
        return {s.name for s in self.store.team_members(team_no)}

    def unassigned(self) -> set[str]:
        return {s.name for s in flow.unassigned_students(self.store)}

    def teams(self) -> dict[int, list[Student]]:
        return flow.current_teams(self.store)


# =============================================================================
# 부록 1. 쉬움 — 팀 3개, 6단계
# =============================================================================


@pytest.fixture
def easy_run() -> Driver:
    return Driver(EASY_ROWS, team_count=3)


def test_easy_step1_three_students_apply_to_empty_teams(easy_run):
    """1단계: 학생1→팀1, 학생2→팀2, 학생3→팀3 / 기대: 3명 모두 바로 승인"""
    assert easy_run.apply("학생1(PL;RW)", 1) == "승인"
    assert easy_run.apply("학생2(PL;PT)", 2) == "승인"
    assert easy_run.apply("학생3(PL;TT)", 3) == "승인"


def test_easy_steps_1_to_5(easy_run):
    r = easy_run

    # 1단계
    assert r.apply("학생1(PL;RW)", 1) == "승인"
    assert r.apply("학생2(PL;PT)", 2) == "승인"
    assert r.apply("학생3(PL;TT)", 3) == "승인"

    # 2단계: 학생4→팀1, 학생1 찬성 / 기대: 승인
    assert r.apply("학생4(WP;FD)", 1) == "대기"
    assert r.vote("학생1(PL;RW)", "학생4(WP;FD)", AGREE) == "승인"

    # 3단계: 학생5→팀2, 학생2 찬성 / 기대: 승인
    assert r.apply("학생5(WP)", 2) == "대기"
    assert r.vote("학생2(PL;PT)", "학생5(WP)", AGREE) == "승인"

    # 4단계: 학생7→팀1, 학생1 찬성, 학생4 거부 / 기대: 거절
    assert r.apply("학생7(FD;PT)", 1) == "대기"
    assert r.vote("학생1(PL;RW)", "학생7(FD;PT)", AGREE) == "대기"
    assert r.vote("학생4(WP;FD)", "학생7(FD;PT)", REFUSE) == "거절"

    # 5단계: 학생6→팀3, 학생3 찬성 / 기대: 승인
    assert r.apply("학생6(WP;TT)", 3) == "대기"
    assert r.vote("학생3(PL;TT)", "학생6(WP;TT)", AGREE) == "승인"

    assert r.members(1) == {"학생1(PL;RW)", "학생4(WP;FD)"}
    assert r.members(2) == {"학생2(PL;PT)", "학생5(WP)"}
    assert r.members(3) == {"학생3(PL;TT)", "학생6(WP;TT)"}


def test_easy_step6_close_assign_and_confirm(easy_run):
    """6단계: 관리자가 마감하고 배정, 확정
    기대: 남은 학생이 모두 배정되고, 모든 팀이 규칙을 지킴"""
    r = easy_run
    test_easy_steps_1_to_5(r)

    assert r.close() == "승인"
    # 학생7 은 4단계에서 이미 거절되었고, 1명뿐인 팀은 없다.
    assert r.unassigned() == {"학생7(FD;PT)", "학생8(TT;RW;PT)"}

    plan = flow.solve_assignment(r.teams(), flow.unassigned_students(r.store))
    assert plan is not None, "규칙을 지키는 배정을 찾지 못했다"

    assert flow.confirm_assignment(r.store, plan).outcome == "승인"
    assert flow.check_confirmed_teams(r.store) == []
    assert r.unassigned() == set()


# =============================================================================
# 부록 2. 중간 — 팀 4개, 11단계
# =============================================================================


@pytest.fixture
def medium_run() -> Driver:
    return Driver(MEDIUM_ROWS, team_count=4)


def test_medium_steps_1_to_8(medium_run):
    r = medium_run

    # 1단계: 학생1→팀1 / 기대: 바로 승인
    assert r.apply("학생1(PL;PT;TT)", 1) == "승인"

    # 2단계: 학생5→팀1, 학생1 찬성 / 기대: 승인
    assert r.apply("학생5(WP;TT)", 1) == "대기"
    assert r.vote("학생1(PL;PT;TT)", "학생5(WP;TT)", AGREE) == "승인"

    # 3단계: 학생2→팀1 / 기대: 막힘(주 역할 중복)
    #   지원이 막혔으므로 뒤의 투표는 건너뛴다.
    assert r.apply("학생2(PL;TT)", 1) == "막힘"

    # 4단계: 학생6→팀2 / 기대: 바로 승인
    assert r.apply("학생6(WP;FD)", 2) == "승인"

    # 5단계: 학생9→팀2, 학생6 찬성 / 기대: 승인
    assert r.apply("학생9(FD;WP)", 2) == "대기"
    assert r.vote("학생6(WP;FD)", "학생9(FD;WP)", AGREE) == "승인"

    # 6단계: 학생10→팀2, 학생6 찬성, 학생9 거부 / 기대: 거절
    assert r.apply("학생10(TT;PL)", 2) == "대기"
    assert r.vote("학생6(WP;FD)", "학생10(TT;PL)", AGREE) == "대기"
    assert r.vote("학생9(FD;WP)", "학생10(TT;PL)", REFUSE) == "거절"

    # 7단계: 학생3→팀3, 학생11→팀4 / 기대: 2명 모두 바로 승인
    assert r.apply("학생3(PL;RW)", 3) == "승인"
    assert r.apply("학생11(RW)", 4) == "승인"

    # 8단계: 학생12→팀4 (아무도 투표하지 않음), 이어서 팀3 에도 지원
    #   기대: 팀4 지원은 대기, 팀3 지원은 막힘
    assert r.apply("학생12(PT;RW;FD)", 4) == "대기"
    assert r.apply("학생12(PT;RW;FD)", 3) == "막힘"


def test_medium_steps_9_to_11(medium_run):
    r = medium_run
    test_medium_steps_1_to_8(r)

    # 9단계: 관리자가 마감
    #   기대: 학생12 의 지원은 거절. 학생3 과 학생11 은 팀에서 빠짐
    assert r.close() == "승인"
    assert r.store.pending_application_of(r.no("학생12(PT;RW;FD)")) is None
    assert r.members(3) == set()
    assert r.members(4) == set()
    assert {"학생3(PL;RW)", "학생11(RW)", "학생12(PT;RW;FD)"} <= r.unassigned()

    # 10단계: 학생2→팀3 / 기대: 막힘(마감)
    assert r.apply("학생2(PL;TT)", 3) == "막힘"

    # 11단계: 관리자가 배정, 확정
    #   기대: 남은 학생이 모두 배정되고, 모든 팀이 규칙을 지킴
    assert len(r.unassigned()) == 8
    plan = flow.solve_assignment(r.teams(), flow.unassigned_students(r.store))
    assert plan is not None, "규칙을 지키는 배정을 찾지 못했다"

    assert flow.confirm_assignment(r.store, plan).outcome == "승인"
    assert flow.check_confirmed_teams(r.store) == []
    assert r.unassigned() == set()


# =============================================================================
# 부록 3. 어려움 — 팀 4개, 15단계
# =============================================================================


@pytest.fixture
def hard_run() -> Driver:
    return Driver(HARD_ROWS, team_count=4)


def test_hard_steps_1_to_8(hard_run):
    r = hard_run

    # 1단계: 학생1→팀1 / 기대: 바로 승인
    assert r.apply("학생1(PL;RW)", 1) == "승인"

    # 2단계: 학생4→팀1, 학생1 찬성 / 기대: 승인
    assert r.apply("학생4(WP;PL)", 1) == "대기"
    assert r.vote("학생1(PL;RW)", "학생4(WP;PL)", AGREE) == "승인"

    # 3단계: 학생7→팀1, 학생1·학생4 찬성 / 기대: 승인
    assert r.apply("학생7(FD;PT;TT)", 1) == "대기"
    assert r.vote("학생1(PL;RW)", "학생7(FD;PT;TT)", AGREE) == "대기"
    assert r.vote("학생4(WP;PL)", "학생7(FD;PT;TT)", AGREE) == "승인"

    # 4단계: 학생2→팀2 / 기대: 바로 승인
    assert r.apply("학생2(PL;PT)", 2) == "승인"

    # 5단계: 학생8→팀2, 학생2 찬성 / 기대: 승인
    assert r.apply("학생8(FD;TT)", 2) == "대기"
    assert r.vote("학생2(PL;PT)", "학생8(FD;TT)", AGREE) == "승인"

    # 6단계: 학생5 와 학생6 이 차례로 팀2 에 지원 / 기대: 2명 모두 대기
    assert r.apply("학생5(WP;FD)", 2) == "대기"
    assert r.apply("학생6(WP;RW)", 2) == "대기"

    # 7단계: 학생2·학생8 이 학생5 에 찬성 / 기대: 승인
    assert r.vote("학생2(PL;PT)", "학생5(WP;FD)", AGREE) == "대기"
    assert r.vote("학생8(FD;TT)", "학생5(WP;FD)", AGREE) == "승인"

    # 8단계: 학생2·학생8·학생5 가 학생6 에 찬성 / 기대: 거절(승인 직전 검사)
    #   학생5 가 먼저 승인되어 팀2 의 주 역할에 웹 프로그래머가 생겼다.
    assert r.vote("학생2(PL;PT)", "학생6(WP;RW)", AGREE) == "대기"
    assert r.vote("학생8(FD;TT)", "학생6(WP;RW)", AGREE) == "대기"
    assert r.vote("학생5(WP;FD)", "학생6(WP;RW)", AGREE) == "거절"


def test_hard_steps_9_to_13(hard_run):
    r = hard_run
    test_hard_steps_1_to_8(r)

    # 9단계: 학생11→팀3 / 기대: 바로 승인
    assert r.apply("학생11(TT;PT)", 3) == "승인"

    # 10단계: 학생15→팀3, 학생11 찬성 / 기대: 승인
    assert r.apply("학생15(PT;FD)", 3) == "대기"
    assert r.vote("학생11(TT;PT)", "학생15(PT;FD)", AGREE) == "승인"

    # 11단계: 학생14→팀3 / 기대: 막힘(필수 포함 역할 자리)
    #   지원이 막혔으므로 뒤의 투표는 건너뛴다.
    assert r.apply("학생14(RW;TT)", 3) == "막힘"

    # 12단계: 학생10→팀4 / 기대: 바로 승인
    assert r.apply("학생10(TT;RW)", 4) == "승인"

    # 13단계: 학생13→팀1, 학생1 만 찬성 / 기대: 대기
    assert r.apply("학생13(RW;PT;FD)", 1) == "대기"
    assert r.vote("학생1(PL;RW)", "학생13(RW;PT;FD)", AGREE) == "대기"


def test_hard_steps_14_to_15(hard_run):
    r = hard_run
    test_hard_steps_9_to_13(r)

    # 14단계: 관리자가 마감
    #   기대: 학생13 의 지원은 거절. 학생10 은 팀에서 빠짐
    assert r.close() == "승인"
    assert r.store.pending_application_of(r.no("학생13(RW;PT;FD)")) is None
    assert r.members(4) == set()
    assert {"학생10(TT;RW)", "학생13(RW;PT;FD)"} <= r.unassigned()

    # 15단계: 관리자가 배정, 확정
    #   기대: 남은 학생이 모두 배정되고, 모든 팀이 규칙을 지킴
    assert len(r.unassigned()) == 8
    plan = flow.solve_assignment(r.teams(), flow.unassigned_students(r.store))
    assert plan is not None, "규칙을 지키는 배정을 찾지 못했다"

    assert flow.confirm_assignment(r.store, plan).outcome == "승인"
    assert flow.check_confirmed_teams(r.store) == []
    assert r.unassigned() == set()


# =============================================================================
# 흐름 규칙 — 시나리오에 없지만 공고가 요구하는 것
# =============================================================================


def test_vote_cannot_be_changed(easy_run):
    """한 번 투표하면 바꿀 수 없음 (공고 2.4절)."""
    r = easy_run
    r.apply("학생1(PL;RW)", 1)
    r.apply("학생4(WP;FD)", 1)
    assert r.vote("학생1(PL;RW)", "학생4(WP;FD)", AGREE) == "승인"
    # 이미 승인된 지원에 다시 투표할 수 없다
    assert r.vote("학생1(PL;RW)", "학생4(WP;FD)", REFUSE) == "막힘"


def test_non_member_cannot_vote(easy_run):
    """투표할 사람은 그 팀의 팀원뿐이다."""
    r = easy_run
    r.apply("학생1(PL;RW)", 1)
    r.apply("학생4(WP;FD)", 1)
    assert r.vote("학생2(PL;PT)", "학생4(WP;FD)", AGREE) == "막힘"


def test_new_member_must_also_vote(hard_run):
    """투표할 사람은 투표하는 때의 팀원이다 (공고 2.4절).

    내가 지원한 뒤에 다른 지원자가 먼저 승인되어 팀원이 되면, 그 사람도 내 지원에
    투표해야 한다. 어려움 7~8단계가 이 규칙에 기댄다.
    """
    r = hard_run
    r.apply("학생2(PL;PT)", 2)
    r.apply("학생8(FD;TT)", 2)
    r.vote("학생2(PL;PT)", "학생8(FD;TT)", AGREE)

    r.apply("학생5(WP;FD)", 2)
    r.apply("학생13(RW;PT;FD)", 2)

    # 학생5 를 먼저 승인시킨다
    r.vote("학생2(PL;PT)", "학생5(WP;FD)", AGREE)
    assert r.vote("학생8(FD;TT)", "학생5(WP;FD)", AGREE) == "승인"

    # 학생13 의 지원은 기존 두 명이 찬성해도 아직 대기다. 새 팀원 학생5 도
    # 투표해야 한다.
    r.vote("학생2(PL;PT)", "학생13(RW;PT;FD)", AGREE)
    assert r.vote("학생8(FD;TT)", "학생13(RW;PT;FD)", AGREE) == "대기"
    assert r.vote("학생5(WP;FD)", "학생13(RW;PT;FD)", AGREE) == "승인"


def test_voting_is_blocked_after_close(easy_run):
    r = easy_run
    r.apply("학생1(PL;RW)", 1)
    r.apply("학생4(WP;FD)", 1)
    r.close()
    assert r.vote("학생1(PL;RW)", "학생4(WP;FD)", AGREE) == "막힘"


def test_student_can_apply_again_after_rejection(easy_run):
    """결과가 나온 뒤에는 다른 팀에 다시 지원할 수 있다 (공고 2.4절)."""
    r = easy_run
    r.apply("학생1(PL;RW)", 1)
    r.apply("학생2(PL;PT)", 2)
    r.apply("학생7(FD;PT)", 1)
    assert r.vote("학생1(PL;RW)", "학생7(FD;PT)", REFUSE) == "거절"
    assert r.apply("학생7(FD;PT)", 2) == "대기"


def test_blocked_application_is_not_recorded(medium_run):
    """막힘은 지원을 아예 접수하지 않은 것이므로 대기 지원이 생기지 않는다."""
    r = medium_run
    r.apply("학생1(PL;PT;TT)", 1)
    assert r.apply("학생2(PL;TT)", 1) == "막힘"
    assert r.store.pending_application_of(r.no("학생2(PL;TT)")) is None
    # 막혔을 뿐이므로 다른 팀에는 지원할 수 있다
    assert r.apply("학생2(PL;TT)", 2) == "승인"


def test_losing_the_last_slot_is_recorded_as_a_rejection(easy_run):
    """유일성 제약에 막힌 승인은 거절로 기록된다 (공고 3장).

    학생4 가 팀1 에 지원해 대기하는 동안 다른 경로로 팀2 에 들어간 상황을 만든다.
    승인 직전 재검사는 팀1 만 보므로 통과하지만, 한 학생은 한 팀에만 속할 수
    있으므로 저장이 막힌다.
    """
    r = easy_run
    assert r.apply("학생1(PL;RW)", 1) == "승인"
    assert r.apply("학생4(WP;FD)", 1) == "대기"

    r.store.add_member(2, r.no("학생4(WP;FD)"))

    assert r.vote("학생1(PL;RW)", "학생4(WP;FD)", AGREE) == "거절"


def test_solver_reports_failure_when_no_valid_assignment_exists():
    """규칙을 지키는 배정이 없으면 None 을 돌려준다 (공고 2.5절 8항)."""
    rows = [
        ("2026701", "학생71(TT)"),
        ("2026702", "학생72(PT)"),
        ("2026703", "학생73(RW)"),
        ("2026704", "학생74(FD)"),
    ]
    r = Driver(rows, team_count=2)
    # 기획자도 웹 프로그래머도 맡을 수 있는 학생이 아무도 없다
    assert flow.solve_assignment(r.teams(), flow.unassigned_students(r.store)) is None
