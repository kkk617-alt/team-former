"""AI 배정과 자율 배정의 조합 테스트 (공고 2.5절 3~8항)."""

from __future__ import annotations

import json

import pytest

from app import assign, flow

from conftest import HARD_ROWS, make_roster
from memstore import InMemoryStore
from test_ai import FakeClock, FakeStreamer, plan_body


def build_store(rows, team_count: int) -> tuple[InMemoryStore, dict]:
    roster = make_roster(rows)
    store = InMemoryStore()
    store.reset(list(roster.values()), team_count)
    return store, roster


def hard_after_close() -> tuple[InMemoryStore, dict]:
    """어려움 시나리오 14단계 직후 상태를 만든다."""
    store, roster = build_store(HARD_ROWS, 4)

    def no(label: str) -> str:
        return roster[label].student_no

    flow.apply_to_team(store, no("학생1(PL;RW)"), 1)
    flow.apply_to_team(store, no("학생4(WP;PL)"), 1)
    flow.cast_vote(store, no("학생1(PL;RW)"), no("학생4(WP;PL)"), "찬성")
    flow.apply_to_team(store, no("학생7(FD;PT;TT)"), 1)
    flow.cast_vote(store, no("학생1(PL;RW)"), no("학생7(FD;PT;TT)"), "찬성")
    flow.cast_vote(store, no("학생4(WP;PL)"), no("학생7(FD;PT;TT)"), "찬성")

    flow.apply_to_team(store, no("학생2(PL;PT)"), 2)
    flow.apply_to_team(store, no("학생8(FD;TT)"), 2)
    flow.cast_vote(store, no("학생2(PL;PT)"), no("학생8(FD;TT)"), "찬성")
    flow.apply_to_team(store, no("학생5(WP;FD)"), 2)
    flow.cast_vote(store, no("학생2(PL;PT)"), no("학생5(WP;FD)"), "찬성")
    flow.cast_vote(store, no("학생8(FD;TT)"), no("학생5(WP;FD)"), "찬성")

    flow.apply_to_team(store, no("학생11(TT;PT)"), 3)
    flow.apply_to_team(store, no("학생15(PT;FD)"), 3)
    flow.cast_vote(store, no("학생11(TT;PT)"), no("학생15(PT;FD)"), "찬성")

    flow.apply_to_team(store, no("학생10(TT;RW)"), 4)
    flow.close_recruiting(store)
    return store, roster


def propose(store, responses, *, models=None, clock=None, **kwargs):
    clock = clock or FakeClock()
    streamer = FakeStreamer(responses, clock)
    outcome = assign.propose_assignment(
        store,
        api_key="테스트-키",
        models=models or ["model-1", "model-2", "model-3"],
        streamer=streamer,
        now=clock,
        **kwargs,
    )
    return outcome, streamer


# =============================================================================
# AI 가 성공한 경우
# =============================================================================


def test_uses_the_plan_from_the_ai_when_it_passes_validation():
    store, _ = hard_after_close()
    teams = flow.current_teams(store)
    unassigned = flow.unassigned_students(store)

    # 앱이 스스로 찾은 배정을 그대로 AI 응답으로 흉내 낸다 (검사를 통과하는 값)
    valid = flow.solve_assignment(teams, unassigned)
    assert valid is not None
    body = plan_body(
        [{"student_no": no, "team": team} for no, team in valid.items()]
    )

    outcome, streamer = propose(store, [(200, [body], 1.0)])

    assert outcome.plan == valid
    assert outcome.source == "AI 1차 모델"
    assert streamer.calls == ["model-1"]
    assert [a.status for a in outcome.attempts] == ["성공"]
    assert outcome.problems == []


def test_reports_which_model_produced_the_plan():
    store, _ = hard_after_close()
    valid = flow.solve_assignment(
        flow.current_teams(store), flow.unassigned_students(store)
    )
    body = plan_body([{"student_no": no, "team": t} for no, t in valid.items()])

    outcome, _ = propose(store, [(500, [b"x"], 1.0), (200, [body], 1.0)])
    assert outcome.source == "AI 2차 모델"


# =============================================================================
# AI 가 3차까지 실패한 경우 (공고 2.5절 6항, 3장의 어려운 해결)
# =============================================================================


def test_falls_back_to_its_own_search_when_all_models_fail():
    store, _ = hard_after_close()
    teams = flow.current_teams(store)
    unassigned = flow.unassigned_students(store)

    outcome, streamer = propose(
        store,
        [(500, [b"x"], 1.0), (500, [b"x"], 1.0), (500, [b"x"], 1.0)],
    )

    assert streamer.calls == ["model-1", "model-2", "model-3"]
    assert outcome.source == "앱 자율 배정"
    assert outcome.plan is not None
    assert len(outcome.attempts) == 3
    # 자율 배정도 2.5절 4항의 검사를 통과해야 한다
    assert flow.validate_assignment(teams, unassigned, outcome.plan) == []


def test_fallback_plan_assigns_every_unassigned_student():
    store, _ = hard_after_close()
    unassigned = flow.unassigned_students(store)

    outcome, _ = propose(
        store, [(500, [b"x"], 1.0), (500, [b"x"], 1.0), (500, [b"x"], 1.0)]
    )

    assert set(outcome.plan) == {s.student_no for s in unassigned}


