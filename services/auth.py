"""Authentification réutilisable et indépendante des routes Flask."""

from __future__ import annotations

import secrets
import time
from typing import Any, MutableMapping

import bcrypt


SESSION_TTL_SECONDS = 86_400


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("password must contain at least 8 characters")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False


def create_session(user: MutableMapping[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    sessions = user.setdefault("sessions", [])
    sessions.append({"id": token, "created_at": time.time()})
    user["sessions"] = sessions[-30:]
    return token


def session_is_valid(user: MutableMapping[str, Any], token: str | None) -> bool:
    if not token:
        return False
    now = time.time()
    active = []
    found = False
    for session in user.get("sessions", []):
        item = session if isinstance(session, dict) else {"id": session, "created_at": now}
        if now - float(item.get("created_at", 0)) <= SESSION_TTL_SECONDS:
            active.append(item)
            found = found or secrets.compare_digest(str(item.get("id", "")), token)
    user["sessions"] = active
    return found
