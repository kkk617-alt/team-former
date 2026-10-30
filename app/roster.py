"""명단 CSV 파싱 (공고 2.6절).

나눠 주는 CSV 는 엑셀에서 한글이 깨지지 않도록 BOM 이 붙은 UTF-8 이므로
utf-8-sig 로 읽는다. BOM 이 없는 파일도 같은 코덱으로 읽힌다.

    student_no,name,main_role,sub_roles
    2026001,가나다,기획자,보고서 작성자
    2026002,라마바,웹 프로그래머,
    2026003,사아자,테스터,기획자;발표자
"""

from __future__ import annotations

import csv
import io

from .roles import ALL_ROLES, is_valid_role
from .rules import Student

COLUMNS = ("student_no", "name", "main_role", "sub_roles")
MAX_SUB_ROLES = 2

#: 관리자 계정이 쓰는 학번. 명단에 들어올 수 없다 (공고 2.1절).
ADMIN_STUDENT_NO = "admin"


class RosterError(Exception):
    """명단 CSV 가 잘못된 경우. 메시지를 관리자 화면에 그대로 보여 준다."""


def parse_roster(data: bytes) -> list[Student]:
    """명단 CSV 의 바이트를 학생 목록으로 바꾼다.

    Raises:
        RosterError: 열이 모자라거나, 역할 이름이 6개 밖이거나, 학번이 겹칠 때.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RosterError(
            "CSV 를 UTF-8 로 읽을 수 없음. 엑셀에서 "
            "'CSV UTF-8(쉼표로 분리)' 형식으로 저장해야 함"
        ) from exc

    reader = csv.DictReader(io.StringIO(text))

    missing = [column for column in COLUMNS if column not in (reader.fieldnames or [])]
    if missing:
        raise RosterError(
            f"CSV 에 {', '.join(missing)} 열이 없음. "
            f"첫 줄은 {','.join(COLUMNS)} 이어야 함"
        )

    students: list[Student] = []
    seen: set[str] = set()

    for offset, row in enumerate(reader):
        # DictReader 는 머리글을 1번째 줄로 먹었으므로 +2 가 파일의 줄 번호다.
        line_no = offset + 2
        student = _parse_row(row, line_no)
        if student is None:
            continue
        if student.student_no in seen:
            raise RosterError(
                f"{line_no}번째 줄: 학번 {student.student_no} 이 이미 나왔음"
            )
        seen.add(student.student_no)
        students.append(student)

    if not students:
        raise RosterError("명단이 비어 있음")

    return students


def _parse_row(row: dict[str, str | None], line_no: int) -> Student | None:
    student_no = _clean(row.get("student_no"))
    name = _clean(row.get("name"))
    main_role = _clean(row.get("main_role"))
    raw_sub_roles = _clean(row.get("sub_roles"))

    # 아무 값도 없는 줄은 건너뛴다 (파일 끝의 빈 줄 등)
    if not any((student_no, name, main_role, raw_sub_roles)):
        return None

    if not student_no:
        raise RosterError(f"{line_no}번째 줄: 학번이 비어 있음")
    if student_no.lower() == ADMIN_STUDENT_NO:
        raise RosterError(
            f"{line_no}번째 줄: 학번 '{ADMIN_STUDENT_NO}' 은 관리자 계정이 쓰므로 "
            "명단에 넣을 수 없음"
        )
    if not name:
        raise RosterError(f"{line_no}번째 줄: 이름이 비어 있음")

    if not is_valid_role(main_role):
        raise RosterError(
            f"{line_no}번째 줄: 주 역할 '{main_role}' 은 역할이 아님. "
            f"써야 하는 값: {', '.join(ALL_ROLES)}"
        )

    sub_roles = _parse_sub_roles(raw_sub_roles, main_role, line_no)
    return Student(
        student_no=student_no,
        name=name,
        main_role=main_role,
        sub_roles=sub_roles,
    )


def _parse_sub_roles(raw: str, main_role: str, line_no: int) -> tuple[str, ...]:
    if not raw:
        return ()

    parts = [part.strip() for part in raw.split(";")]
    parts = [part for part in parts if part]

    if len(parts) > MAX_SUB_ROLES:
        raise RosterError(
            f"{line_no}번째 줄: 보조 역할이 {len(parts)}개임 "
            f"(최대 {MAX_SUB_ROLES}개)"
        )

    sub_roles: list[str] = []
    for part in parts:
        if not is_valid_role(part):
            raise RosterError(
                f"{line_no}번째 줄: 보조 역할 '{part}' 은 역할이 아님. "
                f"써야 하는 값: {', '.join(ALL_ROLES)}"
            )
        # 주 역할과 같은 보조 역할은 담당 가능 역할을 늘리지 않으므로 버린다.
        if part == main_role or part in sub_roles:
            continue
        sub_roles.append(part)

    return tuple(sub_roles)


def _clean(value: str | None) -> str:
    return (value or "").strip()
