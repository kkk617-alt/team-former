"""Store 계약 적합성 검사.

app/repo.py 는 실제 Supabase 없이는 동작을 시험할 수 없다. 그래서 적어도 계약의
모든 연산이 같은 이름과 같은 인자로 구현되어 있는지는 DB 없이 확인한다.

이름이 틀리거나 빠진 것을 배포 뒤에 발견하면, 채점 중에 앱이 죽는다.
"""

from __future__ import annotations

import inspect

import pytest

from app.repo import PgStore
from app.store import Store

from memstore import InMemoryStore

IMPLEMENTATIONS = [PgStore, InMemoryStore]


def protocol_methods() -> list[str]:
    return sorted(
        name
        for name, value in vars(Store).items()
        if not name.startswith("_") and callable(value)
    )


def test_protocol_is_not_empty():
    assert len(protocol_methods()) > 15


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda c: c.__name__)
def test_implements_every_method_of_the_contract(implementation):
    missing = [name for name in protocol_methods() if not hasattr(implementation, name)]
    assert missing == [], f"{implementation.__name__} 에 없는 연산: {missing}"


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda c: c.__name__)
def test_parameter_names_match_the_contract(implementation):
    mismatches: list[str] = []

    for name in protocol_methods():
        expected = _parameters(getattr(Store, name))
        actual = _parameters(getattr(implementation, name))
        if expected != actual:
            mismatches.append(f"{name}: 계약 {expected} / 구현 {actual}")

    assert mismatches == [], "\n".join(mismatches)


def _parameters(func) -> list[str]:
    return [
        name
        for name in inspect.signature(func).parameters
        if name not in ("self", "args", "kwargs")
    ]
