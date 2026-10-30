"""오픈라우터 모델 체인 테스트 (공고 2.5절 5항, 4.3절, 3장).

HTTP 는 streamer 로 주입해 가짜를 쓴다. 시간은 now 로 주입해 진짜로 기다리지
않고 전여 대기 시간 규칙을 검증한다.
"""

from __future__ import annotations

import json

import pytest

from app import ai
from app.rules import Student

from conftest import HARD_ROWS, make_roster


def plan_body(assignments: list[dict]) -> bytes:
    """오픈라우터 응답 한 벌."""
    content = json.dumps({"assignments": assignments}, ensure_ascii=False)
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


def raw_body(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeStreamer:
    """호출마다 미리 정한 응답을 돌려준다.

    responses: [(status_code, [chunk, ...], seconds_per_chunk)]
    """

    def __init__(self, responses, clock: FakeClock) -> None:
        self.responses = list(responses)
        self.clock = clock
        self.calls: list[str] = []

    def __call__(self, *, model, body, api_key, timeout_seconds):
        self.calls.append(model)
        status, chunks, per_chunk = self.responses.pop(0)

        def generate():
            for chunk in chunks:
                self.clock.advance(per_chunk)
                yield chunk

        return status, generate()


@pytest.fixture
def roster() -> dict[str, Student]:
    return make_roster(HARD_ROWS)


@pytest.fixture
def situation(roster):
    """어려움 14단계 직후와 비슷한 상황."""
    teams = {
        1: [roster["학생1(PL;RW)"], roster["학생4(WP;PL)"]],
        2: [roster["학생2(PL;PT)"], roster["학생8(FD;TT)"]],
    }
    unassigned = [roster["학생3(PL;TT)"], roster["학생5(WP;FD)"]]
    return teams, unassigned


def accept_all(_plan):
    return []


def reject_all(_plan):
    return ["팀3에 웹 프로그래머를 맡을 학생이 없음"]


def run(situation, responses, *, validate=accept_all, models=None, clock=None, **kwargs):
    teams, unassigned = situation
    clock = clock or FakeClock()
    streamer = FakeStreamer(responses, clock)
    result = ai.request_assignment(
        teams=teams,
        unassigned=unassigned,
        models=models or ["model-1", "model-2", "model-3"],
        api_key="테스트-키",
        validate=validate,
        streamer=streamer,
        now=clock,
        **kwargs,
    )
    return result, streamer, clock


# =============================================================================
# 성공
# =============================================================================


def test_parses_assignment_from_first_model(situation):
    body = plan_body([
        {"student_no": "2026303", "team": 1},
        {"student_no": "2026305", "team": 2},
    ])
    result, streamer, _ = run(situation, [(200, [body], 1.0)])

    assert result.plan == {"2026303": 1, "2026305": 2}
    assert result.succeeded
    assert streamer.calls == ["model-1"]
    assert [a.status for a in result.attempts] == ["성공"]


def test_tolerates_json_wrapped_in_a_code_fence(situation):
    content = '```json\n{"assignments": [{"student_no": "2026303", "team": 1}]}\n```'
    result, _, _ = run(situation, [(200, [raw_body(content)], 1.0)])
    assert result.plan == {"2026303": 1}


def test_accepts_team_key_spelled_team_no(situation):
    content = '{"assignments": [{"student_no": "2026303", "team_no": 2}]}'
    result, _, _ = run(situation, [(200, [raw_body(content)], 1.0)])
    assert result.plan == {"2026303": 2}


def test_records_elapsed_time_for_each_attempt(situation):
    body = plan_body([{"student_no": "2026303", "team": 1}])
    result, _, _ = run(situation, [(200, [body], 3.0)])
    assert result.attempts[0].elapsed_ms == 3000


# =============================================================================
# 실패 뒤 다음 모델로 넘어감 (공고 2.5절 5항)
# =============================================================================


def test_falls_through_on_http_429(situation):
    """무료 모델은 사용량이 많다며 거절하는 일이 잦다 (공고 4.3절)."""
    good = plan_body([{"student_no": "2026303", "team": 1}])
    result, streamer, _ = run(
        situation,
        [(429, [b'{"error":"rate limited"}'], 0.5), (200, [good], 0.5)],
    )

    assert streamer.calls == ["model-1", "model-2"]
    assert result.attempts[0].status == "HTTP오류"
    assert "429" in result.attempts[0].detail
    assert result.succeeded


def test_falls_through_on_empty_content(situation):
    """추론 모델은 생각하는 데 토큰을 다 써서 빈 응답을 낼 수 있다 (공고 4.3절)."""
    good = plan_body([{"student_no": "2026303", "team": 1}])
    result, streamer, _ = run(situation, [(200, [raw_body("")], 0.5), (200, [good], 0.5)])

    assert result.attempts[0].status == "빈응답"
    assert streamer.calls == ["model-1", "model-2"]


def test_falls_through_on_malformed_json(situation):
    good = plan_body([{"student_no": "2026303", "team": 1}])
    result, streamer, _ = run(
        situation,
        [(200, [raw_body("배정은 알아서 하시면 됩니다")], 0.5), (200, [good], 0.5)],
    )

    assert result.attempts[0].status == "형식오류"
    assert streamer.calls == ["model-1", "model-2"]


def test_falls_through_when_plan_fails_validation(situation):
    """배정안이 2.5절 4항의 검사를 통과하지 못하면 실패로 본다."""
    body = plan_body([{"student_no": "2026303", "team": 1}])
    result, streamer, _ = run(
        situation, [(200, [body], 0.5), (200, [body], 0.5), (200, [body], 0.5)],
        validate=reject_all,
    )

    assert [a.status for a in result.attempts] == ["검사실패"] * 3
    assert "웹 프로그래머" in result.attempts[0].detail
    assert result.plan is None
    assert not result.succeeded


def test_gives_up_after_three_models(situation):
    result, streamer, _ = run(
        situation,
        [(500, [b"oops"], 0.5), (500, [b"oops"], 0.5), (500, [b"oops"], 0.5)],
    )

    assert streamer.calls == ["model-1", "model-2", "model-3"]
    assert len(result.attempts) == 3
    assert result.plan is None


# =============================================================================
# 전여 120초 대기 시간 (공고 3장의 어려운 해결)
#
# requests 의 timeout 인자는 다음 바이트를 기다리는 시간만 재므로, 응답이 조금씩
# 천천히 오면 전체 시간은 120초를 넘긴다. 그래서 청크마다 경과 시간을 본다.
# =============================================================================


def test_aborts_when_total_wall_clock_exceeds_the_limit(situation):
    """청크는 각각 30초 안에 오지만 전체로는 120초를 넘긴다. 끊어야 한다."""
    good = plan_body([{"student_no": "2026303", "team": 1}])
    clock = FakeClock()
    slow = (200, [b'{"choices": [{"message":', b' {"content":', b' "..."', b"}}]}"], 40.0)
    result, streamer, _ = run(
        situation, [slow, (200, [good], 1.0)], clock=clock, timeout_seconds=120.0
    )

    assert result.attempts[0].status == "시간초과"
    assert streamer.calls == ["model-1", "model-2"]
    assert result.succeeded


def test_does_not_abort_a_response_that_finishes_in_time(situation):
    good = plan_body([{"student_no": "2026303", "team": 1}])
    result, _, _ = run(
        situation, [(200, [good], 100.0)], timeout_seconds=120.0
    )
    assert result.attempts[0].status == "성공"


def test_timeout_detail_reports_the_limit(situation):
    good = plan_body([{"student_no": "2026303", "team": 1}])
    slow = (200, [b"{", b"}", b"{", b"}"], 50.0)
    result, _, _ = run(situation, [slow, (200, [good], 1.0)], timeout_seconds=120.0)
    assert "120" in result.attempts[0].detail


# =============================================================================
# 진행 안내 (공고 3장 "AI 대기 중 화면" 의 어려운 해결)
# =============================================================================


def test_reports_which_model_is_being_waited_on(situation):
    good = plan_body([{"student_no": "2026303", "team": 1}])
    seen: list[tuple[int, str]] = []

    teams, unassigned = situation
    clock = FakeClock()
    ai.request_assignment(
        teams=teams,
        unassigned=unassigned,
        models=["model-1", "model-2"],
        api_key="테스트-키",
        validate=accept_all,
        streamer=FakeStreamer([(500, [b"x"], 1.0), (200, [good], 1.0)], clock),
        now=clock,
        on_progress=lambda attempt_no, model, elapsed: seen.append((attempt_no, model)),
    )

    assert (1, "model-1") in seen
    assert (2, "model-2") in seen


# =============================================================================
# 프롬프트
# =============================================================================


def test_prompt_states_the_rules_and_the_situation(situation, roster):
    teams, unassigned = situation
    prompt = ai.build_prompt(teams, unassigned)

    # 규칙
    assert "2~4" in prompt
    assert "주 역할" in prompt
    assert "기획자" in prompt and "웹 프로그래머" in prompt
    # 지금 팀 구성과 팀이 없는 학생
    assert roster["학생1(PL;RW)"].name in prompt
    assert roster["학생3(PL;TT)"].name in prompt
    assert "2026303" in prompt
    # 이미 팀에 있는 학생은 옮기지 않는다는 지시
    assert "옮기지" in prompt


def test_prompt_lists_sub_roles(situation, roster):
    teams, unassigned = situation
    prompt = ai.build_prompt(teams, unassigned)
    assert "프론트엔드 디자이너" in prompt  # 학생5(WP;FD) 의 보조 역할


# =============================================================================
# 금지 사항 (공고 6.3절 14번, -2점)
# =============================================================================


def test_default_models_do_not_use_the_free_router():
    for model in ai.DEFAULT_MODELS:
        assert model != "openrouter/free"
        assert not model.startswith("openrouter/free")


def test_request_body_asks_for_low_reasoning_effort(situation):
    """빈 응답을 줄이기 위한 설정 (공고 4.3절)."""
    body = ai.build_request_body("some-model", "프롬프트")
    assert body["reasoning"]["effort"] == "low"
    assert body["max_tokens"] >= 2000
