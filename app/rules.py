"""팀 구성 규칙 엔진.

이 모듈은 DB도 Streamlit도 모르는 순수 함수만 담는다. 덕분에 Supabase와
오픈라우터 키 없이 부록 시나리오 전 단계를 테스트로 재현할 수 있다
(docs/구현 계획.md 1.1절).

공고 근거
  2.3절  팀 규칙 (인원, 주 역할 중복, 필수 포함 역할)
  2.4절  지원과 투표 (막힘 사유, 승인 직전 재검사)
  3장    필수 포함 역할 자리 계산
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from .roles import PLANNER, REQUIRED_ROLES, WEB_DEV

#: 공고 2.3절 인원 규칙
MIN_TEAM_SIZE = 2
MAX_TEAM_SIZE = 4

#: 결과 안내의 첫 단어 (공고 2.7절). 채점 프로그램이 이 단어로 판정한다.
APPROVED = "승인"
PENDING = "대기"
REJECTED = "거절"
BLOCKED = "막힘"


@dataclass(frozen=True)
class Student:
    """명단 CSV 한 줄에 대응하는 학생.

    주 역할은 팀 안의 중복을 따지는 기준이고, 보조 역할은 필수 포함 역할을 맡을
    수 있는지 따질 때만 쓴다 (공고 2.3절). 두 용도를 섞지 않는다.
    """

    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...] = ()

    @property
    def capable_roles(self) -> frozenset[str]:
        """담당 가능 역할 = 주 역할 ∪ 보조 역할."""
        return frozenset((self.main_role, *self.sub_roles))

    def can_take(self, role: str) -> bool:
        return role in self.capable_roles


@dataclass(frozen=True)
class Decision:
    """동작 하나의 판정 결과.

    message 가 화면의 result 컨테이너에 그대로 들어간다. 첫 단어는 반드시
    승인·대기·거절·막힘 중 하나다 (공고 2.7절).
    """

    outcome: str
    reason: str

    @property
    def message(self) -> str:
        return f"{self.outcome}: {self.reason}"

    @property
    def blocked(self) -> bool:
        return self.outcome == BLOCKED


# =============================================================================
# 필수 포함 역할
# =============================================================================


def required_fill_count(members: Sequence[Student]) -> int:
    """팀원이 필수 포함 역할 2개 가운데 몇 개를 채웠는지 센다 (0, 1, 2).

    기획자와 웹 프로그래머는 서로 다른 학생이 맡아야 하므로, 한 학생이 둘 다
    담당 가능해도 하나로만 센다 (공고 3장). 팀원 집합과 두 역할 사이의 최대
    이분 매칭 크기이며, 역할이 2개뿐이라 경우를 직접 따진다.
    """
    planners = {s.student_no for s in members if s.can_take(PLANNER)}
    web_devs = {s.student_no for s in members if s.can_take(WEB_DEV)}

    if not planners and not web_devs:
        return 0
    # 양쪽이 비어 있지 않고 서로 다른 두 사람을 뽑을 수 있으면 둘 다 채운 것이다.
    if planners and web_devs and len(planners | web_devs) >= 2:
        return 2
    return 1


def required_role_problem(members: Sequence[Student], label: str) -> str | None:
    """팀이 필수 포함 역할을 못 채우는 이유. 채웠으면 None."""
    planners = [s for s in members if s.can_take(PLANNER)]
    web_devs = [s for s in members if s.can_take(WEB_DEV)]

    if not planners and not web_devs:
        return f"{label}에 기획자와 웹 프로그래머를 맡을 학생이 없음"
    if not planners:
        return f"{label}에 기획자를 맡을 학생이 없음"
    if not web_devs:
        return f"{label}에 웹 프로그래머를 맡을 학생이 없음"
    if required_fill_count(members) < len(REQUIRED_ROLES):
        return f"{label}의 기획자와 웹 프로그래머를 서로 다른 학생이 맡을 수 없음"
    return None


def duplicated_main_roles(members: Sequence[Student]) -> list[str]:
    """한 팀에 2명 이상인 주 역할 목록."""
    counts = Counter(s.main_role for s in members)
    return sorted(role for role, n in counts.items() if n > 1)


# =============================================================================
# 지원 게이트
# =============================================================================


def _structural_block(applicant: Student, members: Sequence[Student]) -> str | None:
    """팀의 현재 구성만 보고 지원을 막아야 하는 이유. 없으면 None.

    지원 접수(check_apply)와 승인 직전 재검사(check_before_approval)가 같은
    함수를 쓴다. 두 시점의 판정이 어긋나지 않게 하려는 것이다.
    """
    if len(members) >= MAX_TEAM_SIZE:
        return "팀이 꽉 참"

    if any(m.main_role == applicant.main_role for m in members):
        return "같은 주 역할의 팀원이 있음"

    # 필수 포함 역할 자리 계산 (공고 3장, 어려운 해결)
    #
    #   남는자리 < 미충족  →  막힘
    #
    # 부등식이어야 한다. 미충족이 2 라도 남는자리가 2 면 아직 두 자리로 두 역할을
    # 채울 수 있으므로 막지 않는다.
    prospective = [*members, applicant]
    remaining_slots = MAX_TEAM_SIZE - len(prospective)
    unmet = len(REQUIRED_ROLES) - required_fill_count(prospective)
    if remaining_slots < unmet:
        return "필수 포함 역할을 맡을 학생의 자리가 모자람"

    return None


def check_apply(
    applicant: Student,
    members: Sequence[Student],
    *,
    closed: bool = False,
    has_team: bool = False,
    has_pending: bool = False,
) -> Decision:
    """지원 단추를 누른 결과 (공고 2.4절).

    검사 순서가 곧 안내 문구의 우선순위다. 앞의 세 가지는 2.8절에 따라 단추를
    숨기거나 비활성화하는 사유이기도 하다.
    """
    if closed:
        return Decision(BLOCKED, "모집이 마감됨")
    if has_team:
        return Decision(BLOCKED, "이미 팀이 있음")
    if has_pending:
        return Decision(BLOCKED, "결과를 기다리는 지원이 있음")

    reason = _structural_block(applicant, members)
    if reason:
        return Decision(BLOCKED, reason)

    if not members:
        return Decision(APPROVED, "빈 팀이라 바로 승인됨")
    return Decision(PENDING, "팀원의 투표를 기다림")


def check_before_approval(applicant: Student, members: Sequence[Student]) -> Decision:
    """승인 직전 재검사 (공고 2.4절, 3장의 어려운 해결).

    모든 팀원이 찬성해 승인하려는 순간에 규칙을 다시 본다. 같은 팀에 대기 중인
    지원이 여럿일 때 앞의 지원이 먼저 승인되어 팀 구성이 바뀌기 때문이다.

    접수 시점 조건(마감, 이미 팀 있음, 대기 중 지원)은 다시 보지 않는다.
    """
    reason = _structural_block(applicant, members)
    if reason:
        return Decision(REJECTED, reason)
    return Decision(APPROVED, "팀에 들어감")


# =============================================================================
# 확정 팀 구성 검사
# =============================================================================


def check_final_teams(teams: Mapping[int, Sequence[Student]]) -> list[str]:
    """확정하려는 팀 구성의 위반 사유 목록. 비어 있으면 규칙을 모두 지킨 것이다.

    공고 2.5절 4항 검사의 3·4·5번(인원, 주 역할 중복, 필수 포함 역할)에 해당한다.
    """
    problems: list[str] = []

    for team_no in sorted(teams):
        members = teams[team_no]
        label = f"팀{team_no}"

        if not MIN_TEAM_SIZE <= len(members) <= MAX_TEAM_SIZE:
            problems.append(
                f"{label}의 인원이 {len(members)}명임 "
                f"({MIN_TEAM_SIZE}~{MAX_TEAM_SIZE}명이어야 함)"
            )

        for role in duplicated_main_roles(members):
            problems.append(f"{label}에 주 역할이 {role}인 학생이 2명 이상임")

        problem = required_role_problem(members, label)
        if problem:
            problems.append(problem)

    return problems
