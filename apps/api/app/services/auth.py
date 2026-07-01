from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Cookie, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User
from app.services.runtime_secrets import effective_settings

_SIGNING_PERSON = b"repopilot-sess"


@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: str
    github_user_id: str | None = None
    email: str | None = None


async def get_current_user(
    x_repopilot_user: str | None = Header(default=None),
    x_repopilot_role: str | None = Header(default=None),
    repopilot_session: str | None = Cookie(default=None),
) -> CurrentUser:
    config = effective_settings(settings)
    session = verify_session_cookie(repopilot_session)
    if session is not None:
        username = session.get("username")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.")
        return CurrentUser(
            username=str(username),
            role=str(session.get("role") or "viewer"),
            github_user_id=str(session["github_user_id"]) if session.get("github_user_id") else None,
            email=str(session["email"]) if session.get("email") else None,
        )
    if config.dev_header_auth_enabled and config.environment == "local":
        return CurrentUser(
            username=x_repopilot_user or config.dev_auth_username,
            role=x_repopilot_role or config.dev_auth_role,
        )
    if config.dev_header_auth_enabled and config.environment != "local":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Development header authentication is only allowed in the local environment.",
        )
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")


async def get_or_create_user(db: AsyncSession, current_user: CurrentUser) -> User:
    if current_user.github_user_id:
        user = await db.scalar(select(User).where(User.github_user_id == current_user.github_user_id))
    else:
        user = await db.scalar(select(User).where(User.username == current_user.username))
    if user is None:
        user = User(
            github_user_id=current_user.github_user_id,
            username=current_user.username,
            email=current_user.email,
            role=current_user.role,
        )
        db.add(user)
        await db.flush()
    else:
        user.username = current_user.username
        user.email = current_user.email or user.email
        user.role = current_user.role
    return user


def create_session_cookie(payload: dict[str, Any], *, max_age_seconds: int = 60 * 60 * 24 * 14) -> str:
    issued_at = int(time.time())
    body = {
        **payload,
        "iat": issued_at,
        "exp": issued_at + max_age_seconds,
    }
    encoded = _b64encode(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_sign(encoded)}"


def verify_session_cookie(value: str | None) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    encoded, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(encoded)):
        return None
    try:
        payload = json.loads(_b64decode(encoded))
    except (ValueError, json.JSONDecodeError):
        return None
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None
    return dict(payload)


def create_signed_value(payload: dict[str, Any], *, max_age_seconds: int = 10 * 60) -> str:
    return create_session_cookie(payload, max_age_seconds=max_age_seconds)


def verify_signed_value(value: str | None) -> dict[str, Any] | None:
    return verify_session_cookie(value)


def _sign(value: str) -> str:
    return hashlib.blake2b(value.encode("utf-8"), key=_session_signing_key(), digest_size=32, person=_SIGNING_PERSON).hexdigest()


def _session_signing_key() -> bytes:
    secret = effective_settings().session_secret_key.encode("utf-8")
    if len(secret) <= 64:
        return secret
    return hashlib.blake2b(secret, digest_size=64, person=_SIGNING_PERSON).digest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
