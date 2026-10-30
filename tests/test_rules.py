"""규칙 엔진 테스트.

공고 2.3절(팀 규칙), 2.4절(지원과 투표), 3장(필수 포함 역할 자리 계산)을 검증한다.
시나리오에서 가져온 사례는 어느 단계인지 주석으로 남긴다.
"""

from __future__ import annotations

from app import rules
from app.roles import PLANNER, PRESENTER, REPORTER, TESTER, WEB_DEV

from conftest import make_student


# =============================================================================
# 담당 가능 역할 (공고 2.3절)
# =============================================================================


def test_capable_roles_is_main_plus_sub(easy):
    학생1 = easy["학생1(PL;RW)"]
    assert 학생1.capable_roles == frozenset({PLANNER, REPORTER})


def test_capable_roles_with_two_sub_roles(easy):
    학생8 = easy["학생8(TT;RW;PT)"]
    assert 학생8.capable_roles == frozenset({TESTER, REPORTER, PRESENTER})


def test_capable_roles_with_no_sub_role(easy):
    학생5 = easy["학생5(WP)"]
    assert 학생5.capable_roles == frozenset({WEB_DEV})


# =============================================================================
# 필수 포함 역할 충족수 (공고 2.3절, 3장)
#
# 기획자와 웹 프로그래머는 서로 다른 학생이 맡아야 하므로, 한 학생이 둘 다 할 수
# 있어도 하나로만 센다.
# =============================================================================


def test_fill_count_is_zero_when_nobody_can_take_required_roles(hard):
    # 어려움 10단계 직후의 팀3
    members = [hard["학생11(TT;PT)"], hard["학생15(PT;FD)"]]
    assert rules.required_fill_count(members) == 0


def test_fill_count_is_one_when_a_single_student_can_do_both():
    """공고 3장의 예: 주 역할 기획자 + 보조 역할 웹 프로그래머인 학생 혼자인 팀은
    필수 포함 역할 2개 가운데 1개만 채운 것이다."""
    혼자 = make_student("2026999", "학생99(PL;WP)")
    assert rules.required_fill_count([혼자]) == 1


def test_fill_count_is_two_when_two_different_students_cover_each_role(hard):
    # 어려움 2단계 직후의 팀1
    members = [hard["학생1(PL;RW)"], hard["학생4(WP;PL)"]]
    assert rules.required_fill_count(members) == 2


def test_fill_count_counts_sub_role_as_valid(hard):
    """학생9 는 주 역할이 프론트엔드 디자이너지만 보조 역할로 웹 프로그래머를 맡을
    수 있다."""
    members = [hard["학생12(TT;PL)"], hard["학생9(FD;WP)"]]
    assert rules.required_fill_count(members) == 2


def test_fill_count_is_one_when_only_one_required_role_is_covered(easy):
    members = [easy["학생1(PL;RW)"], easy["학생3(PL;TT)"]]
    assert rules.required_fill_count(members) == 1


# =============================================================================
# 지원 게이트 (공고 2.4절)
# =============================================================================


def test_apply_approved_immediately_on_empty_team(easy):
    # 쉬움 1단계
    decision = rules.check_apply(easy["학생1(PL;RW)"], [])
    assert decision.outcome == "승인"
    assert decision.message.startswith("승인")


def test_apply_pending_when_team_has_members(easy):
    # 쉬움 2단계
    decision = rules.check_apply(easy["학생4(WP;FD)"], [easy["학생1(PL;RW)"]])
    assert decision.outcome == "대기"


def test_apply_blocked_when_recruiting_closed(medium):
    # 중간 10단계
    decision = rules.check_apply(
        medium["학생2(PL;TT)"], [medium["학생3(PL;RW)"]], closed=True
    )
    assert decision.outcome == "막힘"
    assert decision.message == "막힘: 모집이 마감됨"


def test_apply_blocked_when_student_already_has_team(easy):
    decision = rules.check_apply(easy["학생1(PL;RW)"], [], has_team=True)
    assert decision.outcome == "막힘"
    assert decision.message == "막힘: 이미 팀이 있음"


def test_apply_blocked_when_a_pending_application_exists(medium):
    # 중간 8단계 후반: 학생12 가 팀4 지원 결과를 기다리는 중에 팀3 에 지원
    decision = rules.check_apply(
        medium["학생12(PT;RW;FD)"],
        [medium["학생3(PL;RW)"]],
        has_pending=True,
    )
    assert decision.outcome == "막힘"
    assert decision.message == "막힘: 결과를 기다리는 지원이 있음"


