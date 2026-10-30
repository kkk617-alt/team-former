"""실제 Supabase(PostgreSQL) 에 대고 돌리는 검사.

DATABASE_URL 과 TEAM_FORMER_TEST_DB=1 이 둘 다 있을 때만 돈다. 이 검사는 tf_
테이블의 내용을 지우므로, 실수로 돌지 않게 환경 변수를 하나 더 요구한다.
6장 실습의 테이블은 이름이 달라 건드리지 않는다.

    # Git Bash
    TEAM_FORMER_TEST_DB=1 python -m pytest tests/test_postgres.py -v

여기서 확인하는 것은 인메모리 저장소로는 확인할 수 없는 것들이다.

  - schema.sql 이 실제로 적용되고 여러 번 적용해도 안전한지
  - repo.py 의 SQL 이 동작하는지 (계약 검사는 이름만 보므로)
  - 유일성 제약이 정말로 막는지 (공고 3장 "마지막 자리에 두 명이 동시에")
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app import auth, flow
from app.roster import parse_roster
from app.store import AlreadyInTeam, PendingExists, SlotTaken

from conftest import FIXTURES

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema.sql"

pytestmark = pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") and os.environ.get("TEAM_FORMER_TEST_DB") == "1"),
    reason="DATABASE_URL 과 TEAM_FORMER_TEST_DB=1 이 있어야 돈다",
)

ADMIN_PASSWORD = "실제-DB-검사용-관리자-비밀번호"


@pytest.fixture(scope="module")
def schema_applied():
    """schema.sql 을 두 번 적용해 멱등성까지 확인한다."""
    import psycopg2

    sql = SCHEMA.read_text(encoding="utf-8")
    conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")
    try:
        for _ in range(2):
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
    finally:
        conn.close()
    return True


@pytest.fixture
def store(schema_applied):
    """쉬움 명단으로 초기화한 PgStore. 동작마다 트랜잭션을 새로 연다.

    이 검사는 관리자 비밀번호를 검사용 값으로 바꿔 쓰므로, 끝나면 원래 해시로
    되돌린다. 되돌리지 않으면 같은 DB 를 쓰는 배포한 앱의 관리자 비밀번호가
    바뀐 채로 남는다. 배포한 앱은 시작할 때 한 번만 관리자 계정을 손보므로
    스스로 고치지 못하고, 채점 기간에 그런 일이 생기면 공고 6.3절 17번에 따라
    시나리오 점수가 0점이 된다.
    """
    from app import repo

    with repo.open_store() as s:
        original_admin_hash = s.password_hash("admin")

    students = parse_roster((FIXTURES / "쉬움.csv").read_bytes())
    with repo.open_store() as s:
        s.ensure_admin(auth.hash_password(ADMIN_PASSWORD))
        s.replace_roster(students, 3, auth.hash_password(auth.STUDENT_PASSWORD))

    try:
        with repo.open_store() as s:
            yield s
    finally:
        if original_admin_hash:
            with repo.open_store() as s:
                _restore_admin_hash(s, original_admin_hash)


def _restore_admin_hash(store, password_hash: str) -> None:
    """관리자 비밀번호 해시를 원래 값으로 되돌린다."""
    with store._conn.cursor() as cur:  # noqa: SLF001
        cur.execute(
            "update tf_students set password_hash = %s where student_no = 'admin'",
            (password_hash,),
        )


def no(store, label: str) -> str:
    for student in store.all_students():
        if student.name == label:
            return student.student_no
    raise AssertionError(f"{label} 을 찾을 수 없음")


# =============================================================================
# 명단과 역할
# =============================================================================


def test_roster_round_trips_through_the_database(store):
    students = store.all_students()
    assert len(students) == 8
    assert all(s.student_no != "admin" for s in students)


def test_sub_roles_keep_their_csv_order(store):
    student = store.student(no(store, "학생8(TT;RW;PT)"))
    assert student.main_role == "테스터"
    assert student.sub_roles == ("보고서 작성자", "발표자")


def test_student_with_no_sub_role(store):
    student = store.student(no(store, "학생5(WP)"))
    assert student.sub_roles == ()


def test_teams_are_created_empty(store):
    assert store.team_numbers() == [1, 2, 3]
    for team_no in store.team_numbers():
        assert store.team_members(team_no) == []


def test_admin_survives_the_roster_upload(store):
    assert store.is_admin("admin")
    assert auth.authenticate(store, "admin", ADMIN_PASSWORD) is not None


def test_students_can_log_in(store):
    account = auth.authenticate(store, no(store, "학생1(PL;RW)"), auth.STUDENT_PASSWORD)
    assert account is not None
    assert not account.is_admin


def test_wrong_password_is_refused(store):
    assert auth.authenticate(store, no(store, "학생1(PL;RW)"), "틀림") is None


# =============================================================================
# 부록 1(쉬움) 전 단계를 실제 DB 로
# =============================================================================


def test_easy_scenario_against_the_real_database(store):
    s1 = no(store, "학생1(PL;RW)")
    s2 = no(store, "학생2(PL;PT)")
    s3 = no(store, "학생3(PL;TT)")
    s4 = no(store, "학생4(WP;FD)")
    s5 = no(store, "학생5(WP)")
    s6 = no(store, "학생6(WP;TT)")
    s7 = no(store, "학생7(FD;PT)")

    # 1단계
    assert flow.apply_to_team(store, s1, 1).outcome == "승인"
    assert flow.apply_to_team(store, s2, 2).outcome == "승인"
    assert flow.apply_to_team(store, s3, 3).outcome == "승인"

    # 2단계
    assert flow.apply_to_team(store, s4, 1).outcome == "대기"
    assert flow.cast_vote(store, s1, s4, "찬성").outcome == "승인"

    # 3단계
    assert flow.apply_to_team(store, s5, 2).outcome == "대기"
    assert flow.cast_vote(store, s2, s5, "찬성").outcome == "승인"

    # 4단계
    assert flow.apply_to_team(store, s7, 1).outcome == "대기"
    assert flow.cast_vote(store, s1, s7, "찬성").outcome == "대기"
    assert flow.cast_vote(store, s4, s7, "거부").outcome == "거절"

    # 5단계
    assert flow.apply_to_team(store, s6, 3).outcome == "대기"
    assert flow.cast_vote(store, s3, s6, "찬성").outcome == "승인"

    # 6단계
    assert flow.close_recruiting(store).outcome == "승인"
    plan = flow.solve_assignment(
        flow.current_teams(store), flow.unassigned_students(store)
    )
    assert plan is not None
    assert flow.confirm_assignment(store, plan).outcome == "승인"
    assert flow.check_confirmed_teams(store) == []
    assert flow.unassigned_students(store) == []


# =============================================================================
# DB 제약 (인메모리로는 확인할 수 없는 것)
# =============================================================================


def test_unique_constraint_keeps_a_student_in_one_team(store):
    """tf_members.student_id 유일 제약 — 한 학생은 한 팀에만 (공고 3장)."""
    s1 = no(store, "학생1(PL;RW)")
    store.add_member(1, s1)
    with pytest.raises(AlreadyInTeam):
        store.add_member(2, s1)


def test_primary_key_blocks_a_fifth_member(store):
    """slot_no 는 1~4 이므로 다섯 번째 자리가 없다 (공고 5절)."""
    labels = [
        "학생1(PL;RW)",
        "학생4(WP;FD)",
        "학생7(FD;PT)",
        "학생8(TT;RW;PT)",
    ]
    for label in labels:
        store.add_member(1, no(store, label))

    with pytest.raises(SlotTaken):
        store.add_member(1, no(store, "학생2(PL;PT)"))


def test_partial_unique_index_allows_only_one_pending_application(store):
    """결과가 나오기 전에는 다른 팀에 지원할 수 없다 (공고 2.4절)."""
    s1 = no(store, "학생1(PL;RW)")
    s4 = no(store, "학생4(WP;FD)")
    store.add_member(1, s1)

    store.create_application(1, s4, "대기")
    with pytest.raises(PendingExists):
        store.create_application(2, s4, "대기")


def test_transaction_survives_a_constraint_violation(store):
    """제약 위반 뒤에도 같은 트랜잭션에서 질의를 계속할 수 있어야 한다.

    PostgreSQL 은 제약 위반이 나면 트랜잭션을 중단 상태로 만든다. 그런데
    flow.py 는 유일성 제약에 막힌 뒤 그 지원을 '거절' 로 바꾸는 질의를 한다.
    repo.py 가 저장점으로 되돌리지 않으면 그 질의가 InFailedSqlTransaction 으로
    죽어, 먼저 도착한 학생만 기록하는 처리가 실패한다.
    """
    s1 = no(store, "학생1(PL;RW)")
    s4 = no(store, "학생4(WP;FD)")
    store.add_member(1, s1)

    with pytest.raises(AlreadyInTeam):
        store.add_member(2, s1)

    # 트랜잭션이 살아 있어야 한다
    application = store.create_application(1, s4, "대기")
    store.set_application_status(application.id, "거절", "검사용")
    assert store.application(application.id).status == "거절"


def test_losing_the_last_slot_is_recorded_as_a_rejection(store):
    """유일성 제약에 막힌 승인이 '거절' 로 기록된다 (공고 3장).

    학생4 가 팀1 에 지원해 대기하는 동안 다른 경로로 팀2 에 들어가 버린 상황을
    만든다. 승인 직전 재검사는 팀1 만 보므로 통과하지만, student_id 유일 제약이
    막는다.
    """
    s1 = no(store, "학생1(PL;RW)")
    s4 = no(store, "학생4(WP;FD)")

    assert flow.apply_to_team(store, s1, 1).outcome == "승인"
    assert flow.apply_to_team(store, s4, 1).outcome == "대기"

    store.add_member(2, s4)  # 그 사이에 다른 팀에 들어감

    decision = flow.cast_vote(store, s1, s4, "찬성")
    assert decision.outcome == "거절"
    assert "먼저 차지" in decision.reason


def test_a_vote_cannot_be_changed(store):
    """(application_id, voter_id) 기본 키 — 한 번 투표하면 바꿀 수 없다."""
    s1 = no(store, "학생1(PL;RW)")
    s4 = no(store, "학생4(WP;FD)")
    store.add_member(1, s1)
    application = store.create_application(1, s4, "대기")

    store.record_vote(application.id, s1, "찬성")
    store.record_vote(application.id, s1, "거부")
    assert store.vote_of(application.id, s1) == "찬성"


def test_check_constraint_rejects_a_role_outside_the_six(store, schema_applied):
    """main_role 과 role 에 6개 역할 밖의 값이 들어가지 않는다 (공고 5절)."""
    import psycopg2

    with pytest.raises(psycopg2.errors.CheckViolation):
        with store._conn.cursor() as cur:  # noqa: SLF001
            cur.execute(
                """
                insert into tf_students
                    (student_no, name, main_role, password_hash, is_admin)
                values ('9999999', '검사용', '수석 개발자', 'x', false)
                """
            )
    store._conn.rollback()  # noqa: SLF001


def test_password_is_not_stored_in_plain_text(store):
    """공고 6.3절 10번 (-2점)."""
    stored = store.password_hash(no(store, "학생1(PL;RW)"))
    assert stored != auth.STUDENT_PASSWORD
    assert stored.startswith("$2b$")


# =============================================================================
# AI 호출 기록
# =============================================================================


def test_ai_attempts_are_logged(store):
    from app.ai import AiAttempt

    store.log_ai_attempts(
        [
            AiAttempt(1, "model-a", "시간초과", "120초 안에 응답 없음", 120000),
            AiAttempt(2, "model-b", "성공", None, 4200),
        ]
    )
    rows = store.recent_ai_logs(limit=5)
    statuses = [row[3] for row in rows]
    assert "시간초과" in statuses
    assert "성공" in statuses

# =============================================================================
# 화면 한 번 = 왕복 한 번 (공고 4.2절)
# =============================================================================


class _CountingCursor:
    """execute 를 센다. with 문에서도 쓸 수 있게 감싼다."""

    def __init__(self, cursor, counter):
        self._cursor = cursor
        self._counter = counter

    def execute(self, *args, **kwargs):
        self._counter.executes += 1
        return self._cursor.execute(*args, **kwargs)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *exc):
        return self._cursor.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _CountingConn:
    def __init__(self, conn):
        self._conn = conn
        self.executes = 0

    def cursor(self, *args, **kwargs):
        return _CountingCursor(self._conn.cursor(*args, **kwargs), self)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _state_with_a_pending_application(store):
    """팀1 에 두 명, 팀1 에 대기 중인 지원 하나, 그 지원에 투표 하나."""
    s1 = no(store, "학생1(PL;RW)")
    s4 = no(store, "학생4(WP;FD)")
    s7 = no(store, "학생7(FD;PT)")
    flow.apply_to_team(store, s1, 1)
    flow.apply_to_team(store, s4, 1)
    flow.cast_vote(store, s1, s4, "찬성")
    flow.apply_to_team(store, s7, 1)
    flow.cast_vote(store, s1, s7, "찬성")
    return s1, s4, s7


def test_student_screen_needs_one_round_trip(store):
    """공고 4.2절. 다섯 번 묻던 것을 한 번으로 줄인 것이 이 과제의 요구다."""
    s1, _, _ = _state_with_a_pending_application(store)

    counting = _CountingConn(store._conn)  # noqa: SLF001
    store._conn = counting  # noqa: SLF001
    store.student_screen(s1)

    assert counting.executes == 1, f"왕복 {counting.executes} 번"


def test_student_screen_says_the_same_thing_as_the_single_queries(store):
    """한 번에 가져온 값이 따로 물은 값과 같아야 한다.

    질의를 둘로 두면 한쪽만 고쳐져 어긋날 수 있다. 그 어긋남을 여기서 잡는다.
    """
    s1, _, s7 = _state_with_a_pending_application(store)

    screen = store.student_screen(s1)
    assert screen.closed == store.is_closed()
    assert screen.teams == store.all_team_members()
    assert screen.my_team_no == store.team_of(s1)
    assert screen.my_pending == store.pending_application_of(s1)
    assert screen.incoming == store.incoming_applications(1, s1)

    # 투표까지 들어 있어야 한다
    assert [(a.student_no, v) for a, _, v in screen.incoming] == [(s7, "찬성")]


def test_student_screen_of_a_student_with_no_team(store):
    _state_with_a_pending_application(store)
    s2 = no(store, "학생2(PL;PT)")

    screen = store.student_screen(s2)
    assert screen.my_team_no is None
    assert screen.my_pending is None
    assert screen.incoming == []
    assert sorted(screen.teams) == [1, 2, 3]


def test_student_screen_of_an_applicant_waiting_for_votes(store):
    _, _, s7 = _state_with_a_pending_application(store)

    screen = store.student_screen(s7)
    assert screen.my_team_no is None
    assert screen.my_pending is not None
    assert screen.my_pending.team_no == 1
    assert screen.my_pending.status == "대기"


def test_student_screen_sees_the_closing(store):
    s1, _, _ = _state_with_a_pending_application(store)
    flow.close_recruiting(store)
    assert store.student_screen(s1).closed is True
