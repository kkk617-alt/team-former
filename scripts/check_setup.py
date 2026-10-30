#!/usr/bin/env python
"""설정이 제대로 되었는지 점검한다.

    python scripts/check_setup.py

확인하는 것
  1. 비밀 값 3개가 있는지 (공고 4.1절)
  2. DATABASE_URL 이 풀러 주소인지 — 직결 주소면 Streamlit Cloud 에서 연결되지 않음
  3. DB 에 연결되고 tf_ 테이블이 있는지
  4. 오픈라우터 키가 살아 있고 고른 모델 3개를 지금 쓸 수 있는지 (공고 4.3절)

키와 DB 주소는 어디에도 출력하지 않는다. 있는지 없는지만 알려 준다
(공고 6.3절 8번, -3점).
"""

from __future__ import annotations

import sys
from pathlib import Path

# 윈도우 콘솔의 기본 인코딩은 cp949 라서 한글이 깨져 보인다. UTF-8 로 맞춘다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK = "[ 있음 ]"
NO = "[ 없음 ]"
GOOD = "[  좋음  ]"
WARN = "[  주의  ]"
BAD = "[ 잘못됨 ]"

EXPECTED_TABLES = {
    "tf_students",
    "tf_student_sub_roles",
    "tf_teams",
    "tf_members",
    "tf_applications",
    "tf_votes",
    "tf_settings",
    "tf_ai_logs",
}


def check_secrets() -> bool:
    from app import config

    print("1. 비밀 값")
    status = config.secret_status()
    for name, present in status.items():
        print(f"   {OK if present else NO} {name}")

    if not all(status.values()):
        print("\n   → .env 의 빈 따옴표를 채우세요. 값은 채팅창에 붙여넣지 마세요.")
        return False
    return True


def check_database_url_shape() -> bool:
    from app import config

    print("\n2. DATABASE_URL 모양")
    url = config.get_secret("DATABASE_URL") or ""

    if ".pooler.supabase.com" in url:
        print(f"   {GOOD} 풀러(Session pooler) 주소입니다")
        return True
    if ".supabase.co" in url:
        print(f"   {BAD} 직결 주소입니다 (db.….supabase.co)")
        print("          무료 프로젝트의 직결 주소는 IPv6 전용이라 Streamlit")
        print("          Cloud 에서 연결되지 않습니다. Supabase 대시보드의")
        print("          Connect → Session pooler 주소로 바꾸세요.")
        return False
    if "[YOUR-PASSWORD]" in url or "YOUR-PASSWORD" in url:
        print(f"   {BAD} 주소에 [YOUR-PASSWORD] 가 그대로 남아 있습니다")
        return False

    print(f"   {WARN} Supabase 주소로 보이지 않습니다. 그래도 연결은 해 봅니다")
    return True


#: URI 의 사용자 정보 칸에 그대로 쓰면 주소가 잘못 읽히는 글자들.
#: 비밀번호에 들어 있으면 퍼센트 인코딩해야 한다 (RFC 3986).
UNSAFE_IN_PASSWORD = "@/?#[] "


def check_password_encoding() -> bool:
    """비밀번호에 인코딩하지 않은 특수문자가 있는지 본다.

    Supabase 가 만들어 주는 비밀번호에는 특수문자가 섞일 수 있다. 그대로
    주소에 붙이면 libpq 가 주소를 잘못 읽어, 비밀번호가 맞는데도 연결이
    실패한다. 원인을 찾기 어려운 흔한 함정이라 미리 알려 준다.
    """
    from urllib.parse import quote

    from app import config

    print("\n2-1. 비밀번호 특수문자")
    url = config.get_secret("DATABASE_URL") or ""

    if "://" not in url or "@" not in url:
        print(f"   {WARN} 주소 모양을 알아보지 못해 건너뜁니다")
        return True

    userinfo = url.split("://", 1)[1].rsplit("@", 1)[0]
    password = userinfo.split(":", 1)[1] if ":" in userinfo else ""

    if not password:
        print(f"   {WARN} 주소에 비밀번호가 없습니다")
        return True

    bad = sorted({ch for ch in password if ch in UNSAFE_IN_PASSWORD})
    if not bad:
        print(f"   {GOOD} 그대로 써도 되는 비밀번호입니다")
        return True

    print(f"   {BAD} 비밀번호에 그대로 쓰면 안 되는 글자가 있습니다: {' '.join(bad)}")
    print("          아래처럼 바꿔 적으세요 (퍼센트 인코딩).")
    for ch in bad:
        label = "빈칸" if ch == " " else ch
        print(f"            {label}  →  {quote(ch, safe='')}")
    print("          또는 Supabase 에서 영문과 숫자로만 된 비밀번호로 재설정하세요")
    print("          (Project Settings → Database → Reset database password).")
    return False


