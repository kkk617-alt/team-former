"""학생 화면 (공고 2.8절).

화면 전체가 하나의 st.fragment 안에 있고 5초마다 다시 그려진다. 다른 학생의
지원이나 투표가 화면을 다시 열지 않아도 나타난다 (공고 3장의 어려운 해결).

결과 안내(result)도 같은 fragment 안에 둔다. fragment 안의 단추를 누르면 그
fragment 만 다시 그려지므로, 안내가 밖에 있으면 갱신되지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from .. import flow, repo
from ..rules import MAX_TEAM_SIZE, Student
from ..store import Application, Store
from . import common, keys

AGREE = "찬성"
REFUSE = "거부"


@dataclass
class Snapshot:
    """화면 한 번 그리는 데 필요한 값을 한 트랜잭션에서 모아 온다."""

    closed: bool
    my_team_no: int | None
    my_pending: Application | None
    teams: dict[int, list[Student]] = field(default_factory=dict)
    #: 내 팀에 들어온 대기 중인 지원 [(지원, 지원자)]
    incoming: list[tuple[Application, Student]] = field(default_factory=list)
    #: {지원 id: 내가 한 투표}
    my_votes: dict[int, str] = field(default_factory=dict)


def _read(store: Store, student_no: str) -> Snapshot:
    my_team_no = store.team_of(student_no)
    snapshot = Snapshot(
        closed=store.is_closed(),
        my_team_no=my_team_no,
        my_pending=store.pending_application_of(student_no),
        teams=flow.current_teams(store),
    )

    if my_team_no is not None:
        # 지원·지원자·내 투표를 한 번에 가져온다. 지원마다 따로 물으면 왕복이
        # 지원 수의 두 배가 되어 화면이 느려진다 (공고 4.2절).
        for application, applicant, vote in store.incoming_applications(
            my_team_no, student_no
        ):
            snapshot.incoming.append((application, applicant))
            if vote is not None:
                snapshot.my_votes[application.id] = vote

    return snapshot


@st.fragment(run_every=common.REFRESH_SECONDS)
def render() -> None:
    account = common.current_account()
    if account is None or account.student is None:
        return
    student_no = account.student.student_no

    with repo.open_store() as store:
        snapshot = _read(store, student_no)

    common.render_result()
    common.render_refresh_button()

    _render_my_state(snapshot)
    _render_incoming_votes(snapshot, student_no)
    _render_teams(snapshot, student_no)


# =============================================================================
# 내 상태
# =============================================================================


def _render_my_state(snapshot: Snapshot) -> None:
    if snapshot.closed:
        st.info("모집이 마감되었습니다.")

    if snapshot.my_team_no is not None:
        st.success(f"내 팀: 팀{snapshot.my_team_no}")
    elif snapshot.my_pending is not None:
        st.warning(
            f"팀{snapshot.my_pending.team_no} 지원 결과를 기다리는 중입니다. "
            "결과가 나오기 전에는 다른 팀에 지원할 수 없습니다."
        )
    else:
        st.warning("아직 팀이 없음")


# =============================================================================
# 내 팀에 들어온 지원에 투표
# =============================================================================


def _render_incoming_votes(snapshot: Snapshot, student_no: str) -> None:
    if snapshot.my_team_no is None:
        return

    st.subheader("내 팀에 들어온 지원")
    if not snapshot.incoming:
        st.caption("대기 중인 지원이 없습니다.")
        return

    for application, applicant in snapshot.incoming:
        with st.container(border=True):
            st.write(f"**{applicant.name}** — {common.describe_roles(applicant)}")

            my_vote = snapshot.my_votes.get(application.id)
            if my_vote is not None:
                # 이미 투표한 지원은 단추를 숨기고 내 투표를 보여 준다 (공고 2.8절)
                st.write(f"내 투표: {my_vote}")
                continue
            if snapshot.closed:
                st.caption("모집이 마감되어 투표할 수 없습니다.")
                continue

            yes, no = st.columns(2)
            with yes:
                if st.button("찬성", key=keys.vote_yes(applicant.student_no)):
                    _vote(student_no, applicant.student_no, AGREE)
            with no:
                if st.button("거부", key=keys.vote_no(applicant.student_no)):
                    _vote(student_no, applicant.student_no, REFUSE)


def _vote(voter_no: str, applicant_no: str, vote: str) -> None:
    with repo.open_store() as store:
        decision = flow.cast_vote(store, voter_no, applicant_no, vote)
    common.set_result(decision.message)
    st.rerun(scope="fragment")


# =============================================================================
# 팀 목록
# =============================================================================


def _render_teams(snapshot: Snapshot, student_no: str) -> None:
    st.subheader("팀 목록")

    # 지원 단추를 숨기거나 비활성화해야 하는 경우 (공고 2.8절)
    cannot_apply = (
        snapshot.closed
        or snapshot.my_team_no is not None
        or snapshot.my_pending is not None
    )

    for team_no in sorted(snapshot.teams):
        members = snapshot.teams[team_no]
        mine = team_no == snapshot.my_team_no

        with st.container(key=keys.team(team_no), border=True):
            title = f"팀{team_no} ({len(members)}/{MAX_TEAM_SIZE}명)"
            if mine:
                title += " — 내 팀"
            st.markdown(f"**{title}**")

            if members:
                for member in members:
                    st.write(f"- {member.name} — {common.describe_roles(member)}")
            else:
                st.caption("아직 팀원이 없습니다.")

            if cannot_apply:
                continue

            if st.button("지원", key=keys.apply(team_no)):
                _apply(student_no, team_no)


def _apply(student_no: str, team_no: int) -> None:
    with repo.open_store() as store:
        decision = flow.apply_to_team(store, student_no, team_no)
    common.set_result(decision.message)
    st.rerun(scope="fragment")