def test_apply_blocked_when_team_is_full(hard):
    members = [
        hard["학생1(PL;RW)"],
        hard["학생4(WP;PL)"],
        hard["학생7(FD;PT;TT)"],
        hard["학생10(TT;RW)"],
    ]
    decision = rules.check_apply(hard["학생16(PT)"], members)
    assert decision.outcome == "막힘"
    assert decision.message == "막힘: 팀이 꽉 참"


def test_apply_blocked_on_duplicate_main_role(medium):
    """중간 3단계. 팀1 에 주 역할 기획자인 학생1 이 있는데 학생2 도 기획자다."""
    members = [medium["학생1(PL;PT;TT)"], medium["학생5(WP;TT)"]]
    decision = rules.check_apply(medium["학생2(PL;TT)"], members)
    assert decision.outcome == "막힘"
    assert decision.message == "막힘: 같은 주 역할의 팀원이 있음"


def test_duplicate_main_role_ignores_sub_roles(medium):
    """보조 역할이 겹치는 것은 중복이 아니다. 학생1 과 학생5 는 보조 역할이 둘 다
    테스터지만 주 역할은 다르므로 같은 팀에 있을 수 있다."""
    decision = rules.check_apply(medium["학생5(WP;TT)"], [medium["학생1(PL;PT;TT)"]])
    assert decision.outcome == "대기"


# =============================================================================
# 필수 포함 역할 자리 (공고 3장) — 어려운 해결
#
# 남는자리 < 미충족  →  막힘
#
# 아래 두 테스트가 서로를 검증하는 쌍이다. 부등식이 아니라 "필수 역할이 없으면
# 막는다" 로 구현하면 두 번째 테스트가 깨진다.
# =============================================================================


def test_apply_blocked_when_required_role_slots_run_short(hard):
    """어려움 11단계. 팀3 은 학생11·학생15 뿐이라 기획자도 웹 프로그래머도 없는데,
    학생14 도 둘 다 못 맡는다. 들어가면 남는자리 1 로 미충족 2 를 채울 수 없다."""
    members = [hard["학생11(TT;PT)"], hard["학생15(PT;FD)"]]
    decision = rules.check_apply(hard["학생14(RW;TT)"], members)
    assert decision.outcome == "막힘"
    assert decision.message == "막힘: 필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_apply_allowed_when_remaining_slots_exactly_cover_unmet_roles(medium):
    """중간 8단계. 팀4 는 학생11(RW) 혼자라 충족수 0 이지만, 학생12 가 들어가도
    남는자리가 2 이므로 아직 두 자리로 두 역할을 채울 수 있다. 막지 않는다."""
    members = [medium["학생11(RW)"]]
    decision = rules.check_apply(medium["학생12(PT;RW;FD)"], members)
    assert decision.outcome == "대기"


def test_apply_blocked_on_third_member_without_required_roles():
    """공고 3장의 예: 테스터와 발표자만 있는 팀(2명)에 보고서 작성자가 지원하면,
    남는 자리 1개로 필수 포함 역할 2개를 채울 수 없으므로 막는다."""
    members = [make_student("2026901", "학생91(TT)"), make_student("2026902", "학생92(PT)")]
    지원자 = make_student("2026903", "학생93(RW)")
    decision = rules.check_apply(지원자, members)
    assert decision.outcome == "막힘"
    assert decision.message == "막힘: 필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_apply_allowed_when_applicant_fills_the_last_unmet_role(hard):
    """어려움 3단계. 팀1 은 기획자·웹 프로그래머가 이미 다 있으므로 네 번째
    자리와 무관하게 통과한다."""
    members = [hard["학생1(PL;RW)"], hard["학생4(WP;PL)"]]
    decision = rules.check_apply(hard["학생7(FD;PT;TT)"], members)
    assert decision.outcome == "대기"


def test_block_order_puts_closed_before_other_reasons(hard):
    """여러 사유가 겹치면 모집 마감이 먼저 안내된다."""
    members = [
        hard["학생1(PL;RW)"],
        hard["학생4(WP;PL)"],
        hard["학생7(FD;PT;TT)"],
        hard["학생10(TT;RW)"],
    ]
    decision = rules.check_apply(hard["학생16(PT)"], members, closed=True)
    assert decision.message == "막힘: 모집이 마감됨"


# =============================================================================
# 승인 직전 재검사 (공고 2.4절) — 어려운 해결
# =============================================================================


