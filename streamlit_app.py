"""팀 프로젝트 팀 편성 웹 앱 — 진입점.

Streamlit Community Cloud 의 Main file path 에 이 파일 이름을 넣는다 (공고 4.4절).

구조
    app/rules.py   팀 구성 규칙 (순수 함수)
    app/flow.py    지원·투표·마감·배정 흐름
    app/repo.py    Supabase 저장소
    app/ai.py      오픈라우터 모델 체인
    app/ui/        화면

자세한 설계는 docs/PRD.md 와 docs/구현 계획.md 에 있다.
"""

from __future__ import annotations

import streamlit as st

from app.ui import admin, common, student

st.set_page_config(page_title="팀 편성", page_icon="🧩", layout="wide")


def main() -> None:
    common.bootstrap()

    account = common.current_account()
    if account is None:
        common.render_login()
        return

    header, logout = st.columns([5, 1])
    with header:
        st.title("팀 편성")
        common.render_whoami(account)
    with logout:
        if st.button("로그아웃"):
            common.sign_out()
            st.rerun()

    if account.is_admin:
        admin.render()
    else:
        student.render()


main()
