"""로그인과 비밀번호 해시 테스트.

공고 6.3절의 감점 항목을 직접 겨눈다.
  10번 비밀번호를 해시하지 않고 적힌 그대로 DB 에 저장함 (-2점)
  11번 학생 계정으로 관리자 기능을 쓸 수 있음 (-3점)
  12번 비밀번호가 틀려도 로그인되거나 학번만으로 남의 계정에 들어갈 수 있음 (-3점)
"""

from __future__ import annotations

import pytest

from app import auth
from app.roster import parse_roster

from conftest import FIXTURES
from memstore import InMemoryStore

STUDENT_PASSWORD = "1234"
ADMIN_PASSWORD = "관리자-비밀-값"


@pytest.fixture
def store() -> InMemoryStore:
    students = parse_roster((FIXTURES / "쉬움.csv").read_bytes())
    store = InMemoryStore()
    store.replace_roster(students, 3, auth.hash_password(STUDENT_PASSWORD))
    store.ensure_admin(auth.hash_password(ADMIN_PASSWORD))
    return store


# =============================================================================
# 해시 (공고 6.3절 10번)
# =============================================================================


def test_hash_does_not_contain_the_password():
    hashed = auth.hash_password("비밀1234")
    assert "비밀1234" not in hashed


def test_hash_looks_like_bcrypt():
    assert auth.hash_password("1234").startswith("$2b$")


def test_same_password_hashes_differently_each_time():
    """소금(salt)이 붙으므로 같은 비밀번호도 매번 다른 해시가 된다."""
    assert auth.hash_password("1234") != auth.hash_password("1234")


def test_verify_accepts_the_right_password():
    hashed = auth.hash_password("1234")
    assert auth.verify_password("1234", hashed)


def test_verify_rejects_the_wrong_password():
    hashed = auth.hash_password("1234")
    assert not auth.verify_password("4321", hashed)


def test_verify_rejects_an_empty_password():
    hashed = auth.hash_password("1234")
    assert not auth.verify_password("", hashed)


def test_verify_returns_false_on_a_broken_hash():
    """DB 에 이상한 값이 들어 있어도 예외를 던지지 않고 거부한다."""
    assert not auth.verify_password("1234", "해시가-아닌-값")
    assert not auth.verify_password("1234", "")


def test_hash_rejects_an_empty_password():
    with pytest.raises(ValueError):
        auth.hash_password("")


# =============================================================================
# 로그인 (공고 6.3절 12번)
# =============================================================================


def test_login_succeeds_with_the_right_credentials(store):
    account = auth.authenticate(store, "2026101", STUDENT_PASSWORD)
    assert account is not None
    assert account.student.name == "학생1(PL;RW)"
    assert not account.is_admin


def test_login_fails_with_the_wrong_password(store):
    assert auth.authenticate(store, "2026101", "틀린값") is None


def test_login_fails_with_an_empty_password(store):
    assert auth.authenticate(store, "2026101", "") is None


def test_login_fails_for_an_unknown_student_no(store):
    assert auth.authenticate(store, "9999999", STUDENT_PASSWORD) is None


def test_login_does_not_accept_another_students_password_as_a_master_key(store):
    """학번만으로 남의 계정에 들어갈 수 없다."""
    assert auth.authenticate(store, "2026102", ADMIN_PASSWORD) is None


def test_student_password_does_not_open_the_admin_account(store):
    assert auth.authenticate(store, "admin", STUDENT_PASSWORD) is None


# =============================================================================
# 관리자 (공고 6.3절 11번)
# =============================================================================


def test_admin_logs_in_with_the_admin_password(store):
    account = auth.authenticate(store, "admin", ADMIN_PASSWORD)
    assert account is not None
    assert account.is_admin


def test_admin_student_no_is_case_insensitive(store):
    assert auth.authenticate(store, "ADMIN", ADMIN_PASSWORD) is not None


def test_students_are_not_admins(store):
    account = auth.authenticate(store, "2026101", STUDENT_PASSWORD)
    assert not account.is_admin


def test_admin_survives_a_roster_reupload(store):
    """명단을 다시 올려도 관리자 계정은 남는다 (공고 2.1절)."""
    students = parse_roster((FIXTURES / "중간.csv").read_bytes())
    store.replace_roster(students, 4, auth.hash_password(STUDENT_PASSWORD))

    assert auth.authenticate(store, "admin", ADMIN_PASSWORD) is not None
    # 새 명단의 학생으로 로그인된다
    assert auth.authenticate(store, "2026201", STUDENT_PASSWORD) is not None
    # 예전 명단의 학생은 사라졌다
    assert auth.authenticate(store, "2026101", STUDENT_PASSWORD) is None


def test_admin_password_is_updated_on_restart(store):
    """앱이 시작할 때 ADMIN_PASSWORD 로 비밀번호를 갱신한다 (공고 2.1절)."""
    store.ensure_admin(auth.hash_password("새-비밀번호"))

    assert auth.authenticate(store, "admin", "새-비밀번호") is not None
    assert auth.authenticate(store, "admin", ADMIN_PASSWORD) is None


def test_admin_is_not_listed_as_a_student(store):
    """관리자는 팀 배정 대상이 아니다."""
    assert all(s.student_no != "admin" for s in store.all_students())
