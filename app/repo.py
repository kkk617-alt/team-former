"""Supabase(PostgreSQL) 저장소. app/store.py 의 Store 계약을 구현한다.

SQL 은 이 파일에만 있다. flow.py 와 ui/ 는 SQL 을 직접 쓰지 않는다.

학번(text)과 팀 번호(int)로 말하는 Store 계약을 DB 의 내부 id 로 옮기는 일도
여기서 한다.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Sequence

import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extras import execute_values

from . import db
from .rules import MAX_TEAM_SIZE, Student
from .store import (
    AlreadyInTeam,
    Application,
    PendingExists,
    SlotTaken,
    StudentScreen,
)

ADMIN_STUDENT_NO = "admin"

#: 유일성 제약 이름 → 앱 예외. schema.sql 의 이름과 맞아야 한다.
_MEMBER_STUDENT_UNIQUE = "tf_members_student_id_key"
_PENDING_UNIQUE = "tf_applications_one_pending_per_student"


class PgStore:
    """연결 하나(= 트랜잭션 하나) 위에서 동작하는 저장소."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    # --- 작은 도구 -------------------------------------------------------
    @contextmanager
    def _cursor(self):
        with self._conn.cursor() as cur:
            yield cur

    def _student_id(self, student_no: str) -> int | None:
        with self._cursor() as cur:
            cur.execute("select id from tf_students where student_no = %s", (student_no,))
            row = cur.fetchone()
        return row[0] if row else None

    def _team_id(self, team_no: int) -> int | None:
        with self._cursor() as cur:
            cur.execute("select id from tf_teams where team_no = %s", (team_no,))
            row = cur.fetchone()
        return row[0] if row else None

    # --- 명단과 계정 ------------------------------------------------------
    def replace_roster(
        self,
        students: Sequence[Student],
        team_count: int,
        student_password_hash: str,
    ) -> None:
        """명단으로 처음 상태를 만든다 (공고 2.6절).

        지원·투표·팀원·마감 표시를 모두 지우고, 명단의 학생과 넣은 팀 수만큼의
        빈 팀을 만든다. 관리자 계정은 남긴다 (공고 2.1절).
        """
        with self._cursor() as cur:
            # tf_teams 를 지우면 tf_members 와 tf_applications 가, 거기에 딸린
            # tf_votes 가 함께 지워진다 (on delete cascade).
            cur.execute("delete from tf_teams")
            cur.execute("delete from tf_students where not is_admin")
            cur.execute("delete from tf_settings")

            execute_values(
                cur,
                """
                insert into tf_students
                    (student_no, name, main_role, password_hash, is_admin)
                values %s
                """,
                [
                    (s.student_no, s.name, s.main_role, student_password_hash, False)
                    for s in students
                ],
            )

            cur.execute(
                "select id, student_no from tf_students where not is_admin"
            )
            ids = {student_no: sid for sid, student_no in cur.fetchall()}

            sub_rows = [
                (ids[s.student_no], role, position)
                for s in students
                for position, role in enumerate(s.sub_roles, start=1)
            ]
            if sub_rows:
                execute_values(
                    cur,
                    "insert into tf_student_sub_roles (student_id, role, position) values %s",
                    sub_rows,
                )

            execute_values(
                cur,
                "insert into tf_teams (team_no, name) values %s",
                [(n, f"팀{n}") for n in range(1, team_count + 1)],
            )

            cur.execute(
                "insert into tf_settings (key, value) values (%s, %s)",
                ("team_count", str(team_count)),
            )

    def ensure_admin(self, password_hash: str) -> None:
        """관리자 계정을 만들거나 비밀번호를 갱신한다 (공고 2.1절).

        main_role 은 null 이다. 관리자는 팀 배정 대상이 아니다.
        """
        with self._cursor() as cur:
            cur.execute(
                """
                insert into tf_students
                    (student_no, name, main_role, password_hash, is_admin)
                values (%s, %s, null, %s, true)
                on conflict (student_no) do update
                    set password_hash = excluded.password_hash,
                        is_admin      = true,
                        main_role     = null
                """,
                (ADMIN_STUDENT_NO, "관리자", password_hash),
            )

    def password_hash(self, student_no: str) -> str | None:
        with self._cursor() as cur:
            cur.execute(
                "select password_hash from tf_students where student_no = %s",
                (student_no,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def is_admin(self, student_no: str) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "select is_admin from tf_students where student_no = %s", (student_no,)
            )
            row = cur.fetchone()
        return bool(row and row[0])

    # --- 학생 ------------------------------------------------------------
    # 두 쪽 모두 text[] 로 못박는다. coalesce 의 기본값을 그냥 '{}' 로 두면
    # 타입이 정해지지 않은 문자열이라 식 전체가 text 로 풀려, 배열 대신
    # '{보고서 작성자,발표자}' 같은 문자열이 돌아온다. 그러면 tuple() 이 글자
    # 단위로 쪼개어 보조 역할이 통째로 망가진다.
    _STUDENT_SELECT = """
        select s.student_no,
               s.name,
               s.main_role,
               coalesce(
                   array_agg(r.role::text order by r.position, r.role)
                       filter (where r.role is not null),
                   '{}'::text[]
               ) as sub_roles
        from tf_students s
        left join tf_student_sub_roles r on r.student_id = s.id
        where not s.is_admin
    """

    @staticmethod
    def _to_student(row) -> Student:
        student_no, name, main_role, sub_roles = row
        return Student(
            student_no=student_no,
            name=name,
            main_role=main_role,
            sub_roles=tuple(sub_roles or ()),
        )

    def student(self, student_no: str) -> Student | None:
        with self._cursor() as cur:
            cur.execute(
                self._STUDENT_SELECT + " and s.student_no = %s group by s.id",
                (student_no,),
            )
            row = cur.fetchone()
        return self._to_student(row) if row else None

    def all_students(self) -> list[Student]:
        with self._cursor() as cur:
            cur.execute(self._STUDENT_SELECT + " group by s.id order by s.student_no")
            return [self._to_student(row) for row in cur.fetchall()]

    def unassigned_students(self) -> list[Student]:
        """팀이 없는 학생을 질의 한 번으로 가져온다 (app/store.py 참고)."""
        with self._cursor() as cur:
            cur.execute(
                self._STUDENT_SELECT
                + """
                  and not exists (
                      select 1 from tf_members m where m.student_id = s.id
                  )
                group by s.id
                order by s.student_no
                """
            )
            return [self._to_student(row) for row in cur.fetchall()]

    # --- 팀 --------------------------------------------------------------
    def team_numbers(self) -> list[int]:
        with self._cursor() as cur:
            cur.execute("select team_no from tf_teams order by team_no")
            return [row[0] for row in cur.fetchall()]

    def team_members(self, team_no: int) -> list[Student]:
        with self._cursor() as cur:
            cur.execute(
                """
                select s.student_no,
                       s.name,
                       s.main_role,
                       coalesce(
                           array_agg(r.role::text order by r.position, r.role)
                               filter (where r.role is not null),
                           '{}'::text[]
                       ),
                       m.slot_no
                from tf_members m
                join tf_teams    t on t.id = m.team_id
                join tf_students s on s.id = m.student_id
                left join tf_student_sub_roles r on r.student_id = s.id
                where t.team_no = %s
                group by s.id, m.slot_no
                order by m.slot_no
                """,
                (team_no,),
            )
            return [self._to_student(row[:4]) for row in cur.fetchall()]

    def all_team_members(self) -> dict[int, list[Student]]:
        """모든 팀의 팀원을 질의 한 번으로 가져온다.

        팀에 아무도 없으면 left join 때문에 학생 칸이 비어서 나오므로 건너뛴다.
        """
        with self._cursor() as cur:
            cur.execute(
                """
                select t.team_no,
                       s.student_no,
                       s.name,
                       s.main_role,
                       coalesce(
                           array_agg(r.role::text order by r.position, r.role)
                               filter (where r.role is not null),
                           '{}'::text[]
                       ),
                       m.slot_no
                from tf_teams t
                left join tf_members  m on m.team_id = t.id
                left join tf_students s on s.id = m.student_id
                left join tf_student_sub_roles r on r.student_id = s.id
                group by t.team_no, s.id, m.slot_no
                order by t.team_no, m.slot_no
                """
            )
            rows = cur.fetchall()

        teams: dict[int, list[Student]] = {}
        for row in rows:
            team_no = row[0]
            teams.setdefault(team_no, [])
            if row[1] is None:  # 빈 팀
                continue
            teams[team_no].append(self._to_student(row[1:5]))
        return teams

    def incoming_applications(
        self, team_no: int, voter_no: str
    ) -> list[tuple[Application, Student, str | None]]:
        """대기 중인 지원과 지원자, 그리고 voter_no 의 투표를 한 번에 가져온다."""
        with self._cursor() as cur:
            cur.execute(
                """
                select a.id, t.team_no, s.student_no, a.status, a.reason,
                       a.created_at, s.name, s.main_role,
                       coalesce(
                           array_agg(r.role::text order by r.position, r.role)
                               filter (where r.role is not null),
                           '{}'::text[]
                       ),
                       v.vote
                from tf_applications a
                join tf_teams    t on t.id = a.team_id
                join tf_students s on s.id = a.student_id
                left join tf_student_sub_roles r on r.student_id = s.id
                left join tf_votes v
                       on v.application_id = a.id
                      and v.voter_id = (
                          select id from tf_students where student_no = %s
                      )
                where t.team_no = %s and a.status = '대기'
                group by a.id, t.team_no, s.student_no, s.name, s.main_role, v.vote
                order by a.created_at, a.id
                """,
                (voter_no, team_no),
            )
            rows = cur.fetchall()

        result = []
        for row in rows:
            application = self._to_application(row[:6])
            applicant = self._to_student((row[2], row[6], row[7], row[8]))
            result.append((application, applicant, row[9]))
        return result

    #: 학생 화면 한 번에 필요한 값 전부를 한 문장으로 가져온다.
    #:
    #: 따로 물으면 왕복이 다섯 번이다. 배포한 앱에서 그것만으로 화면 한 번에
    #: 6.3초가 걸려, fragment 의 5초 간격을 넘겨 모든 세션이 쉬지 않고 화면을
    #: 그리는 상태가 되었다. 그러면 누른 단추의 처리가 뒤로 밀려, 채점 프로그램이
    #: 기다리는 7초를 넘긴다 (공고 2.7절, 4.2절).
    #:
    #: 팀이 없는 학생은 my_team 이 비어 incoming 조건이 거짓이 되므로 빈 목록이
    #: 나온다. json_agg 는 행이 없으면 null 을 주므로 파이썬 쪽에서 받아 준다.
    _SCREEN_SQL = """
        with me as (
            select id from tf_students where student_no = %(no)s
        ),
        sub as (
            select r.student_id,
                   array_agg(r.role::text order by r.position, r.role) as sub_roles
            from tf_student_sub_roles r
            group by r.student_id
        ),
        my_team as (
            select m.team_id from tf_members m
            where m.student_id = (select id from me)
        )
        select
            (select value from tf_settings where key = 'closed'),
            (
                select json_agg(t order by t.team_no, t.slot_no)
                from (
                    select tm.team_no,
                           mm.slot_no,
                           st.student_no,
                           st.name,
                           st.main_role,
                           coalesce(sub.sub_roles, '{}'::text[]) as sub_roles
                    from tf_teams tm
                    left join tf_members  mm on mm.team_id = tm.id
                    left join tf_students st on st.id = mm.student_id
                    left join sub on sub.student_id = st.id
                ) t
            ),
            (
                select json_build_object(
                    'id', a.id,
                    'team_no', tm.team_no,
                    'status', a.status,
                    'reason', a.reason,
                    'created_at', a.created_at
                )
                from tf_applications a
                join tf_teams tm on tm.id = a.team_id
                where a.student_id = (select id from me) and a.status = '대기'
            ),
            (
                select json_agg(i order by i.created_at, i.id)
                from (
                    select a.id,
                           tm.team_no,
                           st.student_no,
                           a.status,
                           a.reason,
                           a.created_at,
                           st.name,
                           st.main_role,
                           coalesce(sub.sub_roles, '{}'::text[]) as sub_roles,
                           v.vote
                    from tf_applications a
                    join tf_teams    tm on tm.id = a.team_id
                    join tf_students st on st.id = a.student_id
                    left join sub on sub.student_id = st.id
                    left join tf_votes v
                           on v.application_id = a.id
                          and v.voter_id = (select id from me)
                    where a.status = '대기'
                      and a.team_id = (select team_id from my_team)
                ) i
            )
    """

    def student_screen(self, student_no: str) -> StudentScreen:
        """학생 화면 한 번에 필요한 값을 왕복 한 번으로 가져온다 (공고 4.2절)."""
        with self._cursor() as cur:
            cur.execute(self._SCREEN_SQL, {"no": student_no})
            closed, teams_json, pending_json, incoming_json = cur.fetchone()

        teams: dict[int, list[Student]] = {}
        my_team_no: int | None = None
        for row in teams_json or ():
            team_no = row["team_no"]
            teams.setdefault(team_no, [])
            if row["student_no"] is None:  # 빈 팀
                continue
            student = self._to_student(
                (row["student_no"], row["name"], row["main_role"], row["sub_roles"])
            )
            teams[team_no].append(student)
            if student.student_no == student_no:
                my_team_no = team_no

        my_pending = None
        if pending_json is not None:
            my_pending = self._to_application(
                (
                    pending_json["id"],
                    pending_json["team_no"],
                    student_no,
                    pending_json["status"],
                    pending_json["reason"],
                    _to_time(pending_json["created_at"]),
                )
            )

        incoming = []
        for row in incoming_json or ():
            incoming.append(
                (
                    self._to_application(
                        (
                            row["id"],
                            row["team_no"],
                            row["student_no"],
                            row["status"],
                            row["reason"],
                            _to_time(row["created_at"]),
                        )
                    ),
                    self._to_student(
                        (
                            row["student_no"],
                            row["name"],
                            row["main_role"],
                            row["sub_roles"],
                        )
                    ),
                    row["vote"],
                )
            )

        return StudentScreen(
            closed=closed == "1",
            teams=teams,
            my_team_no=my_team_no,
            my_pending=my_pending,
            incoming=incoming,
        )

    def team_of(self, student_no: str) -> int | None:
        with self._cursor() as cur:
            cur.execute(
                """
                select t.team_no
                from tf_members m
                join tf_teams    t on t.id = m.team_id
                join tf_students s on s.id = m.student_id
                where s.student_no = %s
                """,
                (student_no,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def add_member(self, team_no: int, student_no: str) -> int:
        """빈 자리 가운데 가장 작은 번호에 넣는다.

        팀 행을 for update 로 잠가, 같은 팀에 동시에 들어오려는 요청을 줄 세운다.
        그래도 최종 판정은 (team_id, slot_no) 기본 키와 student_id 유일 제약이
        한다. 앱이 인원을 세서 막는 대신 DB 가 막게 하는 것이 공고 3장의 어려운
        해결이다.
        """
        team_id = self._team_id(team_no)
        student_id = self._student_id(student_no)
        if team_id is None or student_id is None:
            raise SlotTaken(f"팀{team_no} 또는 학번 {student_no} 가 없음")

        with self._cursor() as cur:
            cur.execute("select id from tf_teams where id = %s for update", (team_id,))

            cur.execute(
                "select slot_no from tf_members where team_id = %s", (team_id,)
            )
            taken = {row[0] for row in cur.fetchall()}
            free = next(
                (n for n in range(1, MAX_TEAM_SIZE + 1) if n not in taken), None
            )
            if free is None:
                raise SlotTaken(f"팀{team_no} 에 빈 자리가 없음")

            # 저장점을 두고 넣는다.
            #
            # PostgreSQL 은 제약 위반이 나면 트랜잭션 전체를 중단 상태로 만들고,
            # 그 뒤의 모든 질의가 InFailedSqlTransaction 으로 실패한다. 그런데
            # flow.py 는 이 예외를 잡은 다음 그 지원을 '거절' 로 바꾸는 질의를
            # 한다. 저장점으로 되돌리지 않으면 그 질의가 죽어, 먼저 도착한
            # 학생만 기록하는 처리 자체가 실패한다.
            cur.execute("savepoint tf_add_member")
            try:
                cur.execute(
                    """
                    insert into tf_members (team_id, slot_no, student_id)
                    values (%s, %s, %s)
                    """,
                    (team_id, free, student_id),
                )
            except pg_errors.UniqueViolation as exc:
                cur.execute("rollback to savepoint tf_add_member")
                raise self._translate_unique(exc) from exc
            cur.execute("release savepoint tf_add_member")

        return free

    @staticmethod
    def _translate_unique(exc: pg_errors.UniqueViolation) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if "student" in name:
            return AlreadyInTeam(str(exc))
        return SlotTaken(str(exc))

    def remove_member(self, student_no: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                delete from tf_members
                where student_id = (select id from tf_students where student_no = %s)
                """,
                (student_no,),
            )

    # --- 지원 ------------------------------------------------------------
    _APPLICATION_SELECT = """
        select a.id, t.team_no, s.student_no, a.status, a.reason, a.created_at
        from tf_applications a
        join tf_teams    t on t.id = a.team_id
        join tf_students s on s.id = a.student_id
    """

    @staticmethod
    def _to_application(row) -> Application:
        app_id, team_no, student_no, status, reason, created_at = row
        return Application(
            id=app_id,
            team_no=team_no,
            student_no=student_no,
            status=status,
            reason=reason,
            created_at=created_at,
        )

    def create_application(
        self, team_no: int, student_no: str, status: str, reason: str | None = None
    ) -> Application:
        team_id = self._team_id(team_no)
        student_id = self._student_id(student_no)
        if team_id is None or student_id is None:
            raise PendingExists(f"팀{team_no} 또는 학번 {student_no} 가 없음")

        with self._cursor() as cur:
            # add_member 와 같은 이유로 저장점을 둔다. 대기 지원이 이미 있어
            # 부분 유일 색인이 막으면, 호출하는 쪽이 그 뒤에도 질의를 할 수
            # 있어야 한다.
            cur.execute("savepoint tf_create_application")
            try:
                cur.execute(
                    """
                    insert into tf_applications
                        (team_id, student_id, status, reason)
                    values (%s, %s, %s, %s)
                    returning id, created_at
                    """,
                    (team_id, student_id, status, reason),
                )
            except pg_errors.UniqueViolation as exc:
                cur.execute("rollback to savepoint tf_create_application")
                raise PendingExists(str(exc)) from exc
            app_id, created_at = cur.fetchone()
            cur.execute("release savepoint tf_create_application")

        return Application(
            id=app_id,
            team_no=team_no,
            student_no=student_no,
            status=status,
            reason=reason,
            created_at=created_at,
        )

    def application(self, application_id: int) -> Application | None:
        with self._cursor() as cur:
            cur.execute(self._APPLICATION_SELECT + " where a.id = %s", (application_id,))
            row = cur.fetchone()
        return self._to_application(row) if row else None

    def pending_application_of(self, student_no: str) -> Application | None:
        with self._cursor() as cur:
            cur.execute(
                self._APPLICATION_SELECT
                + " where s.student_no = %s and a.status = '대기'",
                (student_no,),
            )
            row = cur.fetchone()
        return self._to_application(row) if row else None

    def pending_application_for(
        self, team_no: int, student_no: str
    ) -> Application | None:
        with self._cursor() as cur:
            cur.execute(
                self._APPLICATION_SELECT
                + " where s.student_no = %s and t.team_no = %s and a.status = '대기'",
                (student_no, team_no),
            )
            row = cur.fetchone()
        return self._to_application(row) if row else None

    def pending_applications(self) -> list[Application]:
        with self._cursor() as cur:
            cur.execute(
                self._APPLICATION_SELECT
                + " where a.status = '대기' order by a.created_at, a.id"
            )
            return [self._to_application(row) for row in cur.fetchall()]

    def pending_applications_for_team(self, team_no: int) -> list[Application]:
        with self._cursor() as cur:
            cur.execute(
                self._APPLICATION_SELECT
                + " where a.status = '대기' and t.team_no = %s"
                + " order by a.created_at, a.id",
                (team_no,),
            )
            return [self._to_application(row) for row in cur.fetchall()]

    def set_application_status(
        self, application_id: int, status: str, reason: str | None = None
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                "update tf_applications set status = %s, reason = %s where id = %s",
                (status, reason, application_id),
            )

    # --- 투표 ------------------------------------------------------------
    def record_vote(self, application_id: int, voter_no: str, vote: str) -> None:
        voter_id = self._student_id(voter_no)
        if voter_id is None:
            return
        with self._cursor() as cur:
            # 기본 키가 (application_id, voter_id) 이므로 두 번째 투표는 그대로
            # 무시된다. 한 번 투표하면 바꿀 수 없다 (공고 2.4절).
            cur.execute(
                """
                insert into tf_votes (application_id, voter_id, vote)
                values (%s, %s, %s)
                on conflict (application_id, voter_id) do nothing
                """,
                (application_id, voter_id, vote),
            )

    def vote_of(self, application_id: int, voter_no: str) -> str | None:
        with self._cursor() as cur:
            cur.execute(
                """
                select v.vote
                from tf_votes v
                join tf_students s on s.id = v.voter_id
                where v.application_id = %s and s.student_no = %s
                """,
                (application_id, voter_no),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def votes_for(self, application_id: int) -> dict[str, str]:
        with self._cursor() as cur:
            cur.execute(
                """
                select s.student_no, v.vote
                from tf_votes v
                join tf_students s on s.id = v.voter_id
                where v.application_id = %s
                """,
                (application_id,),
            )
            return dict(cur.fetchall())

    # --- 설정 ------------------------------------------------------------
    def setting(self, key: str) -> str | None:
        with self._cursor() as cur:
            cur.execute("select value from tf_settings where key = %s", (key,))
            row = cur.fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                insert into tf_settings (key, value) values (%s, %s)
                on conflict (key) do update set value = excluded.value
                """,
                (key, value),
            )

    def is_closed(self) -> bool:
        return self.setting("closed") == "1"

    # --- AI 호출 기록 -----------------------------------------------------
    def log_ai_attempts(self, attempts) -> None:
        """오픈라우터 호출 기록을 남긴다 (공고 4.2절이 허용한 확장).

        README 7.1절 5항의 실패 사례를 꾸며 내지 않고 실제 기록으로 제시하기
        위한 것이다 (공고 6.3절 20번).
        """
        if not attempts:
            return
        with self._cursor() as cur:
            execute_values(
                cur,
                """
                insert into tf_ai_logs
                    (attempt_no, model, status, detail, elapsed_ms)
                values %s
                """,
                [
                    (a.attempt_no, a.model, a.status, a.detail, a.elapsed_ms)
                    for a in attempts
                ],
            )

    def recent_ai_logs(self, limit: int = 20) -> list[tuple]:
        with self._cursor() as cur:
            cur.execute(
                """
                select created_at, attempt_no, model, status, elapsed_ms, detail
                from tf_ai_logs
                order by created_at desc, id desc
                limit %s
                """,
                (limit,),
            )
            return cur.fetchall()


@contextmanager
def open_store() -> Iterator[PgStore]:
    """동작 하나를 트랜잭션 하나로 묶는다.

    블록이 끝나면 커밋하고 예외가 나면 되돌리므로, 승인 직전 재검사와 팀원 추가가
    한 덩어리로 처리된다.
    """
    with db.connection() as conn:
        yield PgStore(conn)

def _to_time(value):
    """JSON 으로 돌아온 시각을 datetime 으로 되살린다.

    psycopg2 는 timestamptz 를 datetime 으로 주지만, json 안에 들어가면
    ISO 문자열이 된다. 따로 물은 값과 같은지 비교하려면 되살려야 한다.
    """
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
