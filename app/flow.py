"""지원·투표·마감·배정 흐름.

규칙 판정은 app/rules.py 가, 저장은 app/store.py 계약의 구현이 맡는다. 이 모듈은
둘을 엮어 "단추를 누른 결과"를 만든다.

모든 함수가 Decision 을 돌려주고, 그 message 가 화면의 result 컨테이너에 그대로
들어간다 (공고 2.7절).
"""

from __future__ import annotations

from typing import Mapping, Sequence

from . import rules
from .roles import REQUIRED_ROLES
from .rules import (
    APPROVED,
    BLOCKED,
    MAX_TEAM_SIZE,
    PENDING,
    REJECTED,
    Decision,
    Student,
)
from .store import AlreadyInTeam, Application, PendingExists, SlotTaken, Store

AGREE = "찬성"
REFUSE = "거부"


# =============================================================================
# 조회
# =============================================================================


def current_teams(store: Store) -> dict[int, list[Student]]:
    """{팀 번호: 팀원}. 빈 팀도 빈 목록으로 들어 있다."""
    return {team_no: store.team_members(team_no) for team_no in store.team_numbers()}


def unassigned_students(store: Store) -> list[Student]:
    """팀이 없는 학생 (공고 2.5절 2항)."""
    return [s for s in store.all_students() if store.team_of(s.student_no) is None]


# =============================================================================
# 지원
# =============================================================================


def apply_to_team(store: Store, student_no: str, team_no: int) -> Decision:
    """팀에 지원하는 단추를 누른 결과 (공고 2.4절)."""
    applicant = store.student(student_no)
    if applicant is None:
        return Decision(BLOCKED, "학생을 찾을 수 없음")
    if team_no not in store.team_numbers():
        return Decision(BLOCKED, "없는 팀임")

    decision = rules.check_apply(
        applicant,
        store.team_members(team_no),
        closed=store.is_closed(),
        has_team=store.team_of(student_no) is not None,
        has_pending=store.pending_application_of(student_no) is not None,
    )

    # 막힘은 지원을 아예 접수하지 않은 것이므로 DB 에 기록하지 않는다 (공고 2.4절).
    if decision.outcome == BLOCKED:
        return decision

    if decision.outcome == APPROVED:
        # 빈 팀 지원은 투표할 팀원이 없으므로 바로 승인된다.
        try:
            store.add_member(team_no, student_no)
        except AlreadyInTeam:
            return Decision(BLOCKED, "이미 팀이 있음")
        except SlotTaken:
            return Decision(BLOCKED, "팀이 꽉 참")
        store.create_application(team_no, student_no, APPROVED, decision.reason)
        return decision

    try:
        store.create_application(team_no, student_no, PENDING)
    except PendingExists:
        return Decision(BLOCKED, "결과를 기다리는 지원이 있음")
    return decision


# =============================================================================
# 투표
# =============================================================================


def cast_vote(store: Store, voter_no: str, applicant_no: str, vote: str) -> Decision:
    """찬성 또는 거부 단추를 누른 결과. 그 지원의 지금 상태를 돌려준다 (공고 2.7절)."""
    if store.is_closed():
        return Decision(BLOCKED, "모집이 마감됨")
    if vote not in (AGREE, REFUSE):
        return Decision(BLOCKED, "알 수 없는 투표임")

    team_no = store.team_of(voter_no)
    if team_no is None:
        return Decision(BLOCKED, "팀원만 투표할 수 있음")

    application = store.pending_application_for(team_no, applicant_no)
    if application is None:
        return Decision(BLOCKED, "투표할 지원이 없음")

    # 한 번 투표하면 바꿀 수 없음 (공고 2.4절)
    if store.vote_of(application.id, voter_no) is not None:
        return Decision(BLOCKED, "이미 투표함")

    store.record_vote(application.id, voter_no, vote)

    if vote == REFUSE:
        # 다른 팀원의 투표를 기다리지 않고 바로 거절됨 (공고 2.4절)
        store.set_application_status(application.id, REJECTED, "팀원이 거부함")
        return Decision(REJECTED, "팀원이 거부함")

    return _try_approve(store, application)


