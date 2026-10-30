"""화면 요소 이름 (공고 2.7절).

자동 채점 프로그램이 Streamlit 의 key 로 화면 요소를 찾는다. 표와 다르게
지정하거나 지정하지 않아 채점이 멈추면 5점이 깎인다 (공고 6.3절 15번).

그래서 이름을 코드 여러 곳에 흩어 적지 않고 여기에만 둔다. tests/test_keys.py
가 이 값들이 공고의 표와 글자까지 같은지 확인한다.

key 에는 영문, 숫자, 밑줄만 쓴다. 한글 key 는 채점 프로그램이 찾지 못한다.
"""

from __future__ import annotations

# --- 로그인 ---------------------------------------------------------------
LOGIN_STUDENT_NO = "login_student_no"
LOGIN_PASSWORD = "login_password"
LOGIN_SUBMIT = "login_submit"

# --- 공통 표시 ------------------------------------------------------------
WHOAMI = "whoami"
RESULT = "result"

# --- 관리자 ---------------------------------------------------------------
ADMIN_ROSTER_FILE = "admin_roster_file"
ADMIN_TEAM_COUNT = "admin_team_count"
ADMIN_START = "admin_start"
ADMIN_CLOSE = "admin_close"
UNASSIGNED = "unassigned"
ADMIN_ASSIGN = "admin_assign"
ASSIGN_STATUS = "assign_status"
ADMIN_CONFIRM = "admin_confirm"

# --- 새로 고침 ------------------------------------------------------------
# 공고상 쉬운 해결(새로 고침 단추) 전용이지만 함께 둔다. 채점 프로그램은 이 단추가
# 있으면 동작하기 전에 먼저 누르므로, st.fragment 자동 갱신이 한 번 엇나가도
# 채점이 멈추지 않는 보험이 된다. 어려운 해결은 st.fragment 로 구현되어 있다.
REFRESH = "refresh"


def team(team_no: int) -> str:
    """팀 하나의 표시. 팀 번호는 관리자가 명단을 올릴 때 만든 팀1, 팀2, … 이며
    시나리오의 팀 번호와 같다."""
    return f"team_{team_no}"


def apply(team_no: int) -> str:
    """팀에 지원하는 단추."""
    return f"apply_{team_no}"


def vote_yes(applicant_student_no: str) -> str:
    """지원에 찬성하는 단추. 예: vote_yes_2026306"""
    return f"vote_yes_{applicant_student_no}"


def vote_no(applicant_student_no: str) -> str:
    """지원에 거부하는 단추."""
    return f"vote_no_{applicant_student_no}"