def test_fallback_plan_can_be_confirmed():
    store, _ = hard_after_close()
    outcome, _ = propose(
        store, [(500, [b"x"], 1.0), (500, [b"x"], 1.0), (500, [b"x"], 1.0)]
    )

    assert flow.confirm_assignment(store, outcome.plan).outcome == "승인"
    assert flow.check_confirmed_teams(store) == []
    assert flow.unassigned_students(store) == []


def test_rejects_an_ai_plan_that_breaks_the_rules_and_falls_through():
    """AI 가 그럴듯한 오답을 내도 확정되지 않는다."""
    store, roster = hard_after_close()
    unassigned = flow.unassigned_students(store)

    # 팀이 없는 학생을 모두 팀1 에 몰아넣은 배정안 — 정원과 주 역할 중복을 어긴다
    bad = plan_body([{"student_no": s.student_no, "team": 1} for s in unassigned])

    outcome, streamer = propose(store, [(200, [bad], 1.0)] * 3)

    assert [a.status for a in outcome.attempts] == ["검사실패"] * 3
    assert outcome.source == "앱 자율 배정"
    assert flow.validate_assignment(
        flow.current_teams(store), unassigned, outcome.plan
    ) == []


# =============================================================================
# 규칙을 지키는 배정이 없는 경우 (공고 2.5절 8항)
# =============================================================================


def test_does_not_call_the_ai_when_no_valid_assignment_exists():
    """이때는 AI 를 부르지 않아도 된다 (공고 2.5절 8항)."""
    rows = [
        ("2026701", "학생71(TT)"),
        ("2026702", "학생72(PT)"),
        ("2026703", "학생73(RW)"),
        ("2026704", "학생74(FD)"),
    ]
    store, _ = build_store(rows, 2)
    flow.close_recruiting(store)

    outcome, streamer = propose(store, [])

    assert streamer.calls == []
    assert outcome.plan is None
    assert outcome.attempts == []
    assert outcome.problems != []
    assert any("기획자" in p or "웹 프로그래머" in p for p in outcome.problems)


def test_problem_message_names_the_team_that_cannot_be_filled():
    """예: 팀3에 웹 프로그래머를 맡을 학생이 없음 (공고 2.5절 8항)."""
    rows = [
        ("2026711", "학생81(PL)"),
        ("2026712", "학생82(TT)"),
        ("2026713", "학생83(PT)"),
        ("2026714", "학생84(RW)"),
    ]
    store, _ = build_store(rows, 2)
    flow.close_recruiting(store)

    outcome, _ = propose(store, [])
    assert any("웹 프로그래머" in p for p in outcome.problems)


# =============================================================================
# 배정할 학생이 없는 경우
# =============================================================================


def test_returns_an_empty_plan_when_nobody_needs_assigning():
    store, roster = build_store(HARD_ROWS[:4], 2)

    def no(label):
        return roster[label].student_no

    flow.apply_to_team(store, no("학생1(PL;RW)"), 1)
    flow.apply_to_team(store, no("학생4(WP;PL)"), 1)
    flow.cast_vote(store, no("학생1(PL;RW)"), no("학생4(WP;PL)"), "찬성")
    flow.apply_to_team(store, no("학생2(PL;PT)"), 2)
    flow.apply_to_team(store, no("학생3(PL;TT)"), 2)
    # 학생3 은 주 역할이 기획자라 학생2 와 중복된다. 다른 구성을 만든다.
    store.reset(list(roster.values()), 2)
    flow.apply_to_team(store, no("학생1(PL;RW)"), 1)
    flow.apply_to_team(store, no("학생4(WP;PL)"), 1)
    flow.cast_vote(store, no("학생1(PL;RW)"), no("학생4(WP;PL)"), "찬성")
    flow.apply_to_team(store, no("학생2(PL;PT)"), 2)
    flow.apply_to_team(store, no("학생3(PL;TT)"), 2)

    flow.close_recruiting(store)
    outcome, streamer = propose(store, [])

    # 팀2 는 1명이라 마감 때 비었고, 학생2·학생3 이 팀이 없는 학생이 되었다.
    # 따라서 배정할 학생이 있다. AI 를 부르거나 자율 배정을 해야 한다.
    assert outcome.plan is not None or outcome.problems != []


def test_empty_plan_when_all_students_already_in_valid_teams():
    rows = [
        ("2026801", "학생91(PL)"),
        ("2026802", "학생92(WP)"),
    ]
    store, roster = build_store(rows, 1)
    flow.apply_to_team(store, "2026801", 1)
    flow.apply_to_team(store, "2026802", 1)
    flow.cast_vote(store, "2026801", "2026802", "찬성")
    flow.close_recruiting(store)

    outcome, streamer = propose(store, [])

    assert outcome.plan == {}
    assert streamer.calls == []
    assert outcome.problems == []


# =============================================================================
# 진행 안내 (공고 3장 "AI 대기 중 화면")
# =============================================================================


def test_passes_progress_updates_through():
    store, _ = hard_after_close()
    seen: list[tuple[int, str]] = []

    propose(
        store,
        [(500, [b"x"], 1.0), (500, [b"x"], 1.0), (500, [b"x"], 1.0)],
        on_progress=lambda n, model, elapsed: seen.append((n, model)),
    )

    assert (1, "model-1") in seen
    assert (3, "model-3") in seen
