"""Auth middleware for managed voicebox (multi-tenant mode).

When VOICEBOX_AUTH_ENABLED=true, all endpoints except /v1/status require
a valid token. Tokens are validated against the gateway's internal API
and cached for a configurable TTL.
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUTH_ENABLED = os.environ.get("VOICEBOX_AUTH_ENABLED", "").lower() in ("true", "1", "yes")
GATEWAY_URL = os.environ.get("VOICEBOX_GATEWAY_URL", "http://localhost:8400")
GATEWAY_INTERNAL_TOKEN = os.environ.get("VOICEBOX_GATEWAY_INTERNAL_TOKEN", "")
TOKEN_CACHE_TTL = int(os.environ.get("VOICEBOX_TOKEN_CACHE_TTL", "300"))
MAX_STREAMS_PER_USER = int(os.environ.get("VOICEBOX_MAX_STREAMS_PER_USER", "4"))

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class AuthResult:
    ok: bool
    user_id: Optional[str] = None
    frame_id: Optional[str] = None
    host_id: Optional[str] = None
    token_type: Optional[str] = None  # "frame" | "host"
    error: Optional[str] = None


@dataclass
class _CacheEntry:
    result: AuthResult
    expires_at: float


# ---------------------------------------------------------------------------
# Token cache
# ---------------------------------------------------------------------------

_cache: dict[str, _CacheEntry] = {}
_cache_lock = asyncio.Lock()


def _cache_key(token: str, frame_id: Optional[str]) -> str:
    return f"{token[:16]}:{frame_id or ''}"


async def _get_cached(token: str, frame_id: Optional[str]) -> Optional[AuthResult]:
    key = _cache_key(token, frame_id)
    async with _cache_lock:
        entry = _cache.get(key)
        if entry and entry.expires_at > time.monotonic():
            return entry.result
        if entry:
            del _cache[key]
    return None


async def _set_cached(token: str, frame_id: Optional[str], result: AuthResult) -> None:
    key = _cache_key(token, frame_id)
    async with _cache_lock:
        _cache[key] = _CacheEntry(result=result, expires_at=time.monotonic() + TOKEN_CACHE_TTL)
        # Evict stale entries if cache grows large
        if len(_cache) > 1000:
            now = time.monotonic()
            stale = [k for k, v in _cache.items() if v.expires_at <= now]
            for k in stale:
                del _cache[k]


# ---------------------------------------------------------------------------
# Per-user stream tracking
# ---------------------------------------------------------------------------

_user_streams: dict[str, int] = {}
_streams_lock = asyncio.Lock()


async def acquire_stream(user_id: str) -> bool:
    """Try to acquire a stream slot for a user. Returns False if at limit."""
    async with _streams_lock:
        current = _user_streams.get(user_id, 0)
        if current >= MAX_STREAMS_PER_USER:
            return False
        _user_streams[user_id] = current + 1
        return True


async def release_stream(user_id: str) -> None:
    """Release a stream slot for a user."""
    async with _streams_lock:
        current = _user_streams.get(user_id, 0)
        if current <= 1:
            _user_streams.pop(user_id, None)
        else:
            _user_streams[user_id] = current - 1


# ---------------------------------------------------------------------------
# Gateway validation
# ---------------------------------------------------------------------------

async def validate_token(token: str, frame_id: Optional[str] = None) -> AuthResult:
    """Validate a token against the gateway's internal API (with caching)."""
    if not AUTH_ENABLED:
        return AuthResult(ok=True, user_id="local", token_type="local")

    if not token:
        return AuthResult(ok=False, error="Missing authorization token")

    # Check cache first
    cached = await _get_cached(token, frame_id)
    if cached is not None:
        return cached

    # Call gateway
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            body: dict = {"token": token}
            if frame_id:
                body["frameId"] = frame_id

            resp = await client.post(
                f"{GATEWAY_URL}/api/internal/validate-token",
                json=body,
                headers={"X-Internal-Token": GATEWAY_INTERNAL_TOKEN},
            )

            if resp.status_code != 200:
                result = AuthResult(ok=False, error=f"Gateway returned {resp.status_code}")
                return result

            data = resp.json()
            if data.get("ok"):
                result = AuthResult(
                    ok=True,
                    user_id=data.get("ownerId"),
                    frame_id=data.get("frameId"),
                    host_id=data.get("hostId"),
                    token_type=data.get("type"),
                )
                await _set_cached(token, frame_id, result)
                return result
            else:
                result = AuthResult(ok=False, error=data.get("code", "TOKEN_INVALID"))
                return result

    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        return AuthResult(ok=False, error="Token validation unavailable")


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_auth_dependency():
    """Create a FastAPI dependency that extracts and validates auth."""
    from fastapi import Request, HTTPException

    async def auth_dependency(request: Request) -> AuthResult:
        if not AUTH_ENABLED:
            return AuthResult(ok=True, user_id="local", token_type="local")

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing Authorization header")

        token = auth_header[7:]  # strip "Bearer "
        frame_id = request.headers.get("x-frame-id")

        result = await validate_token(token, frame_id)
        if not result.ok:
            raise HTTPException(status_code=401, detail=result.error or "Invalid token")

        return result

    return auth_dependency


# ---------------------------------------------------------------------------
# WebSocket auth (token in config message)
# ---------------------------------------------------------------------------

async def validate_ws_config_token(config: dict) -> AuthResult:
    """Validate the token from a WebSocket config message.

    Expected config format: {"language": "en", "token": "optfr_xxx", "frame_id": "uuid"}
    """
    if not AUTH_ENABLED:
        return AuthResult(ok=True, user_id="local", token_type="local")

    token = config.get("token")
    if not token:
        return AuthResult(ok=False, error="Missing token in config message")

    frame_id = config.get("frame_id")
    return await validate_token(token, frame_id)
