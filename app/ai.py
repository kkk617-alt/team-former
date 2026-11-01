"""오픈라우터 모델 체인 (공고 2.5절 5항, 4.3절).

모델 3개를 1차·2차·3차로 차례로 부른다. 앞 모델이 실패하면 다음 모델로 넘어가고,
3차까지 실패하면 호출하는 쪽(app/assign.py)이 스스로 배정한다.

실패로 보는 경우
  HTTP 오류(429 포함), 빈 응답, 형식 오류, 전체 120초 초과,
  그리고 배정안이 공고 2.5절 4항의 검사를 통과하지 못한 경우

HTTP 와 시간은 주입받는다(streamer, now). 테스트가 진짜로 기다리거나 진짜
모델을 부르지 않게 하려는 것이다.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Mapping, Protocol, Sequence

from .roles import ABBREV_BY_ROLE
from .rules import MAX_TEAM_SIZE, MIN_TEAM_SIZE, Student

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

#: 모델 하나에 허용하는 전체 대기 시간 (공고 2.5절 5항)
TIMEOUT_SECONDS = 120.0

#: 연결이 맺어지기를 기다리는 시간
CONNECT_TIMEOUT = 15.0

#: 추론에 토큰을 다 써서 빈 응답이 되는 것을 줄이기 위한 한도 (공고 4.3절).
#: 4096 으로 시험했을 때 생각만 하다 빈 응답을 내는 모델이 있어 늘렸다.
#: 배정안 JSON 자체는 길어야 1천 토큰이 안 된다.
MAX_TOKENS = 16384

#: 1차·2차·3차 모델.
#:
#: 무료 모델은 이름이 :free 로 끝난다. 무료 모델로 자동 연결하는 라우터
#: (openrouter/free) 는 쓰지 않는다 — 다음 모델로 넘어가는 처리를 직접 만드는 것이
#: 과제의 일부이고, 쓰면 2점이 깎인다 (공고 6.3절 14번).
#:
#: 오픈라우터의 무료 모델 목록은 수시로 바뀐다. 제출 전에
#: https://openrouter.ai/models?max_price=0 에서 살아 있는지 확인하고, 필요하면
#: .env 의 AI_MODEL_1/2/3 으로 바꾼다.
#: 제공자를 셋 다 다르게 골랐다. 한 곳이 막히거나 느려도 체인이 살아남는다.
#: 2026-10-30 에 scripts/check_setup.py 로 셋 다 쓸 수 있음을 확인했다.
#: 추론형보다 지시형(instruct)을 앞에 둔다. 추론형은 생각하는 데 토큰을 다 써
#: 빈 응답을 내거나 120초를 넘기는 일이 잦았다.
DEFAULT_MODELS: tuple[str, str, str] = (
    "google/gemma-4-31b-it:free",
    "dots-studio/dots-3-note-preview:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
)

# 결과 상태 (tf_ai_logs.status 의 검사 제약과 같아야 한다)
SUCCESS = "성공"
TIMEOUT = "시간초과"
HTTP_ERROR = "HTTP오류"
EMPTY = "빈응답"
MALFORMED = "형식오류"
INVALID = "검사실패"


class Streamer(Protocol):
    """HTTP 한 번. 본문을 조금씩 돌려주어야 전체 대기 시간을 잴 수 있다."""

    def __call__(
        self, *, model: str, body: dict, api_key: str, timeout_seconds: float
    ) -> tuple[int, Iterator[bytes]]: ...


class PlanFormatError(Exception):
    """응답에서 배정안을 꺼낼 수 없음."""


class DeadlineExceeded(Exception):
    """전체 대기 시간을 넘김."""


@dataclass(frozen=True)
class AiAttempt:
    """모델 한 번 호출의 기록. tf_ai_logs 한 행이 된다."""

    attempt_no: int
    model: str
    status: str
    detail: str | None
    elapsed_ms: int


@dataclass(frozen=True)
class AiResult:
    plan: dict[str, int] | None
    attempts: list[AiAttempt]

    @property
    def succeeded(self) -> bool:
        return self.plan is not None


# =============================================================================
# 프롬프트
# =============================================================================


def _describe(student: Student) -> str:
    sub = ", ".join(ABBREV_BY_ROLE[r] for r in student.sub_roles) or "없음"
    return (
        f"- {student.student_no} {student.name} / "
        f"주 역할 {student.main_role} / 보조 역할 {sub}"
    )


def build_prompt(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
) -> str:
    """지금 팀 구성, 팀이 없는 학생, 규칙을 모델에게 설명한다 (공고 2.5절 3항)."""
    lines: list[str] = []

    lines.append("너는 대학 수업의 팀 편성을 돕는다. 아래 규칙을 모두 지키는 배정을 만들어라.")
    lines.append("")
    lines.append("[규칙]")
    lines.append(f"1. 배정이 끝난 뒤 모든 팀의 인원은 {MIN_TEAM_SIZE}~{MAX_TEAM_SIZE}명이어야 한다. 빈 팀이 없어야 한다.")
    lines.append("2. 한 팀에 주 역할이 같은 학생이 2명 이상 있으면 안 된다.")
    lines.append(
        "3. 모든 팀에는 기획자를 맡을 학생과 웹 프로그래머를 맡을 학생이 "
        "서로 다른 사람으로 1명씩 있어야 한다. 주 역할이든 보조 역할이든 "
        "그 역할을 담당할 수 있으면 맡을 수 있다. 한 학생이 두 역할을 다 "
        "담당할 수 있어도 한 역할만 맡는 것으로 센다."
    )
    lines.append("4. 팀이 없는 학생을 빠짐없이, 각각 정확히 한 팀에만 배정하라.")
    lines.append("5. 이미 팀에 있는 학생은 절대 옮기지 마라. 팀이 없는 학생만 넣어라.")
    lines.append("")

    lines.append("[지금 팀 구성]")
    for team_no in sorted(teams):
        members = teams[team_no]
        if members:
            lines.append(f"팀{team_no} ({len(members)}명)")
            lines.extend(_describe(s) for s in members)
        else:
            lines.append(f"팀{team_no} (0명, 비어 있음)")
    lines.append("")

    lines.append(f"[팀이 없는 학생] {len(unassigned)}명")
    lines.extend(_describe(s) for s in unassigned)
    lines.append("")

    lines.append("[답하는 형식]")
    lines.append("설명이나 인사말 없이 아래 모양의 JSON 만 출력하라.")
    lines.append('{"assignments": [{"student_no": "학번", "team": 팀번호}]}')
    lines.append("student_no 는 문자열, team 은 정수다.")

    return "\n".join(lines)


def build_request_body(model: str, prompt: str) -> dict:
    """오픈라우터 요청 본문.

    reasoning.effort 를 low 로 주고 max_tokens 를 넉넉히 두어, 추론 모델이 생각하는
    데 토큰을 다 써서 빈 응답을 내는 일을 줄인다 (공고 4.3절).
    """
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
        "reasoning": {"effort": "low"},
    }


# =============================================================================
# 응답 해석
# =============================================================================


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    # 첫 줄은 ``` 또는 ```json
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


def _loads_lenient(text: str) -> object:
    """모델이 JSON 앞뒤에 말을 붙여도 가운데를 꺼내 읽는다."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise PlanFormatError("응답에서 JSON 을 찾지 못함")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise PlanFormatError(f"JSON 을 읽을 수 없음: {exc}") from exc


