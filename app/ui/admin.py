"""관리자 화면 (공고 2.1절, 2.5절, 2.6절).

명단 올리기는 fragment 밖에 둔다. 5초마다 자동으로 다시 그리면 파일 올리기가
중간에 끊길 수 있기 때문이다. fragment 밖의 단추를 누르면 앱 전체가 다시 그려져
fragment 안의 결과 안내도 함께 갱신된다.

AI 배정은 최대 6분(모델 3개 × 120초) 동안 화면을 붙잡는다. 그동안 몇 차 모델을
기다리는지 assign_status 에 보여 준다 (공고 3장의 어려운 해결).
"""

from __future__ import annotations

import streamlit as st

from .. import assign, auth, config, flow, repo
from ..roster import RosterError, parse_roster
from ..rules import MAX_TEAM_SIZE
from . import common, keys

_OUTCOME = "_assign_outcome"
_STATUS = "_assign_status"

MIN_TEAMS = 1
MAX_TEAMS = 12


def render() -> None:
    _render_roster_form()
    _live_area()


# =============================================================================
# 명단 올리기 (fragment 밖)
# =============================================================================


def _render_roster_form() -> None:
    st.subheader("명단 올리기")
    st.caption(
        "명단 CSV 와 팀 수를 넣으면 지원·투표·팀원·마감 표시를 모두 지우고 "
        "처음 상태를 만듭니다."
    )

    uploaded = st.file_uploader(
        "명단 CSV", type=["csv"], key=keys.ADMIN_ROSTER_FILE
    )
    team_count = st.number_input(
        "팀 수",
        min_value=MIN_TEAMS,
        max_value=MAX_TEAMS,
        value=3,
        step=1,
        key=keys.ADMIN_TEAM_COUNT,
    )

    if not st.button("명단으로 처음 상태 만들기", key=keys.ADMIN_START):
        return

    if uploaded is None:
        common.set_result("막힘: 명단 CSV 를 올려야 함")
        st.rerun()
        return

    try:
        students = parse_roster(uploaded.getvalue())
    except RosterError as exc:
        common.set_result(f"막힘: {exc}")
        st.rerun()
        return

    # 학생의 비밀번호는 모두 같으므로 해시를 한 번만 계산한다 (app/store.py 참고).
    password_hash = auth.hash_password(auth.STUDENT_PASSWORD)
    with repo.open_store() as store:
        store.replace_roster(students, int(team_count), password_hash)

    st.session_state.pop(_OUTCOME, None)
    st.session_state.pop(_STATUS, None)
    common.set_result(
        f"승인: 학생 {len(students)}명과 빈 팀 {int(team_count)}개로 "
        "처음 상태를 만듦"
    )
    st.rerun()


# =============================================================================
# 마감·배정·확정 (fragment 안, 5초마다 자동 갱신)
# =============================================================================


@st.fragment(run_every=common.REFRESH_SECONDS)
def _live_area() -> None:
    with repo.open_store() as store:
        closed = store.is_closed()
        confirmed = store.setting("confirmed") == "1"
        teams = flow.current_teams(store)
        unassigned = flow.unassigned_students(store)

    common.render_result()
    common.render_refresh_button()

    _render_close(closed)
    _render_unassigned(unassigned)
    _render_assign_status()
    _render_assign_button(closed)
    _render_confirm_button()
    _render_teams(teams, confirmed)


def _render_close(closed: bool) -> None:
    st.subheader("모집")
    st.write("마감됨" if closed else "모집 중")

    if st.button("모집 마감", key=keys.ADMIN_CLOSE, disabled=closed):
        with repo.open_store() as store:
            decision = flow.close_recruiting(store)
        common.set_result(decision.message)
        st.rerun(scope="fragment")


def _render_unassigned(unassigned) -> None:
    """key 가 unassigned 인 컨테이너. 팀이 없는 학생의 이름을 보여 준다.

    마감 때 대기 지원이 거절되고 1명뿐인 팀의 학생이 빠진 결과를 채점자가 이
    표시로 확인한다 (공고 2.7절).
    """
    st.subheader("팀이 없는 학생")
    with st.container(key=keys.UNASSIGNED, border=True):
        if not unassigned:
            st.caption("없음")
            return
        for student in unassigned:
            st.write(f"- {student.name} — {common.describe_roles(student)}")