def test_recheck_approves_when_team_is_still_valid(hard):
    """어려움 7단계. 팀2 가 학생2·학생8 일 때 학생5 를 승인한다."""
    members = [hard["학생2(PL;PT)"], hard["학생8(FD;TT)"]]
    decision = rules.check_before_approval(hard["학생5(WP;FD)"], members)
    assert decision.outcome == "승인"


def test_recheck_rejects_when_main_role_became_duplicated(hard):
    """어려움 8단계. 학생5(WP) 가 먼저 승인되어 팀2 에 들어갔으므로, 뒤이어
    승인하려는 학생6(WP) 은 주 역할이 중복되어 거절된다."""
    members = [hard["학생2(PL;PT)"], hard["학생8(FD;TT)"], hard["학생5(WP;FD)"]]
    decision = rules.check_before_approval(hard["학생6(WP;RW)"], members)
    assert decision.outcome == "거절"
    assert decision.message == "거절: 같은 주 역할의 팀원이 있음"


def test_recheck_rejects_when_team_became_full(hard):
    members = [
        hard["학생1(PL;RW)"],
        hard["학생4(WP;PL)"],
        hard["학생7(FD;PT;TT)"],
        hard["학생10(TT;RW)"],
    ]
    decision = rules.check_before_approval(hard["학생16(PT)"], members)
    assert decision.outcome == "거절"
    assert decision.message == "거절: 팀이 꽉 참"


def test_recheck_rejects_when_required_role_slots_run_short(hard):
    members = [hard["학생11(TT;PT)"], hard["학생15(PT;FD)"]]
    decision = rules.check_before_approval(hard["학생14(RW;TT)"], members)
    assert decision.outcome == "거절"
    assert decision.message == "거절: 필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_recheck_does_not_consider_pending_or_closed_state(hard):
    """재검사는 팀의 현재 구성만 본다. 접수 시점 조건(마감, 이미 팀 있음, 대기 중
    지원 있음)은 다시 보지 않는다."""
    decision = rules.check_before_approval(hard["학생4(WP;PL)"], [hard["학생1(PL;RW)"]])
    assert decision.outcome == "승인"


# =============================================================================
# 확정 팀 구성 검사 (공고 2.3절, 2.5절 4항)
# =============================================================================


def test_final_check_passes_on_valid_teams(easy):
    teams = {
        1: [easy["학생1(PL;RW)"], easy["학생4(WP;FD)"]],
        2: [easy["학생2(PL;PT)"], easy["학생5(WP)"]],
        3: [easy["학생3(PL;TT)"], easy["학생6(WP;TT)"]],
    }
    assert rules.check_final_teams(teams) == []


def test_final_check_flags_team_with_fewer_than_two_members(easy):
    teams = {1: [easy["학생1(PL;RW)"]], 2: [easy["학생2(PL;PT)"], easy["학생5(WP)"]]}
    problems = rules.check_final_teams(teams)
    assert any("팀1" in p and "2~4명" in p for p in problems)


def test_final_check_flags_empty_team(easy):
    teams = {1: [easy["학생1(PL;RW)"], easy["학생4(WP;FD)"]], 2: []}
    problems = rules.check_final_teams(teams)
    assert any("팀2" in p for p in problems)


def test_final_check_flags_team_over_four_members(hard):
    teams = {
        1: [
            hard["학생1(PL;RW)"],
            hard["학생4(WP;PL)"],
            hard["학생7(FD;PT;TT)"],
            hard["학생10(TT;RW)"],
            hard["학생13(RW;PT;FD)"],
        ]
    }
    problems = rules.check_final_teams(teams)
    assert any("팀1" in p and "2~4명" in p for p in problems)


def test_final_check_flags_duplicate_main_role(easy):
    teams = {1: [easy["학생1(PL;RW)"], easy["학생2(PL;PT)"]]}
    problems = rules.check_final_teams(teams)
    assert any("팀1" in p and "주 역할" in p for p in problems)


def test_final_check_flags_missing_required_role(hard):
    """팀3 에 기획자도 웹 프로그래머도 없다."""
    teams = {3: [hard["학생11(TT;PT)"], hard["학생15(PT;FD)"]]}
    problems = rules.check_final_teams(teams)
    assert any("팀3" in p and "기획자" in p for p in problems)


def test_final_check_rejects_one_person_covering_both_required_roles():
    """기획자와 웹 프로그래머는 서로 다른 사람이어야 한다."""
    teams = {
        1: [make_student("2026991", "학생91(PL;WP)"), make_student("2026992", "학생92(TT)")]
    }
    problems = rules.check_final_teams(teams)
    assert any("팀1" in p for p in problems)
