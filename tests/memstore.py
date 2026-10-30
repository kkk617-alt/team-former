"""테스트용 인메모리 저장소.

app/flow.py 를 DB 없이 돌리기 위한 Store 구현이다. schema.sql 의 제약 가운데
흐름에 영향을 주는 것을 흉내 낸다.

  (team_no, slot_no) 기본 키   → SlotTaken
  student_id 유일              → AlreadyInTeam
  대기 지원 1건 부분 유일 색인  → PendingExists

이 제약들을 흉내 내는 이유는 flow.py 의 예외 처리 경로를 테스트가 실제로 지나게
하려는 것이다. 다만 진짜 동시성은 재현하지 못하므로, 실제 DB(app/repo.py)에서
한 번 더 확인해야 한다.
"""

from __future__ import annotations

import itertools

from app.rules import MAX_TEAM_SIZE, Student
from app.store import AlreadyInTeam, Application, PendingExists, SlotTaken


class InMemoryStore:
    def __init__(self) -> None:
        self._students: dict[str, Student] = {}
        self._team_numbers: list[int] = []
        # (team_no, slot_no) -> student_no  ... 기본 키를 그대로 흉내 낸다
        self._slots: dict[tuple[int, int], str] = {}
        self._applications: dict[int, Application] = {}
        self._votes: dict[tuple[int, str], str] = {}
        self._settings: dict[str, str] = {}
        self._next_app_id = itertools.count(1)
        self._clock = itertools.count(1)

    # --- 명단 올리기 ------------------------------------------------------
    def reset(self, students: list[Student], team_count: int) -> None:
        """명단 CSV 와 팀 수로 상태를 초기화한다 (공고 2.6절)."""
        self._students = {s.student_no: s for s in students}
        self._team_numbers = list(range(1, team_count + 1))
        self._slots.clear()
        self._applications.clear()
        self._votes.clear()
        self._settings.clear()

    # --- 학생 ------------------------------------------------------------
    def student(self, student_no: str) -> Student | None:
        return self._students.get(student_no)

    def all_students(self) -> list[Student]:
        return list(self._students.values())

    # --- 팀 --------------------------------------------------------------
    def team_numbers(self) -> list[int]:
        return list(self._team_numbers)

    def team_members(self, team_no: int) -> list[Student]:
        return [
            self._students[no]
            for (t, _slot), no in sorted(self._slots.items())
            if t == team_no
        ]

    def team_of(self, student_no: str) -> int | None:
        for (team_no, _slot), no in self._slots.items():
            if no == student_no:
                return team_no
        return None

    def add_member(self, team_no: int, student_no: str) -> int:
        if self.team_of(student_no) is not None:
            raise AlreadyInTeam(student_no)
        for slot_no in range(1, MAX_TEAM_SIZE + 1):
            if (team_no, slot_no) not in self._slots:
                self._slots[(team_no, slot_no)] = student_no
                return slot_no
        raise SlotTaken(team_no)

    def remove_member(self, student_no: str) -> None:
        for key, no in list(self._slots.items()):
            if no == student_no:
                del self._slots[key]

    # --- 지원 ------------------------------------------------------------
    def create_application(
        self, team_no: int, student_no: str, status: str, reason: str | None = None
    ) -> Application:
        if status == "대기" and self.pending_application_of(student_no) is not None:
            raise PendingExists(student_no)
        app = Application(
            id=next(self._next_app_id),
            team_no=team_no,
            student_no=student_no,
            status=status,
            reason=reason,
            created_at=next(self._clock),
        )
        self._applications[app.id] = app
        return app

    def application(self, application_id: int) -> Application | None:
        return self._applications.get(application_id)

    def pending_application_of(self, student_no: str) -> Application | None:
        for app in self._applications.values():
            if app.student_no == student_no and app.status == "대기":
                return app
        return None

    def pending_application_for(self, team_no: int, student_no: str) -> Application | None:
        app = self.pending_application_of(student_no)
        if app is not None and app.team_no == team_no:
            return app
        return None

    def pending_applications(self) -> list[Application]:
        return sorted(
            (a for a in self._applications.values() if a.status == "대기"),
            key=lambda a: a.created_at,
        )

    def pending_applications_for_team(self, team_no: int) -> list[Application]:
        return [a for a in self.pending_applications() if a.team_no == team_no]

    def set_application_status(
        self, application_id: int, status: str, reason: str | None = None
    ) -> None:
        app = self._applications[application_id]
        self._applications[application_id] = Application(
            id=app.id,
            team_no=app.team_no,
            student_no=app.student_no,
            status=status,
            reason=reason,
            created_at=app.created_at,
        )

    # --- 투표 ------------------------------------------------------------
    def record_vote(self, application_id: int, voter_no: str, vote: str) -> None:
        self._votes[(application_id, voter_no)] = vote

    def vote_of(self, application_id: int, voter_no: str) -> str | None:
        return self._votes.get((application_id, voter_no))

    def votes_for(self, application_id: int) -> dict[str, str]:
        return {
            voter: vote
            for (app_id, voter), vote in self._votes.items()
            if app_id == application_id
        }

    # --- 설정 ------------------------------------------------------------
    def setting(self, key: str) -> str | None:
        return self._settings.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self._settings[key] = value

    def is_closed(self) -> bool:
        return self._settings.get("closed") == "1"
