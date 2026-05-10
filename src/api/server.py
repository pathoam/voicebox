"""VoiceBox ASR API server (FastAPI + uvicorn).

Supports both local (single-user, no auth) and managed (multi-tenant, auth
required) modes. Set VOICEBOX_AUTH_ENABLED=true to enable token validation.
"""

import asyncio
import tempfile
import time
import threading
from typing import Dict, Optional

import numpy as np

from src.utils.logging import get_logger
from src.api.auth import (
    AUTH_ENABLED,
    get_auth_dependency,
    validate_ws_config_token,
    acquire_stream,
    release_stream,
    AuthResult,
)

logger = get_logger(__name__)

# Lazy FastAPI import — only needed when the server is actually started
_app = None
_service = None  # QwenASRService instance shared with desktop app
_max_streams: int = 8
_transcribe_semaphore: Optional[asyncio.Semaphore] = None

# Session tracking for WebSocket streams
_sessions: Dict[str, dict] = {}  # session_id -> {"last_active": float}
_sessions_lock = threading.Lock()
_SESSION_TIMEOUT = 60.0  # seconds of inactivity before auto-cleanup


def _get_app():
    """Lazily create the FastAPI app."""
    global _app
    if _app is not None:
        return _app

    from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Query, Depends
    from fastapi.responses import JSONResponse

    _app = FastAPI(title="VoiceBox ASR API", version="1.0.0")
    auth_dep = get_auth_dependency()

    @_app.get("/v1/status")
    async def status():
        active = 0
        if _service is not None:
            active = _service.active_session_count()
        model_name = "unknown"
        streaming = False
        if _service is not None:
            model_name = f"qwen-{_service.model_size}"
            streaming = _service.supports_streaming()
        sample_rate = 16000
        return {
            "status": "ready" if _service is not None else "not_configured",
            "model": model_name,
            "streaming_supported": streaming,
            "active_streams": active,
            "max_streams": _max_streams,
            "sample_rate": sample_rate,
        }

    @_app.post("/v1/transcribe")
    async def transcribe(
        file: UploadFile = File(...),
        language: Optional[str] = Query(None),
        _auth: AuthResult = Depends(auth_dep),
    ):
        if _service is None:
            return JSONResponse(
                status_code=503,
                content={"error": "ASR service not configured"},
            )

        global _transcribe_semaphore
        if _transcribe_semaphore is None:
            _transcribe_semaphore = asyncio.Semaphore(_max_streams)

        async with _transcribe_semaphore:
            # Save upload to temp file
            suffix = ".wav"
            if file.filename and "." in file.filename:
                suffix = "." + file.filename.rsplit(".", 1)[-1]
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name

            try:
                start = time.monotonic()
                # Run transcription in thread pool to avoid blocking the event loop
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(
                    None, _service.transcribe, tmp_path
                )
                elapsed = time.monotonic() - start
                return {
                    "text": text,
                    "processing_time_seconds": round(elapsed, 3),
                }
            finally:
                import os
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @_app.websocket("/v1/stream")
    async def stream(ws: WebSocket):
        if _service is None or not _service.supports_streaming():
            await ws.close(code=1013, reason="Streaming not available")
            return

        await ws.accept()

        # Wait for config message
        try:
            config = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
        except (asyncio.TimeoutError, Exception):
            await ws.close(code=1002, reason="Expected JSON config message")
            return

        # Authenticate from config message (Stage 5: WebSocket auth)
        auth = await validate_ws_config_token(config)
        if not auth.ok:
            await ws.send_json({"error": auth.error or "Authentication failed"})
            await ws.close(code=1008, reason="Unauthorized")
            return

        # Per-user stream limit
        user_id = auth.user_id or "anonymous"
        if AUTH_ENABLED and not await acquire_stream(user_id):
            await ws.send_json({"error": "Per-user stream limit reached"})
            await ws.close(code=1013, reason="Too many streams for this user")
            return

        language = config.get("language", None)
        if language == "auto":
            language = None

        # Check global stream limit
        active = _service.active_session_count()
        if active >= _max_streams:
            if AUTH_ENABLED:
                await release_stream(user_id)
            await ws.send_json({"error": "Max concurrent streams reached"})
            await ws.close(code=1013, reason="Too many streams")
            return

        # Create session
        session_id = _service.start_streaming_session(language=language)
        with _sessions_lock:
            _sessions[session_id] = {"last_active": time.monotonic()}

        await ws.send_json({"status": "streaming", "session_id": session_id})
        logger.info(f"WebSocket stream started: session={session_id}")

        try:
            while True:
                msg = await asyncio.wait_for(
                    ws.receive(), timeout=_SESSION_TIMEOUT
                )

                with _sessions_lock:
                    if session_id in _sessions:
                        _sessions[session_id]["last_active"] = time.monotonic()

                if msg["type"] == "websocket.receive":
                    # Binary frame = audio data
                    if "bytes" in msg and msg["bytes"]:
                        raw = msg["bytes"]
                        # Convert raw int16 PCM bytes to float32 numpy array
                        pcm_int16 = np.frombuffer(raw, dtype=np.int16)
                        audio_float = pcm_int16.astype(np.float32) / 32767.0
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            _service.feed_chunk_session,
                            session_id,
                            audio_float,
                        )
                        # Send partial result
                        partial = _service.get_partial_result(session_id)
                        if partial:
                            await ws.send_json({"partial": partial})

                    # Text frame = JSON control message
                    elif "text" in msg and msg["text"]:
                        import json
                        try:
                            ctrl = json.loads(msg["text"])
                        except json.JSONDecodeError:
                            continue
                        if ctrl.get("action") == "finish":
                            loop = asyncio.get_event_loop()
                            text = await loop.run_in_executor(
                                None,
                                _service.finish_streaming_session,
                                session_id,
                            )
                            await ws.send_json({"text": text, "final": True})
                            break

                elif msg["type"] == "websocket.disconnect":
                    break

        except asyncio.TimeoutError:
            logger.warning(f"Session {session_id} timed out")
            try:
                await ws.send_json({"error": "Session timed out", "final": True})
            except Exception:
                pass
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: session={session_id}")
        except Exception as e:
            logger.error(f"WebSocket error for session {session_id}: {e}")
        finally:
            # Clean up session
            _service.cleanup_session(session_id)
            with _sessions_lock:
                _sessions.pop(session_id, None)
            if AUTH_ENABLED:
                await release_stream(user_id)
            logger.info(f"Session cleaned up: {session_id}")

    return _app


def configure(service, max_streams: int = 8) -> None:
    """Inject the shared QwenASRService and settings."""
    global _service, _max_streams
    _service = service
    _max_streams = max_streams


def start_server(host: str = "127.0.0.1", port: int = 9876, daemon: bool = True) -> threading.Thread:
    """Start the uvicorn server in a background thread.

    Args:
        host: Bind address (default localhost only)
        port: Bind port
        daemon: Run as daemon thread (dies with main process)

    Returns:
        The server thread
    """
    import uvicorn

    app = _get_app()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="voicebox-api")
    thread.daemon = daemon
    thread.start()

    logger.info(f"API server starting on http://{host}:{port}")
    return thread


def run_server(host: str = "127.0.0.1", port: int = 9876) -> None:
    """Run the uvicorn server in the foreground (blocking)."""
    import uvicorn

    app = _get_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