def _try_approve(store: Store, application: Application) -> Decision:
    """모든 팀원이 찬성했으면 승인 직전 재검사를 거쳐 승인한다."""
    members = store.team_members(application.team_no)
    votes = store.votes_for(application.id)

    # 투표할 사람은 투표하는 때의 팀원이다. 내가 지원한 뒤에 승인되어 들어온
    # 팀원도 내 지원에 투표해야 한다 (공고 2.4절).
    if not all(votes.get(m.student_no) == AGREE for m in members):
        return Decision(PENDING, "팀원의 투표를 기다림")

    applicant = store.student(application.student_no)
    if applicant is None:
        store.set_application_status(application.id, REJECTED, "학생을 찾을 수 없음")
        return Decision(REJECTED, "학생을 찾을 수 없음")

    # 승인 직전 재검사 (공고 2.4절, 3장의 어려운 해결)
    decision = rules.check_before_approval(applicant, members)
    if decision.outcome == REJECTED:
        store.set_application_status(application.id, REJECTED, decision.reason)
        return decision

    try:
        store.add_member(application.team_no, application.student_no)
    except (AlreadyInTeam, SlotTaken):
        # DB 유일성 제약이 막은 경우. 먼저 도착한 학생만 기록된다 (공고 3장).
        reason = "마지막 자리를 다른 학생이 먼저 차지함"
        store.set_application_status(application.id, REJECTED, reason)
        return Decision(REJECTED, reason)

    store.set_application_status(application.id, APPROVED, decision.reason)
    return decision


# =============================================================================
# 마감
# =============================================================================


def close_recruiting(store: Store) -> Decision:
    """모집 마감 단추를 누른 결과 (공고 2.5절 1~2항)."""
    if store.is_closed():
        return Decision(BLOCKED, "이미 마감됨")

    store.set_setting("closed", "1")

    # 마감 때 대기 중인 지원은 거절됨
    for application in store.pending_applications():
        store.set_application_status(application.id, REJECTED, "모집 마감")

    # 1명뿐인 팀의 학생은 팀에서 빠져 "팀이 없는 학생" 이 됨
    for team_no in store.team_numbers():
        members = store.team_members(team_no)
        if len(members) == 1:
            store.remove_member(members[0].student_no)

    return Decision(APPROVED, "모집을 마감함")


# =============================================================================
# 배정
# =============================================================================


def validate_assignment(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
    plan: Mapping[str, int],
) -> list[str]:
    """배정안을 공고 2.5절 4항의 다섯 가지로 검사한다. 통과하면 빈 목록.

    AI 가 낸 배정안과 앱이 스스로 찾은 배정안이 같은 함수를 지나게 하여, AI 의
    그럴듯한 오답이 확정되지 않게 한다.
    """
    problems: list[str] = []
    by_no = {s.student_no: s for s in unassigned}
    unassigned_nos = set(by_no)
    planned_nos = set(plan)

    # 1. 팀이 없는 학생이 빠짐없이 배정됨
    missing = sorted(unassigned_nos - planned_nos)
    if missing:
        names = ", ".join(by_no[no].name for no in missing)
        problems.append(f"배정되지 않은 학생이 있음: {names}")

    # 2. 한 학생은 한 팀에만 배정됨
    #    plan 이 학번을 열쇠로 하는 사전이므로 중복 배정은 구조적으로 불가능하다.
    #    여기서는 이미 팀이 있는 학생을 옮기려는 경우를 막는다 (공고 2.5절 3항).
    extra = sorted(planned_nos - unassigned_nos)
    if extra:
        problems.append(f"팀이 없는 학생이 아닌 학번을 배정함: {', '.join(extra)}")

    unknown_teams = sorted({t for t in plan.values() if t not in teams})
    if unknown_teams:
        problems.append(f"없는 팀에 배정함: {unknown_teams}")

    if problems:
        return problems

    # 3~5. 인원, 주 역할 중복, 필수 포함 역할
    merged = {team_no: list(members) for team_no, members in teams.items()}
    for student_no, team_no in plan.items():
        merged[team_no].append(by_no[student_no])

    return rules.check_final_teams(merged)


