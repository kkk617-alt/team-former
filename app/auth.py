"""로그인과 비밀번호 해시 (공고 3장 끝, 6.3절 10·11·12번).

비밀번호는 bcrypt 해시로만 저장한다. 해시는 원래대로 되돌릴 수 없는 다른
문자열이고, 로그인할 때는 입력한 비밀번호를 같은 방법으로 바꿔 저장된 값과
비교한다. DB 가 새어 나가도 원래 비밀번호를 알 수 없다.

구글 로그인(st.login)은 쓰지 않는다. 채점자가 학생 여러 명으로 번갈아
로그인해야 하기 때문이다 (공고 3장).
"""

from __future__ import annotations

from dataclasses import dataclass

import bcrypt

from .rules import Student
from .store import Store

#: 관리자가 쓰는 학번 (공고 2.1절)
ADMIN_STUDENT_NO = "admin"

#: 학생의 비밀번호는 모두 이 값이다 (공고 2.2절)
STUDENT_PASSWORD = "1234"

#: bcrypt 는 72바이트까지만 쓴다. 해시할 때와 확인할 때 같은 방식으로 잘라야
#: 긴 관리자 비밀번호에서도 로그인이 된다.
_BCRYPT_MAX_BYTES = 72


@dataclass(frozen=True)
class Account:
    """로그인한 사람."""

    student_no: str
    name: str
    is_admin: bool
    #: 학생이면 그 학생, 관리자면 None
    student: Student | None = None


def _encode(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """비밀번호를 bcrypt 해시로 바꾼다.

    Raises:
        ValueError: 빈 비밀번호.
    """
    if not plain:
        raise ValueError("비밀번호가 비어 있음")
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """입력한 비밀번호가 저장된 해시와 맞는지.

    DB 에 해시가 아닌 값이 들어 있어도 예외를 던지지 않고 거부한다.
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def authenticate(store: Store, student_no: str, password: str) -> Account | None:
    """학번과 비밀번호로 로그인한다. 맞지 않으면 None.

    비밀번호를 확인하지 않고 통과시키는 경로가 없어야 한다 (공고 6.3절 12번).
    """
    student_no = (student_no or "").strip()
    if not student_no or not password:
        return None

    if student_no.lower() == ADMIN_STUDENT_NO:
        student_no = ADMIN_STUDENT_NO

    hashed = store.password_hash(student_no)
    if hashed is None:
        return None
    if not verify_password(password, hashed):
        return None

    if store.is_admin(student_no):
        return Account(student_no=student_no, name="관리자", is_admin=True)

    student = store.student(student_no)
    if student is None:
        return None
    return Account(
        student_no=student_no,
        name=student.name,
        is_admin=False,
        student=student,
    )
