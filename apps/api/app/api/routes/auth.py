from __future__ import annotations

from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.services.auth import CurrentUser, create_session_cookie, create_signed_value, get_current_user, verify_signed_value
from app.services.github_oauth import GitHubOAuthError, GitHubOAuthService
from app.services.runtime_secrets import effective_settings
from app.services.url_safety import web_app_base_url

router = APIRouter()

OAUTH_STATE_COOKIE = "repopilot_oauth_state"
SESSION_COOKIE = "repopilot_session"


@router.get("/session")
async def get_session(current_user: CurrentUser = Depends(get_current_user)) -> dict[str, str | None]:
    return {
        "username": current_user.username,
        "role": current_user.role,
        "mode": "github-oauth" if current_user.github_user_id else "local-dev-header-auth",
        "github_user_id": current_user.github_user_id,
        "email": current_user.email,
    }


@router.get("/github/login")
async def github_login() -> JSONResponse:
    oauth = GitHubOAuthService()
    configured = oauth.is_configured()
    authorize_url = None
    response_body = {
        "status": "configured" if configured else "placeholder",
        "authorize_url": authorize_url,
        "next_step": "Save GitHub OAuth credentials in Settings -> GitHub to enable real GitHub OAuth sessions.",
    }
    if not configured:
        return JSONResponse(response_body)

    nonce = token_urlsafe(24)
    state_cookie = create_signed_value({"state": nonce})
    response_body["authorize_url"] = oauth.authorization_url(state=nonce)
    response_body["next_step"] = "Redirect the browser to authorize RepoPilot AI with GitHub."
    response = JSONResponse(response_body)
    _set_cookie(response, OAUTH_STATE_COOKIE, state_cookie, max_age=10 * 60)
    return response


@router.get("/github/callback")
async def github_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    repopilot_oauth_state: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error:
        return _redirect_to_app(f"/#connect?{urlencode({'github_error': _safe_oauth_error(error)})}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="GitHub OAuth callback is missing code or state.")

    state_payload = verify_signed_value(repopilot_oauth_state)
    if state_payload is None or state_payload.get("state") != state:
        raise HTTPException(status_code=400, detail="GitHub OAuth state did not match. Please retry the connection flow.")

    oauth = GitHubOAuthService()
    try:
        token = await oauth.exchange_code(code=code)
        profile = await oauth.fetch_profile(token=token)
        repositories = await oauth.fetch_repositories(token=token)
        await oauth.sync_user_repositories(db, profile=profile, repositories=repositories)
    except GitHubOAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    session_cookie = create_session_cookie(
        {
            "github_user_id": profile.github_user_id,
            "username": profile.username,
            "email": profile.email,
            "role": "owner",
        }
    )
    response = _redirect_to_app("/#repositories?github=connected")
    _set_cookie(response, SESSION_COOKIE, session_cookie, max_age=60 * 60 * 24 * 14)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response


def _redirect_to_app(path: str) -> RedirectResponse:
    config = effective_settings(settings)
    return RedirectResponse(f"{web_app_base_url(config.web_app_url)}{_safe_redirect_path(path)}", status_code=303)


def _safe_redirect_path(path: str) -> str:
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        return "/"
    if any(ord(char) < 32 for char in path):
        return "/"
    return path


def _safe_oauth_error(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    cleaned = "".join(char for char in value[:80] if char in allowed)
    return cleaned or "github_oauth_error"


def _set_cookie(response: JSONResponse | RedirectResponse, key: str, value: str, *, max_age: int) -> None:
    config = effective_settings(settings)
    response.set_cookie(
        key,
        value,
        max_age=max_age,
        httponly=True,
        secure=config.web_app_url.startswith("https://"),
        samesite="lax",
        path="/",
    )
