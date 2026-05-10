"""Tests for voicebox auth middleware."""

import asyncio
import os
import time
from unittest.mock import AsyncMock, patch

import pytest


# Set up env before importing auth module
os.environ["VOICEBOX_AUTH_ENABLED"] = "true"
os.environ["VOICEBOX_GATEWAY_URL"] = "http://gateway:8400"
os.environ["VOICEBOX_GATEWAY_INTERNAL_TOKEN"] = "test-internal-token"
os.environ["VOICEBOX_TOKEN_CACHE_TTL"] = "5"
os.environ["VOICEBOX_MAX_STREAMS_PER_USER"] = "2"

# Force re-read of env (module reads at import time)
import importlib
import src.api.auth as auth_module
auth_module.AUTH_ENABLED = True
auth_module.GATEWAY_URL = "http://gateway:8400"
auth_module.GATEWAY_INTERNAL_TOKEN = "test-internal-token"
auth_module.TOKEN_CACHE_TTL = 5
auth_module.MAX_STREAMS_PER_USER = 2

from src.api.auth import (
    validate_token,
    validate_ws_config_token,
    acquire_stream,
    release_stream,
    AuthResult,
    _cache,
    _user_streams,
)


@pytest.fixture(autouse=True)
def clear_state():
    """Clear caches and stream counters between tests."""
    _cache.clear()
    _user_streams.clear()
    yield
    _cache.clear()
    _user_streams.clear()


class TestValidateToken:
    @pytest.mark.asyncio
    async def test_empty_token_rejected(self):
        result = await validate_token("")
        assert not result.ok
        assert "Missing" in (result.error or "")

    @pytest.mark.asyncio
    async def test_successful_frame_token(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "type": "frame",
            "frameId": "frame-123",
            "ownerId": "user-456",
            "slug": "my-frame",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await validate_token("optfr_abc123", "frame-123")

        assert result.ok
        assert result.user_id == "user-456"
        assert result.frame_id == "frame-123"
        assert result.token_type == "frame"

    @pytest.mark.asyncio
    async def test_successful_host_token(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "type": "host",
            "hostId": "host-789",
            "ownerId": "user-456",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await validate_token("opth_xyz789")

        assert result.ok
        assert result.user_id == "user-456"
        assert result.host_id == "host-789"
        assert result.token_type == "host"

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": False, "code": "TOKEN_INVALID"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await validate_token("bad-token")

        assert not result.ok
        assert result.error == "TOKEN_INVALID"

    @pytest.mark.asyncio
    async def test_caching(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True, "type": "frame", "frameId": "f1", "ownerId": "u1",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.auth.httpx.AsyncClient", return_value=mock_client):
            r1 = await validate_token("optfr_cached", "f1")
            r2 = await validate_token("optfr_cached", "f1")

        assert r1.ok and r2.ok
        # Should only have called the gateway once (second hit cache)
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_gateway_error(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await validate_token("optfr_test")

        assert not result.ok
        assert "500" in (result.error or "")

    @pytest.mark.asyncio
    async def test_network_failure(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await validate_token("optfr_test")

        assert not result.ok
        assert "unavailable" in (result.error or "")


class TestWebSocketAuth:
    @pytest.mark.asyncio
    async def test_missing_token_rejected(self):
        result = await validate_ws_config_token({"language": "en"})
        assert not result.ok
        assert "Missing token" in (result.error or "")

    @pytest.mark.asyncio
    async def test_valid_config_token(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True, "type": "frame", "frameId": "f1", "ownerId": "u1",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.auth.httpx.AsyncClient", return_value=mock_client):
            result = await validate_ws_config_token({
                "language": "en",
                "token": "optfr_abc",
                "frame_id": "f1",
            })

        assert result.ok
        assert result.user_id == "u1"


class TestStreamLimiting:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        assert await acquire_stream("user-1")
        assert await acquire_stream("user-1")

    @pytest.mark.asyncio
    async def test_acquire_at_limit(self):
        assert await acquire_stream("user-2")
        assert await acquire_stream("user-2")
        assert not await acquire_stream("user-2")  # limit is 2

    @pytest.mark.asyncio
    async def test_release_frees_slot(self):
        assert await acquire_stream("user-3")
        assert await acquire_stream("user-3")
        assert not await acquire_stream("user-3")

        await release_stream("user-3")
        assert await acquire_stream("user-3")

    @pytest.mark.asyncio
    async def test_independent_users(self):
        assert await acquire_stream("user-a")
        assert await acquire_stream("user-a")
        assert not await acquire_stream("user-a")

        # Different user is not affected
        assert await acquire_stream("user-b")
        assert await acquire_stream("user-b")
