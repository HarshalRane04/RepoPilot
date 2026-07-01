from __future__ import annotations

import ipaddress
from urllib.parse import quote, urlencode, urlparse, urlunparse

from app.core.config import settings


class UnsafeUrlError(ValueError):
    pass


def public_https_base_url(value: str, *, allowed_hosts: set[str], label: str) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        if not _local_http_allowed(parsed):
            raise UnsafeUrlError(f"{label} must use https.")
    if not host:
        raise UnsafeUrlError(f"{label} must include a host.")
    if parsed.username or parsed.password:
        raise UnsafeUrlError(f"{label} must not include credentials.")
    if parsed.params or parsed.query or parsed.fragment:
        raise UnsafeUrlError(f"{label} must be a base URL without query, params, or fragment.")
    if not _local_http_allowed(parsed) and _is_private_or_loopback(host):
        raise UnsafeUrlError(f"{label} must not target a private or loopback host.")
    allowed = {item.lower() for item in allowed_hosts if item}
    if allowed and host not in allowed:
        raise UnsafeUrlError(f"{label} host is not in the allowed host set.")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def provider_base_url(value: str, *, default_base_url: str, provider_id: str) -> str:
    default_host = (urlparse(default_base_url).hostname or "").lower()
    return public_https_base_url(value, allowed_hosts={default_host}, label=f"{provider_id} model provider base URL")


def github_api_base_url(value: str) -> str:
    default_host = "api.github.com"
    return public_https_base_url(value, allowed_hosts={default_host}, label="GitHub API base URL")


def github_web_base_url(value: str) -> str:
    return public_https_base_url(value, allowed_hosts={"github.com"}, label="GitHub web base URL")


def web_app_base_url(value: str) -> str:
    return public_https_base_url(value, allowed_hosts=set(), label="Web app URL")


def path_segment(value: str) -> str:
    return quote(value.strip(), safe="")


def path_fragment(value: str) -> str:
    return quote(value.strip().lstrip("/"), safe="/")


def query_string(values: dict[str, str | int]) -> str:
    return urlencode(values)


def _local_http_allowed(parsed) -> bool:
    if settings.environment != "local":
        return False
    return parsed.scheme == "http" and (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}


def _is_private_or_loopback(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
