"""설정 점검 도구가 비밀번호를 흘리지 않는지 (공고 6.3절 8번, -3점).

check_setup.py 는 DB 주소 안의 비밀번호를 읽어, 퍼센트 인코딩이 필요한 글자가
있는지 알려 준다. 그 안내에 비밀번호의 글자를 그대로 적으면 "코드가 이 값들을
출력하게 되어 있음"에 걸린다.

안내가 비밀번호에 대해 아무것도 알려 주지 않는다는 것은, 서로 다른 비밀번호에
대해 안내가 똑같다는 것으로 확인한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_setup  # noqa: E402


def test_a_password_without_special_characters_has_no_problem():
    assert check_setup.password_encoding_problem("abc123XYZ") is None


def test_a_password_with_a_special_character_has_a_problem():
    assert check_setup.password_encoding_problem("abc@123") is not None


def test_the_advice_is_the_same_whichever_character_is_at_fault():
    """안내가 어느 글자 때문인지 알려 주면, 그만큼 비밀번호가 새어 나간다."""
    at = check_setup.password_encoding_problem("abc@123")
    hash_ = check_setup.password_encoding_problem("abc#123")
    slash = check_setup.password_encoding_problem("abc/123")
    assert at == hash_ == slash


def test_the_advice_carries_no_information_about_the_password():
    """안내가 비밀번호에 따라 조금이라도 달라지면 그만큼 비밀번호가 새어 나간다.

    안내문에는 Supabase, password 같은 영어 낱말이 들어가므로 "비밀번호의 글자가
    안 나온다"로는 확인할 수 없다. 확인해야 할 성질은 안내가 비밀번호의 함수가
    아니라는 것이다.
    """
    긴_비밀번호 = check_setup.password_encoding_problem("p@ssw/rd#1 x[y]")
    짧은_비밀번호 = check_setup.password_encoding_problem("@")
    assert 긴_비밀번호 == 짧은_비밀번호
    assert "p@ssw/rd#1 x[y]" not in chr(10).join(긴_비밀번호)
