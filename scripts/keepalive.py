#!/usr/bin/env python
"""매일 DB 에 질의를 보내 Supabase 무료 프로젝트가 일시정지되지 않게 한다.

공고 3장 "DB(Supabase)가 일시정지되지 않게" 의 어려운 해결이다. Supabase 는
무료 프로젝트에서 1주일 동안 DB 요청이 적으면 일시정지하고, 프로젝트 주인만
다시 켤 수 있다. 채점 기간에 일시정지되어 있으면 시나리오 점수가 0점이 된다
(공고 6.3절 16번).

.github/workflows/keepalive.yml 이 이 파일을 매일 부른다.

DB 주소는 환경 변수로만 받고 어디에도 출력하지 않는다. 실패했을 때도 예외의
종류만 적는다. 예외 본문에는 호스트 이름과 비밀번호가 섞여 나올 수 있기
때문이다 (공고 6.3절 8번).
"""

from __future__ import annotations

import os
import sys

# 윈도우 콘솔의 기본 인코딩은 cp949 라서 한글이 깨져 보인다. UTF-8 로 맞춘다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

CONNECT_TIMEOUT = 15


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL 이 없음", file=sys.stderr)
        return 1

    try:
        import psycopg2
    except ImportError:
        print("psycopg2 가 설치되지 않음", file=sys.stderr)
        return 1

    conn = None
    try:
        conn = psycopg2.connect(
            url,
            sslmode="require",
            connect_timeout=CONNECT_TIMEOUT,
            application_name="team-former-keepalive",
        )
        with conn.cursor() as cur:
            cur.execute("select count(*) from tf_settings")
            rows = cur.fetchone()[0]
        print(f"DB 응답 있음 (tf_settings {rows}행)")
        return 0
    except Exception as exc:
        print(f"DB 질의 실패: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
