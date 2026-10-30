"""화면 공통 부분: 로그인, 로그인한 사람 표시, 결과 안내.

결과 안내(result)는 st.session_state 에 보관한다. st.fragment 가 5초마다 화면을
다시 그리므로, 지역 변수에 두면 다음 갱신에서 사라진다 (docs/구현 계획.md 7.1절).
"""

from __future__ import annotations

import streamlit as st

from .. import auth, config, repo
from ..auth import Account
from ..roles import ABBREV_BY_ROLE
from ..rules import Student
from . import keys

#: st.fragment 자동 갱신 간격. 채점 프로그램은 단추가 나타나기를 7초까지
#: 기다리므로 5초 이하여야 한다 (공고 2.7절).
REFRESH_SECONDS = 5

_ACCOUNT = "_account"
_RESULT = "_result"


# =============================================================================
# 시작할 때
# =============================================================================


@st.cache_resource(show_spinner=False)
def _ensure_admin_account() -> bool:
    """관리자 계정을 만들거나 비밀번호를 갱신한다 (공고 2.1절).

    앱 과정이 사는 동안 한 번만 돈다.
    """
    with repo.open_store() as store:
        store.ensure_admin(auth.hash_password(config.admin_password()))
    return True


def bootstrap() -> None:
    """비밀 값과 DB 를 확인한다. 값 자체는 보여 주지 않는다 (공고 4.1절)."""
    missing = [name for name, present in config.secret_status().items() if not present]
    if missing:
        st.error(
            "다음 비밀 값이 없어 앱을 시작할 수 없음: "
            + ", ".join(missing)
            + "\n\n로컬에서는 .env 에, 배포한 앱에서는 Streamlit Secrets 에 "
            "넣어야 합니다 (공고 4.1절, 4.4절)."
        )
        st.stop()

    try:
        _ensure_admin_account()
    except Exception as exc:
        # 예외 본문에 DB 주소가 섞여 나오지 않게 종류만 보여 준다 (공고 6.3절 8번).
        st.error(
            "DB 에 연결할 수 없어 앱을 시작할 수 없음 "
            f"({type(exc).__name__}). Supabase 프로젝트가 일시정지되지 않았는지, "
            "DATABASE_URL 이 풀러(Supavisor) 주소인지 확인하세요."
        )
        st.stop()


# =============================================================================
# 로그인한 사람
# =============================================================================


def current_account() -> Account | None:
    return st.session_state.get(_ACCOUNT)


def sign_in(account: Account) -> None:
    st.session_state[_ACCOUNT] = account


def sign_out() -> None:
    st.session_state.pop(_ACCOUNT, None)
    st.session_state.pop(_RESULT, None)
    st.session_state.pop("_assign_outcome", None)
    st.session_state.pop("_assign_status", None)


# =============================================================================
# 결과 안내 (공고 2.7절)
# =============================================================================


def set_result(message: str) -> None:
    """result 컨테이너에 보여 줄 문장. 승인·대기·거절·막힘 으로 시작해야 한다."""
    st.session_state[_RESULT] = message


def render_result() -> None:
    """key 가 result 인 컨테이너.

    안내 문장만 담는다. 라벨 같은 글자를 함께 넣으면 채점 프로그램이 읽는 첫
    단어가 승인·대기·거절·막힘 이 아니게 된다.
    """
    with st.container(key=keys.RESULT, border=True):
        message = st.session_state.get(_RESULT)
        if message:
            st.write(message)
        else:
            st.caption("아직 누른 단추가 없습니다.")


def render_whoami(account: Account) -> None:
    """key 가 whoami 인 컨테이너. 이름이 보여야 한다 (공고 2.7절)."""
    with st.container(key=keys.WHOAMI, border=True):
        if account.is_admin:
            st.write(f"관리자 ({account.student_no})")
        else:
            st.write(f"{account.name} · 학번 {account.student_no}")


def render_refresh_button() -> None:
    """새로 고침 단추 (공고 2.7절).

    자동 갱신은 st.fragment 로 하지만, 채점 프로그램이 동작 전에 이 단추를 먼저
    누르므로 보험으로 함께 둔다.

    단추를 눌러도 아무것도 하지 않는다. 누르는 것만으로 Streamlit 이 이 fragment
    를 처음부터 다시 돌리고, 그 처음에서 DB 를 이미 다시 읽기 때문이다. 여기서
    st.rerun 을 또 부르면 같은 읽기를 한 번 더 해 화면이 두 배로 느려진다.
    """
    st.button("새로 고침", key=keys.REFRESH)


# =============================================================================
# 역할 표시
# =============================================================================


def describe_roles(student: Student) -> str:
    """'기획자 (보조: 보고서 작성자)' 꼴로 적는다."""
    if not student.sub_roles:
        return student.main_role
    sub = ", ".join(student.sub_roles)
    return f"{student.main_role} (보조: {sub})"


def short_roles(student: Student) -> str:
    codes = [ABBREV_BY_ROLE[student.main_role]]
    codes += [ABBREV_BY_ROLE[r] for r in student.sub_roles]
    return ";".join(codes)


# =============================================================================
# 로그인 화면
# =============================================================================


def render_login() -> None:
    st.title("팀 편성")
    st.caption("학번과 비밀번호로 로그인하세요. 관리자는 학번 칸에 admin 을 넣습니다.")

    with st.form("login_form"):
        student_no = st.text_input("학번", key=keys.LOGIN_STUDENT_NO)
        password = st.text_input("비밀번호", type="password", key=keys.LOGIN_PASSWORD)
        submitted = st.form_submit_button("로그인", key=keys.LOGIN_SUBMIT)

    if not submitted:
        return

    with repo.open_store() as store:
        account = auth.authenticate(store, student_no, password)

    if account is None:
        st.error("막힘: 학번이나 비밀번호가 맞지 않음")
        return

    sign_in(account)
    set_result(f"승인: {account.name} 으로 로그인함")
    st.rerun()
