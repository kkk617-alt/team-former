"""DB 연결 (공고 4.2절).

질의를 할 때마다 연결을 새로 만들면 오래 걸린다. 화면을 한 번 그릴 때 질의를
10번 하는데 연결에만 0.5초씩 걸리면 화면이 5초 늦어진다. 그래서 연결은 한 번만
만들어 두고 다시 쓴다.

Streamlit 은 사용자마다 다른 스레드에서 스크립트를 돌리므로, 연결 하나를 그대로
공유하면 서로의 트랜잭션이 섞인다. 그래서 st.cache_resource 로 연결 풀을 한 번만
만들고, 동작 하나가 그 풀에서 연결을 하나 빌려 쓴 뒤 돌려준다. "연결을 새로
만들지 않는다" 는 요구는 지키면서 스레드 안전성도 얻는 방법이다.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2 import pool as pg_pool

from . import config

MIN_CONNECTIONS = 1

#: 채점 프로그램은 가상 학생마다 브라우저를 따로 연다 (공고 6.2절 2항). 명단이
#: 16명이면 창 16개가 5초마다 화면을 다시 그리므로 요청이 몰린다.
MAX_CONNECTIONS = 20

#: 풀이 비었을 때 기다리는 한도. psycopg2 의 getconn 은 풀이 다 차면 기다리지
#: 않고 바로 예외를 던지므로, 직접 잠깐 기다렸다 다시 집는다. 그냥 두면 동시
#: 접속이 몰릴 때 화면이 오류로 죽는다.
POOL_WAIT_SECONDS = 5.0
POOL_RETRY_DELAY = 0.1


def _build_pool() -> pg_pool.ThreadedConnectionPool:
    dsn = config.database_url()
    return pg_pool.ThreadedConnectionPool(
        MIN_CONNECTIONS,
        MAX_CONNECTIONS,
        dsn=dsn,
        # Supabase 는 TLS 를 요구한다. 주소에 이미 적혀 있으면 그 값이 쓰인다.
        sslmode="require",
        # 끊긴 연결을 오래 붙잡지 않게 한다.
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
        application_name="team-former",
    )


_pool: pg_pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> pg_pool.ThreadedConnectionPool:
    """연결 풀. 앱 과정이 사는 동안 한 번만 만든다.

    모듈 전역에 두면 Streamlit 이 스크립트를 다시 돌려도 모듈을 다시 불러오지
    않으므로 풀이 그대로 남는다. st.cache_resource 를 쓰지 않는 덕에 Streamlit
    밖(스크립트, 테스트)에서도 같은 경로가 쓰인다.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            # 잠금을 기다리는 동안 다른 스레드가 만들었을 수 있다.
            if _pool is None:
                _pool = _build_pool()
    return _pool


@contextmanager
def connection() -> Iterator[psycopg2.extensions.connection]:
    """풀에서 연결을 빌려 쓰고 돌려준다.

    블록이 끝나면 커밋하고, 예외가 나면 되돌린다. 동작 하나가 트랜잭션 하나가
    되므로, 승인 직전 재검사와 팀원 추가가 한 덩어리로 처리된다.
    """
    pool = get_pool()
    conn = _borrow(pool)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _borrow(pool: pg_pool.ThreadedConnectionPool):
    """풀에서 연결을 집는다. 다 차 있으면 잠깐 기다렸다 다시 시도한다."""
    deadline = time.monotonic() + POOL_WAIT_SECONDS
    while True:
        try:
            return pool.getconn()
        except pg_pool.PoolError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(POOL_RETRY_DELAY)


def check_connection() -> bool:
    """DB 에 닿는지 확인한다. 외부 예약 서비스가 매일 부르는 경로이기도 하다
    (공고 3장 "DB 가 일시정지되지 않게" 의 어려운 해결)."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select 1")
            return cur.fetchone()[0] == 1