def parse_plan(content: str) -> dict[str, int]:
    """모델이 낸 글에서 {학번: 팀 번호} 를 꺼낸다."""
    data = _loads_lenient(_strip_code_fence(content))
    if not isinstance(data, dict):
        raise PlanFormatError("JSON 의 가장 바깥이 객체가 아님")

    items = data.get("assignments")
    if not isinstance(items, list):
        raise PlanFormatError("assignments 가 배열이 아님")

    plan: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            raise PlanFormatError("assignments 의 원소가 객체가 아님")
        student_no = item.get("student_no")
        team = item.get("team", item.get("team_no"))
        if student_no is None or team is None:
            raise PlanFormatError("student_no 또는 team 이 없음")
        try:
            plan[str(student_no).strip()] = int(team)
        except (TypeError, ValueError) as exc:
            raise PlanFormatError(f"team 이 정수가 아님: {team!r}") from exc

    if not plan:
        raise PlanFormatError("assignments 가 비어 있음")
    return plan


def _extract_content(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise PlanFormatError(f"응답 본문이 JSON 이 아님: {exc}") from exc

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise PlanFormatError("응답에 choices 가 없음")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        content = choices[0].get("text")
    return content or ""


# =============================================================================
# 호출
# =============================================================================


def _read_within_deadline(
    chunks: Iterator[bytes],
    deadline: float,
    now: Callable[[], float],
    on_tick: Callable[[], None] | None = None,
) -> bytes:
    """본문을 읽되 전체 대기 시간을 넘기면 끊는다.

    requests 의 timeout 인자는 다음 바이트를 기다리는 시간만 재므로, 응답이 조금씩
    천천히 오면 전체 시간이 제한을 넘는다. 그래서 청크마다 시각을 확인한다
    (공고 3장 "AI 응답이 늦을 때" 의 어려운 해결).
    """
    buffer = bytearray()
    try:
        for chunk in chunks:
            buffer.extend(chunk)
            if on_tick is not None:
                on_tick()
            if now() > deadline:
                raise DeadlineExceeded()
    finally:
        close = getattr(chunks, "close", None)
        if close is not None:
            close()
    return bytes(buffer)


def request_assignment(
    *,
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
    models: Sequence[str],
    api_key: str,
    validate: Callable[[dict[str, int]], list[str]],
    streamer: Streamer,
    timeout_seconds: float = TIMEOUT_SECONDS,
    on_progress: Callable[[int, str, float], None] | None = None,
    now: Callable[[], float] = time.monotonic,
) -> AiResult:
    """모델을 차례로 불러 검사를 통과하는 배정안을 받는다.

    Args:
        validate: 배정안을 받아 위반 사유 목록을 돌려준다. 비어 있으면 통과.
        on_progress: (몇 차, 모델 이름, 경과 초) 로 불린다. 화면의 assign_status
            에 "2차 모델 응답 대기 중" 처럼 보여 주기 위한 것이다.
    """
    prompt = build_prompt(teams, unassigned)
    attempts: list[AiAttempt] = []

    for index, model in enumerate(models, start=1):
        started = now()
        deadline = started + timeout_seconds

        def report() -> None:
            if on_progress is not None:
                on_progress(index, model, now() - started)

        report()

        status, detail, plan = _attempt(
            model=model,
            prompt=prompt,
            api_key=api_key,
            validate=validate,
            streamer=streamer,
            timeout_seconds=timeout_seconds,
            deadline=deadline,
            now=now,
            on_tick=report,
        )

        attempts.append(
            AiAttempt(
                attempt_no=index,
                model=model,
                status=status,
                detail=detail,
                elapsed_ms=int(round((now() - started) * 1000)),
            )
        )

        if status == SUCCESS:
            return AiResult(plan=plan, attempts=attempts)

    return AiResult(plan=None, attempts=attempts)


def _attempt(
    *,
    model: str,
    prompt: str,
    api_key: str,
    validate: Callable[[dict[str, int]], list[str]],
    streamer: Streamer,
    timeout_seconds: float,
    deadline: float,
    now: Callable[[], float],
    on_tick: Callable[[], None],
) -> tuple[str, str | None, dict[str, int] | None]:
    """모델 하나를 부른 결과를 (상태, 설명, 배정안) 으로 돌려준다."""
    body = build_request_body(model, prompt)

    try:
        status_code, chunks = streamer(
            model=model, body=body, api_key=api_key, timeout_seconds=timeout_seconds
        )
    except Exception as exc:  # 연결 실패, 읽기 시간 초과 등
        return HTTP_ERROR, f"{type(exc).__name__}: {exc}"[:500], None

    try:
        raw = _read_within_deadline(chunks, deadline, now, on_tick)
    except DeadlineExceeded:
        return TIMEOUT, f"{timeout_seconds:.0f}초 안에 응답을 받지 못해 끊음", None
    except Exception as exc:
        return HTTP_ERROR, f"{type(exc).__name__}: {exc}"[:500], None

    if status_code != 200:
        snippet = raw.decode("utf-8", errors="replace")[:300]
        return HTTP_ERROR, f"HTTP {status_code}: {snippet}", None

    try:
        content = _extract_content(raw)
    except PlanFormatError as exc:
        return MALFORMED, str(exc), None

    if not content.strip():
        return EMPTY, "모델이 빈 응답을 보냄", None

    try:
        plan = parse_plan(content)
    except PlanFormatError as exc:
        return MALFORMED, f"{exc} (응답 앞부분: {content.strip()[:200]})", None

    problems = validate(plan)
    if problems:
        return INVALID, "; ".join(problems)[:500], None

    return SUCCESS, None, plan


# =============================================================================
# 실제 HTTP
# =============================================================================


def requests_streamer(
    *, model: str, body: dict, api_key: str, timeout_seconds: float
) -> tuple[int, Iterator[bytes]]:
    """requests 로 오픈라우터를 부른다.

    stream=True 로 본문을 조금씩 받아 전체 대기 시간을 잴 수 있게 한다. API 키는
    헤더에만 넣고 어디에도 기록하지 않는다 (공고 6.3절 8번).
    """
    import requests

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        stream=True,
        timeout=(CONNECT_TIMEOUT, timeout_seconds),
    )

    def iterate() -> Iterator[bytes]:
        try:
            yield from response.iter_content(chunk_size=1024)
        finally:
            response.close()

    return response.status_code, iterate()
