"""비밀 값 읽기 (공고 4.1절).

오픈라우터 키, DB 주소, 관리자 비밀번호는 로컬에서는 .env 에, 배포한 앱에서는
Streamlit Secrets 에 둔다. 이 모듈은 두 곳을 모두 보고 값을 돌려준다.

값 자체를 화면이나 로그에 쓰지 않는다. 있는지 확인할 때는 secret_status() 로
"있음/없음" 만 본다 (공고 4.1절, 6.3절 8번 -3점).
"""

from __future__ import annotations

import os
from pathlib import Path

from .ai import DEFAULT_MODELS

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
DATABASE_URL = "DATABASE_URL"
ADMIN_PASSWORD = "ADMIN_PASSWORD"
AI_MODEL_KEYS = ("AI_MODEL_1", "AI_MODEL_2", "AI_MODEL_3")

_loaded = False


def _load_dotenv_once() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)


def _from_streamlit_secrets(name: str) -> str | None:
    """Streamlit Secrets 에서 읽는다.

    secrets.toml 이 없으면 st.secrets 접근 자체가 예외를 던지므로 감싼다. 로컬에서
    .env 만 쓰는 경우가 그렇다.
    """
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value) if value else None


def get_secret(name: str, default: str | None = None) -> str | None:
    """Streamlit Secrets → 환경 변수(.env) 순으로 찾는다."""
    value = _from_streamlit_secrets(name)
    if value:
        return value

    _load_dotenv_once()
    value = os.environ.get(name)
    return value if value else default


def require_secret(name: str) -> str:
    """없으면 무엇이 빠졌는지 알려 주고 멈춘다. 값은 보여 주지 않는다."""
    value = get_secret(name)
    if not value:
        raise RuntimeError(
            f"{name} 이(가) 없음. 로컬에서는 .env 에, 배포한 앱에서는 "
            f"Streamlit Secrets 에 넣어야 함 (공고 4.1절, 4.4절)"
        )
    return value


def openrouter_api_key() -> str:
    return require_secret(OPENROUTER_API_KEY)


def database_url() -> str:
    return require_secret(DATABASE_URL)


def admin_password() -> str:
    return require_secret(ADMIN_PASSWORD)


def ai_models() -> tuple[str, str, str]:
    """1차·2차·3차 모델. .env 에 없으면 app/ai.py 의 기본값을 쓴다."""
    models = [
        get_secret(key, default) or default
        for key, default in zip(AI_MODEL_KEYS, DEFAULT_MODELS)
    ]
    return models[0], models[1], models[2]


def secret_status() -> dict[str, bool]:
    """비밀 값이 있는지만 돌려준다. 값은 절대 담지 않는다."""
    return {
        name: bool(get_secret(name))
        for name in (OPENROUTER_API_KEY, DATABASE_URL, ADMIN_PASSWORD)
    }