def check_database() -> bool:
    print("\n3. DB 연결")
    try:
        from app import db
    except Exception as exc:
        print(f"   {BAD} 모듈을 불러오지 못함: {type(exc).__name__}")
        return False

    try:
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'public' and table_name like 'tf\\_%'
                    """
                )
                found = {row[0] for row in cur.fetchall()}
    except Exception as exc:
        print(f"   {BAD} 연결 실패: {type(exc).__name__}")
        print("          Supabase 프로젝트가 일시정지되지 않았는지, 주소와")
        print("          비밀번호가 맞는지 확인하세요.")
        return False

    print(f"   {GOOD} 연결됨")

    missing = EXPECTED_TABLES - found
    if missing:
        print(f"   {BAD} 없는 테이블: {', '.join(sorted(missing))}")
        print("          python scripts/apply_schema.py 를 먼저 돌리세요.")
        return False

    print(f"   {GOOD} tf_ 테이블 {len(EXPECTED_TABLES)}개가 모두 있습니다")
    return True


def check_models() -> bool:
    print("\n4. 오픈라우터 키와 모델")
    import requests

    from app import config

    chosen = list(config.ai_models())

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {config.openrouter_api_key()}"},
            timeout=30,
        )
    except Exception as exc:
        print(f"   {BAD} 오픈라우터에 닿지 못함: {type(exc).__name__}")
        return False

    if response.status_code == 401:
        print(f"   {BAD} 키가 거부됨 (HTTP 401). 키를 다시 확인하세요")
        return False
    if response.status_code != 200:
        print(f"   {BAD} HTTP {response.status_code}")
        return False

    print(f"   {GOOD} 키가 받아들여졌습니다")

    available = {item["id"] for item in response.json().get("data", [])}
    all_alive = True
    for index, model in enumerate(chosen, start=1):
        if model in available:
            print(f"   {GOOD} {index}차 {model}")
        else:
            all_alive = False
            print(f"   {BAD} {index}차 {model} — 지금 목록에 없습니다")

    if not all_alive:
        free = sorted(m for m in available if m.endswith(":free"))
        print("\n   → 지금 쓸 수 있는 무료 모델 가운데 일부:")
        for model in free[:12]:
            print(f"        {model}")
        print("   → .env 의 AI_MODEL_1/2/3 과 README 4항을 함께 고치세요.")

    if any(m.startswith("openrouter/free") for m in chosen):
        print(f"   {BAD} openrouter/free 라우터는 쓸 수 없습니다 (공고 6.3절 14번)")
        all_alive = False

    return all_alive


def main() -> int:
    print("설정 점검\n" + "=" * 46)

    if not check_secrets():
        return 1

    shape_ok = check_database_url_shape()
    encoding_ok = check_password_encoding()
    db_ok = check_database()
    models_ok = check_models()

    print("\n" + "=" * 46)
    if shape_ok and encoding_ok and db_ok and models_ok:
        print("모두 좋습니다. 앱을 띄워 볼 수 있습니다:")
        print("  python -m streamlit run streamlit_app.py")
        return 0

    print("위의 [ 잘못됨 ] 항목을 고친 뒤 다시 돌리세요.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
