"""커넥션 풀이 비었을 때의 동작 (공고 4.2절, 6.2절 2항).

채점 프로그램은 가상 학생마다 브라우저를 따로 연다. 명단이 16명이면 창 16개가
5초마다 화면을 다시 그리므로 요청이 몰린다. psycopg2 의 getconn 은 풀이 다 차면
기다리지 않고 바로 PoolError 를 던지므로, 그대로 두면 채점 도중 화면이 오류로
죽는다.
"""

from __future__ import annotations

import pytest
from psycopg2 import pool as pg_pool

from app import db


class FakePool:
    """정해진 횟수만큼 PoolError 를 던진 뒤 연결을 내주는 가짜 풀."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def getconn(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise pg_pool.PoolError("connection pool exhausted")
        return "연결"


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    monkeypatch.setattr(db, "POOL_RETRY_DELAY", 0.001)


def test_borrows_straight_away_when_the_pool_has_room():
    pool = FakePool(fail_times=0)
    assert db._borrow(pool) == "연결"
    assert pool.calls == 1


def test_waits_and_retries_while_the_pool_is_full():
    """다른 창이 연결을 돌려줄 때까지 기다렸다 집는다."""
    pool = FakePool(fail_times=3)
    assert db._borrow(pool) == "연결"
    assert pool.calls == 4


def test_gives_up_after_the_deadline(monkeypatch):
    """영원히 기다리지는 않는다. 한도를 넘으면 원래 예외를 그대로 올린다."""
    monkeypatch.setattr(db, "POOL_WAIT_SECONDS", 0.02)
    pool = FakePool(fail_times=10_000)

    with pytest.raises(pg_pool.PoolError):
        db._borrow(pool)

    assert pool.calls > 1, "한 번도 다시 시도하지 않았다"


def test_pool_is_large_enough_for_a_full_scenario():
    """채점 시나리오의 학생 수는 8~16명이다 (공고 6.2절 8항)."""
    assert db.MAX_CONNECTIONS >= 16
