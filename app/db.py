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

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2 import pool as pg_pool

from . import config

MIN_CONNECTIONS = 1
MAX_CONNECTIONS = 8


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


def get_pool() -> pg_pool.ThreadedConnectionPool:
    """연결 풀. 앱이 사는 동안 한 번만 만든다."""
    try:
        import streamlit as st
    except ImportError:
        return _cached_pool()

    return st.cache_resource(_build_pool, show_spinner=False)()


_pool_singleton: pg_pool.ThreadedConnectionPool | None = None


def _cached_pool() -> pg_pool.ThreadedConnectionPool:
    """Streamlit 밖에서(스크립트, 테스트) 쓰는 경로."""
    global _pool_singleton
    if _pool_singleton is None:
        _pool_singleton = _build_pool()
    return _pool_singleton


@contextmanager
def connection() -> Iterator[psycopg2.extensions.connection]:
    """풀에서 연결을 빌려 쓰고 돌려준다.

    블록이 끝나면 커밋하고, 예외가 나면 되돌린다. 동작 하나가 트랜잭션 하나가
    되므로, 승인 직전 재검사와 팀원 추가가 한 덩어리로 처리된다.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def check_connection() -> bool:
    """DB 에 닿는지 확인한다. 외부 예약 서비스가 매일 부르는 경로이기도 하다
    (공고 3장 "DB 가 일시정지되지 않게" 의 어려운 해결)."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select 1")
            return cur.fetchone()[0] == 1
