"""역할 정의 (공고 2.2절, 2.3절).

역할 문자열을 코드 여러 곳에 흩어 적지 않기 위해 여기에 모은다. DB 의 tf_role
도메인과 이 목록이 같아야 한다 (schema.sql 참고).
"""

from __future__ import annotations

PLANNER = "기획자"
WEB_DEV = "웹 프로그래머"
FRONTEND = "프론트엔드 디자이너"
TESTER = "테스터"
REPORTER = "보고서 작성자"
PRESENTER = "발표자"

#: 공고 2.2절의 6개 역할. CSV 검증과 화면 표시 순서로 쓴다.
ALL_ROLES: tuple[str, ...] = (
    PLANNER,
    WEB_DEV,
    FRONTEND,
    TESTER,
    REPORTER,
    PRESENTER,
)

#: 모든 팀에 서로 다른 사람으로 1명씩 있어야 하는 역할 (공고 2.3절)
REQUIRED_ROLES: tuple[str, ...] = (PLANNER, WEB_DEV)

#: 부록 명단 표기의 약자. 화면에 역할을 짧게 보여 줄 때 쓴다.
ABBREV_BY_ROLE: dict[str, str] = {
    PLANNER: "PL",
    WEB_DEV: "WP",
    FRONTEND: "FD",
    TESTER: "TT",
    REPORTER: "RW",
    PRESENTER: "PT",
}


def is_valid_role(value: str) -> bool:
    return value in ALL_ROLES