def _render_assign_status() -> None:
    """key 가 assign_status 인 컨테이너.

    AI 배정 진행 안내와, 규칙을 지키는 배정이 없을 때의 이유를 보여 준다
    (공고 2.7절, 2.5절 8항).

    단추보다 먼저 그려야 한다. 배정하는 동안 이 안에 진행 상황을 써 넣기
    때문이다.
    """
    st.subheader("AI 배정 진행")
    container = st.container(key=keys.ASSIGN_STATUS, border=True)
    with container:
        slot = st.empty()
        stored = st.session_state.get(_STATUS)
        if stored:
            slot.write(stored)
        else:
            slot.caption("아직 배정하지 않았습니다.")
    st.session_state["_status_slot"] = slot


def _render_assign_button(closed: bool) -> None:
    if not st.button("AI 배정", key=keys.ADMIN_ASSIGN):
        return

    if not closed:
        common.set_result("막힘: 모집을 먼저 마감해야 함")
        st.rerun(scope="fragment")
        return

    slot = st.session_state.get("_status_slot")
    lines: list[str] = []

    def on_progress(attempt_no: int, model: str, elapsed: float) -> None:
        text = f"{attempt_no}차 모델의 응답을 기다리는 중 ({elapsed:.0f}초 경과)"
        if slot is not None:
            slot.info(text)

    with repo.open_store() as store:
        outcome = assign.propose_assignment(
            store,
            api_key=config.openrouter_api_key(),
            models=config.ai_models(),
            on_progress=on_progress,
        )
        store.log_ai_attempts(outcome.attempts)

    for attempt in outcome.attempts:
        detail = f" — {attempt.detail}" if attempt.detail else ""
        lines.append(
            f"{attempt.attempt_no}차 {attempt.model}: {attempt.status} "
            f"({attempt.elapsed_ms / 1000:.1f}초){detail}"
        )

    if outcome.plan is None:
        lines.append("규칙을 지키는 배정이 없음")
        lines.extend(f"- {problem}" for problem in outcome.problems)
        st.session_state[_STATUS] = "\n\n".join(lines)
        st.session_state.pop(_OUTCOME, None)
        common.set_result("막힘: 규칙을 지키는 배정이 없음")
        st.rerun(scope="fragment")
        return

    lines.append(f"배정안 출처: {outcome.source}")
    st.session_state[_STATUS] = "\n\n".join(lines)
    st.session_state[_OUTCOME] = outcome
    common.set_result(f"승인: 배정안을 만듦 ({outcome.source})")
    st.rerun(scope="fragment")


def _plan_rows(plan: dict[str, int]) -> list[dict[str, str]]:
    """확정하려는 배정안을 표로 보여 줄 행. 학생의 이름과 역할, 배정된 팀
    (공고 2.5절 7항)."""
    rows: list[dict[str, str]] = []
    with repo.open_store() as store:
        for student_no, team_no in sorted(plan.items(), key=lambda item: item[1]):
            student = store.student(student_no)
            rows.append(
                {
                    "학번": student_no,
                    "이름": student.name if student else "(알 수 없음)",
                    "역할": common.describe_roles(student) if student else "",
                    "배정된 팀": f"팀{team_no}",
                }
            )
    return rows


def _render_confirm_button() -> None:
    outcome = st.session_state.get(_OUTCOME)

    if outcome is not None and outcome.plan:
        st.write("확정하려는 배정안")
        st.dataframe(_plan_rows(outcome.plan), hide_index=True)

    if not st.button("배정안 확정", key=keys.ADMIN_CONFIRM):
        return

    if outcome is None or outcome.plan is None:
        common.set_result("막힘: 확정할 배정안이 없음. AI 배정을 먼저 누르세요")
        st.rerun(scope="fragment")
        return

    with repo.open_store() as store:
        decision = flow.confirm_assignment(store, outcome.plan)

    common.set_result(decision.message)
    if decision.outcome == "승인":
        st.session_state.pop(_OUTCOME, None)
        st.session_state[_STATUS] = (
            st.session_state.get(_STATUS, "") + "\n\n확정됨"
        ).strip()
    st.rerun(scope="fragment")


def _render_teams(teams, confirmed: bool) -> None:
    st.subheader("팀 구성")
    if confirmed:
        st.success("배정이 확정되었습니다.")

    for team_no in sorted(teams):
        members = teams[team_no]
        with st.container(key=keys.team(team_no), border=True):
            st.markdown(f"**팀{team_no} ({len(members)}/{MAX_TEAM_SIZE}명)**")
            if members:
                for member in members:
                    st.write(f"- {member.name} — {common.describe_roles(member)}")
            else:
                st.caption("아직 팀원이 없습니다.")
