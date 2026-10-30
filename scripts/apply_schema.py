#!/usr/bin/env python
"""schema.sql 을 DATABASE_URL 의 DB 에 적용한다.

Supabase 대시보드의 SQL Editor 에 붙여 넣어도 되지만, 이 쪽이 schema.sql 과
실제 DB 가 어긋나지 않게 하기 쉽다. 여러 번 돌려도 안전하다
(create ... if not exists).

    python scripts/apply_schema.py

DB 주소는 .env 나 환경 변수에서 읽고 화면에 출력하지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA = ROOT / "schema.sql"


def main() -> int:
    from app import config

    try:
        url = config.database_url()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not SCHEMA.exists():
        print(f"{SCHEMA.name} 이 없음", file=sys.stderr)
        return 1

    import psycopg2

    sql = SCHEMA.read_text(encoding="utf-8")

    conn = None
    try:
        conn = psycopg2.connect(url, sslmode="require", connect_timeout=20)
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception as exc:
        # 예외 본문에 DB 주소가 섞여 나올 수 있으므로 종류와 짧은 설명만 적는다.
        print(f"스키마 적용 실패: {type(exc).__name__}", file=sys.stderr)
        if conn is not None:
            conn.rollback()
        return 1
    finally:
        if conn is not None:
            conn.close()

    print("schema.sql 을 적용했습니다.")
    print("만든 테이블: tf_students, tf_student_sub_roles, tf_teams, tf_members,")
    print("             tf_applications, tf_votes, tf_settings, tf_ai_logs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