def solve_assignment(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
) -> dict[str, int] | None:
    """앱이 스스로 찾는 배정 (공고 3장 "3차 모델까지 실패" 의 어려운 해결).

    공고 2.5절 4항의 검사 다섯 가지를 모두 통과하는 배정을 모든 경우를 따져
    끝까지 찾는다. 없으면 None.

    이미 팀에 있는 학생은 옮기지 않는다 (공고 2.5절 3항).
    """
    team_numbers = sorted(teams)
    if not team_numbers:
        return None

    working = {team_no: list(teams[team_no]) for team_no in team_numbers}

    # 담당 가능 역할이 적은 학생부터 배치한다. 선택지가 좁은 쪽을 먼저 넣으면
    # 막다른 길을 일찍 발견해 탐색이 빨리 끝난다.
    order = sorted(unassigned, key=lambda s: (len(s.capable_roles), s.student_no))
    plan: dict[str, int] = {}

    def still_fillable(team_no: int) -> bool:
        """그 팀이 아직 규칙을 지킬 가능성이 있는지 (가지치기)."""
        members = working[team_no]
        if len(members) > MAX_TEAM_SIZE:
            return False
        if rules.duplicated_main_roles(members):
            return False
        remaining_slots = MAX_TEAM_SIZE - len(members)
        unmet = len(REQUIRED_ROLES) - rules.required_fill_count(members)
        return remaining_slots >= unmet

    def search(index: int) -> bool:
        if index == len(order):
            # 가지치기는 속도를 위한 것이고, 맞는지는 최종 검사가 판정한다.
            return rules.check_final_teams(working) == []

        student = order[index]
        for team_no in team_numbers:
            working[team_no].append(student)
            plan[student.student_no] = team_no

            if still_fillable(team_no) and search(index + 1):
                return True

            working[team_no].pop()
            del plan[student.student_no]
        return False

    return dict(plan) if search(0) else None


def confirm_assignment(store: Store, plan: Mapping[str, int]) -> Decision:
    """배정안 확정 단추를 누른 결과 (공고 2.5절 7항)."""
    if not store.is_closed():
        return Decision(BLOCKED, "모집을 먼저 마감해야 함")

    unassigned = unassigned_students(store)
    problems = validate_assignment(current_teams(store), unassigned, plan)
    if problems:
        return Decision(BLOCKED, "; ".join(problems))

    for student_no, team_no in plan.items():
        try:
            store.add_member(team_no, student_no)
        except (AlreadyInTeam, SlotTaken) as exc:
            return Decision(BLOCKED, f"배정을 저장하지 못함 ({type(exc).__name__})")

    store.set_setting("confirmed", "1")
    return Decision(APPROVED, "배정을 확정함")


def check_confirmed_teams(store: Store) -> list[str]:
    """확정된 팀 구성이 규칙을 지키는지 (공고 6.2절 5항의 마지막 검사)."""
    return rules.check_final_teams(current_teams(store))


def assignment_blockers(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
) -> list[str]:
    """규칙을 지키는 배정이 아예 없을 때 그 이유 (공고 2.5절 8항).

    AI 를 부르기 전에 확인해, 가망이 없으면 호출을 아끼고 이유를 보여 준다.
    """
    reasons: list[str] = []

    seats = sum(MAX_TEAM_SIZE - len(members) for members in teams.values())
    if len(unassigned) > seats:
        reasons.append(
            f"팀이 없는 학생이 {len(unassigned)}명인데 남은 자리는 {seats}개임"
        )

    # 어느 팀도 필수 포함 역할을 채울 수 없는 경우를 찾는다.
    pool = list(unassigned)
    for team_no in sorted(teams):
        members = list(teams[team_no])
        remaining_slots = MAX_TEAM_SIZE - len(members)
        unmet = len(REQUIRED_ROLES) - rules.required_fill_count(members)
        if unmet == 0:
            continue
        if remaining_slots < unmet:
            reasons.append(
                f"팀{team_no}은 남은 자리가 {remaining_slots}개인데 "
                f"채워야 할 필수 포함 역할이 {unmet}개임"
            )
            continue
        problem = rules.required_role_problem([*members, *pool], f"팀{team_no}")
        if problem:
            reasons.append(problem)

    return reasons
