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
from typing import Any, Protocol

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

    # --- 학생 ------------------------------------------------------------
    def student(self, student_no: str) -> Student | None: ...

    def all_students(self) -> list[Student]:
        """관리자를 제외한 학생 전체."""
        ...

    # --- 팀 --------------------------------------------------------------
    def team_numbers(self) -> list[int]: ...

    def team_members(self, team_no: int) -> list[Student]: ...

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
