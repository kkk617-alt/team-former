"""AI 배정과 자율 배정의 조합 (공고 2.5절 3~8항).

순서
  1. 앱이 먼저 완전탐색으로 "규칙을 지키는 배정이 있는지" 확인한다.
     없으면 AI 를 부르지 않고 이유를 보여 준다 (공고 2.5절 8항).
  2. 있으면 AI 를 1차·2차·3차로 부른다. AI 의 배정안은 2.5절 4항의 검사를
     통과해야 채택된다.
  3. 3차까지 실패하면 1단계에서 찾아 둔 배정을 쓴다 (공고 2.5절 6항).

1단계를 먼저 하는 이유는 가망 없는 상황에서 AI 호출 한도를 낭비하지 않기
위해서다. 무료 모델은 계정마다 하루 50회까지만 부를 수 있고, 채점 기간에는
30번 이상을 남겨 두어야 한다 (공고 4.3절).

완전탐색이 "배정이 가능한가" 를 정확히 판정하므로, 어림짐작으로 가망 없다고
잘못 단정해 AI 를 건너뛰는 일이 없다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from . import ai, flow
from .ai import AiAttempt, Streamer
from .store import Store


@dataclass(frozen=True)
class AssignmentOutcome:
    """관리자 화면에 보여 줄 배정 결과."""

    #: {학번: 팀 번호}. 규칙을 지키는 배정이 없으면 None, 배정할 학생이 없으면 {}
    plan: dict[str, int] | None
    #: 오픈라우터 호출 기록. tf_ai_logs 에 남긴다
    attempts: list[AiAttempt] = field(default_factory=list)
    #: 배정안의 출처 ("AI 1차 모델", "앱 자율 배정", "배정할 학생이 없음")
    source: str | None = None
    #: 규칙을 지키는 배정이 없을 때의 이유 (공고 2.5절 8항)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.plan is not None


def propose_assignment(
    store: Store,
    *,
    api_key: str,
    models: Sequence[str],
    streamer: Streamer = ai.requests_streamer,
    timeout_seconds: float = ai.TIMEOUT_SECONDS,
    on_progress: Callable[[int, str, float], None] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> AssignmentOutcome:
    """AI 배정 단추를 누른 결과. 확정하지는 않는다."""
    teams = flow.current_teams(store)
    unassigned = flow.unassigned_students(store)

    if not unassigned:
        problems = flow.check_confirmed_teams(store)
        if problems:
            return AssignmentOutcome(plan=None, problems=problems)
        return AssignmentOutcome(plan={}, source="배정할 학생이 없음")

    # 1. 규칙을 지키는 배정이 있는지 정확히 판정하고, 있으면 그 배정을 쥐고 있는다.
    fallback = flow.solve_assignment(teams, unassigned)
    if fallback is None:
        problems = flow.assignment_blockers(teams, unassigned)
        return AssignmentOutcome(
            plan=None,
            problems=problems or ["규칙을 모두 지키는 배정이 없음"],
        )

    # 2. AI 에게 물어본다. 검사를 통과하지 못한 배정안은 실패로 보고 다음 모델로.
    result = ai.request_assignment(
        teams=teams,
        unassigned=unassigned,
        models=models,
        api_key=api_key,
        validate=lambda plan: flow.validate_assignment(teams, unassigned, plan),
        streamer=streamer,
        timeout_seconds=timeout_seconds,
        on_progress=on_progress,
        now=now,
    )

    if result.succeeded:
        attempt_no = result.attempts[-1].attempt_no
        return AssignmentOutcome(
            plan=result.plan,
            attempts=result.attempts,
            source=f"AI {attempt_no}차 모델",
        )

    # 3. 3차 모델까지 실패. 앱이 스스로 찾아 둔 배정을 쓴다.
    return AssignmentOutcome(
        plan=fallback,
        attempts=result.attempts,
        source="앱 자율 배정",
    )
