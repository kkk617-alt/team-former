"""저장소 계약.

app/flow.py 는 이 Protocol 만 보고 동작한다. 구현은 두 가지다.

  app/repo.py     Supabase(PostgreSQL) — 실제 앱이 쓰는 것
  tests/memstore.py  인메모리 — 테스트가 쓰는 것

flow.py 가 SQL 을 직접 쓰지 않게 하려는 분리이고, 덕분에 DB 없이 부록 시나리오를
재현할 수 있다 (docs/구현 계획.md 1.1절).

예외 세 가지는 schema.sql 의 제약을 그대로 옮긴 것이다. 앱이 인원을 세서 막는
대신 DB 가 막게 하고, flow 는 그 예외를 결과 안내로 바꾼다 (공고 3장의 어려운
해결, "마지막 자리에 두 명이 동시에 들어감").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .rules import Student


@dataclass(frozen=True)
class Application:
    """tf_applications 한 행."""

    id: int
    team_no: int
    student_no: str
    status: str  # 대기 | 승인 | 거절
    reason: str | None = None
    created_at: Any = None


@dataclass(frozen=True)
class StudentScreen:
    """학생 화면 한 번을 그리는 데 필요한 값 전부 (공고 2.8절).

    원격 DB 에서는 왕복 횟수가 곧 화면이 뜨는 시간이다 (공고 4.2절). 이 값들을
    따로 물으면 왕복이 다섯 번이 되어, fragment 의 5초 간격으로는 다 그리지
    못하고 화면이 줄지어 밀린다. 그래서 한 번에 받아 온다.
    """

    closed: bool
    teams: dict[int, list[Student]]
    my_team_no: int | None
    my_pending: Application | None
    #: 내 팀에 들어온 대기 중인 지원 [(지원, 지원자, 내가 한 투표)]
    incoming: list[tuple[Application, Student, str | None]]


class StoreError(Exception):
    """저장소 제약 위반."""


class AlreadyInTeam(StoreError):
    """tf_members.student_id 유일 제약 — 한 학생은 한 팀에만 속한다."""


class SlotTaken(StoreError):
    """tf_members (team_id, slot_no) 기본 키 — 빈 자리가 없다."""


class PendingExists(StoreError):
    """tf_applications 부분 유일 색인 — 대기 중인 지원이 이미 있다."""


class Store(Protocol):
    """flow.py 가 필요로 하는 연산."""

    # --- 명단과 계정 ------------------------------------------------------
    def replace_roster(
        self,
        students: "Sequence[Student]",
        team_count: int,
        student_password_hash: str,
    ) -> None:
        """명단 CSV 로 상태를 초기화한다 (공고 2.6절).

        지원·투표·팀원·마감 표시를 모두 지우고, 명단의 학생과 넣은 팀 수만큼의
        빈 팀을 만든다. 관리자 계정은 남긴다 (공고 2.1절).

        학생의 비밀번호는 모두 같은 값(1234)이므로 해시를 한 번만 계산해
        함께 넘긴다. bcrypt 는 한 번에 수백 밀리초가 걸려, 학생마다 따로
        계산하면 명단 올리기가 눈에 띄게 느려진다.
        """
        ...

    def ensure_admin(self, password_hash: str) -> None:
        """관리자 계정을 만들거나 비밀번호를 갱신한다 (공고 2.1절)."""
        ...

    def password_hash(self, student_no: str) -> str | None:
        """저장된 bcrypt 해시. 없는 학번이면 None."""
        ...

    def is_admin(self, student_no: str) -> bool: ...

    # --- 학생 ------------------------------------------------------------
    def student(self, student_no: str) -> Student | None: ...

    def all_students(self) -> list[Student]:
        """관리자를 제외한 학생 전체."""
        ...

    def unassigned_students(self) -> list[Student]:
        """팀이 없는 학생. 질의 한 번으로 가져와야 한다.

        학생마다 team_of 를 부르면 명단이 16명일 때 왕복이 17번이 되어, 원격
        DB 에서는 화면 한 번 그리는 데 5초가 넘는다. 채점 프로그램은 단추가
        나타나기를 7초까지만 기다린다 (공고 2.7절, 4.2절).
        """
        ...

    # --- 팀 --------------------------------------------------------------
    def team_numbers(self) -> list[int]: ...

    def team_members(self, team_no: int) -> list[Student]: ...

    def all_team_members(self) -> dict[int, list[Student]]:
        """{팀 번호: 팀원}. 빈 팀도 빈 목록으로 들어 있다.

        팀마다 team_members 를 부르는 대신 질의 한 번으로 가져온다.
        """
        ...

    def incoming_applications(
        self, team_no: int, voter_no: str
    ) -> list[tuple[Application, Student, str | None]]:
        """그 팀의 대기 중인 지원을 (지원, 지원자, voter_no 가 한 투표) 로 돌려준다.

        지원마다 학생과 투표를 따로 조회하면 왕복이 지원 수의 두 배가 된다.
        """
        ...

    def student_screen(self, student_no: str) -> StudentScreen:
        """학생 화면 한 번에 필요한 값을 왕복 한 번으로 가져온다 (공고 4.2절).

        my_team_no 는 teams 에서 끌어내므로 따로 묻지 않는다.
        """
        ...

    def team_of(self, student_no: str) -> int | None: ...

    def add_member(self, team_no: int, student_no: str) -> int:
        """빈 자리 가운데 가장 작은 번호에 넣고 그 번호를 돌려준다.

        Raises:
            AlreadyInTeam: 그 학생이 이미 어느 팀에 속함
            SlotTaken: 그 팀에 빈 자리가 없음
        """
        ...

    def remove_member(self, student_no: str) -> None: ...

    # --- 지원 ------------------------------------------------------------
    def create_application(
        self, team_no: int, student_no: str, status: str, reason: str | None = None
    ) -> Application:
        """Raises: PendingExists — 대기 지원을 두 건 만들려 할 때."""
        ...

    def application(self, application_id: int) -> Application | None: ...

    def pending_application_of(self, student_no: str) -> Application | None: ...

    def pending_application_for(
        self, team_no: int, student_no: str
    ) -> Application | None: ...

    def pending_applications(self) -> list[Application]:
        """지원한 순서대로."""
        ...

    def pending_applications_for_team(self, team_no: int) -> list[Application]: ...

    def set_application_status(
        self, application_id: int, status: str, reason: str | None = None
    ) -> None: ...

    # --- 투표 ------------------------------------------------------------
    def record_vote(self, application_id: int, voter_no: str, vote: str) -> None: ...

    def vote_of(self, application_id: int, voter_no: str) -> str | None: ...

    def votes_for(self, application_id: int) -> dict[str, str]:
        """{투표한 학생 학번: 찬성|거부}"""
        ...

    # --- 설정 ------------------------------------------------------------
    def setting(self, key: str) -> str | None: ...

    def set_setting(self, key: str, value: str) -> None: ...

    def is_closed(self) -> bool: ...

    # --- AI 호출 기록 -----------------------------------------------------
    def log_ai_attempts(self, attempts: "Sequence[Any]") -> None:
        """오픈라우터 호출 기록을 남긴다.

        README 7.1절 5항의 실패 사례를 꾸며 내지 않고 실제 기록으로 제시하기
        위한 것이다 (공고 6.3절 20번). attempts 는 app.ai.AiAttempt 의 목록이다.
        """
        ...

    def recent_ai_logs(self, limit: int = 20) -> list[tuple]:
        """최근 호출 기록. (created_at, attempt_no, model, status, elapsed_ms, detail)"""
        ...
