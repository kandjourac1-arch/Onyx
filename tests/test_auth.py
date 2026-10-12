import time

from services.auth import create_session, hash_password, session_is_valid, verify_password


def test_passwords_use_bcrypt_and_verify():
    encoded = hash_password("correct horse battery")
    assert encoded.startswith("$2")
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("wrong", encoded)


def test_sessions_expire_and_are_random():
    user = {"sessions": []}
    token = create_session(user)
    assert session_is_valid(user, token)
    assert not session_is_valid(user, "not-a-session-token")
    user["sessions"][0]["created_at"] = time.time() - 86_401
    assert not session_is_valid(user, token)
