import threading
import uuid
from typing import Optional, Dict

import numpy as np

from src.transcription.base import StreamingTranscriptionService, TranscriptionError
from src.utils.logging import get_logger


logger = get_logger(__name__)

# Default session ID used by the desktop app's single-session path
_DEFAULT_SESSION = "__default__"

# Map ISO 639-1 codes to the full names qwen-asr expects
_LANG_MAP = {
    "zh": "Chinese",
    "en": "English",
    "yue": "Cantonese",
    "ar": "Arabic",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "id": "Indonesian",
    "it": "Italian",
    "ko": "Korean",
    "ru": "Russian",
    "th": "Thai",
    "vi": "Vietnamese",
    "ja": "Japanese",
    "tr": "Turkish",
    "hi": "Hindi",
    "ms": "Malay",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "fil": "Filipino",
    "fa": "Persian",
    "el": "Greek",
    "ro": "Romanian",
    "hu": "Hungarian",
    "mk": "Macedonian",
}


def _resolve_language(lang: str) -> Optional[str]:
    """Convert a language setting to the full name qwen-asr expects, or None for auto."""
    if not lang or lang == "auto":
        return None
    # Already a full name (e.g. "English")
    if lang in _LANG_MAP.values():
        return lang
    # ISO code lookup
    resolved = _LANG_MAP.get(lang.lower())
    if resolved:
        return resolved
    logger.warning(f"Unknown language code '{lang}', falling back to auto-detect")
    return None


class QwenGPUBackend:
    """GPU backend using the Python qwen-asr package (Qwen3ASRModel)."""

    def __init__(self, model_size: str = "0.6B", language: str = "auto",
                 kv_cache_mb: int = 256, context: Optional[str] = None):
        self.model_size = model_size
        self.language = _resolve_language(language)
        self.kv_cache_mb = kv_cache_mb
        self.context = context
        self.model = None
        self._is_vllm = False
        self._lock = threading.Lock()
        # Multi-session streaming state
        self._sessions: Dict[str, object] = {}
        self._session_locks: Dict[str, threading.Lock] = {}
        self._sessions_lock = threading.Lock()

    @staticmethod
    def is_available() -> bool:
        try:
            import qwen_asr  # noqa: F401
            return True
        except ImportError:
            return False

    def load_model(self) -> None:
        if self.model is not None:
            return
        from qwen_asr import Qwen3ASRModel

        model_name = f"Qwen/Qwen3-ASR-{self.model_size}"
        try:
            # vLLM requires max_model_len to fit in KV cache. We let vLLM
            # compute the real per-token cost (which accounts for all layers
            # including encoder-only attention) and just set a conservative
            # max_model_len. 13 tokens/s of audio, so kv_cache_mb → minutes:
            #   256MB ≈ 3 min, 2048MB ≈ 24 min
            kv_bytes_per_token = 2 * 28 * 8 * 128 * 2  # 114688 (approximate)
            max_tokens = int((self.kv_cache_mb * 1024 * 1024) // kv_bytes_per_token * 0.95)
            self.model = Qwen3ASRModel.LLM(
                model_name,
                skip_mm_profiling=True,
                kv_cache_memory_bytes=self.kv_cache_mb * 1024 * 1024,
                max_model_len=max_tokens,
            )
            self._is_vllm = True
            logger.info(f"Loaded Qwen ASR with vLLM backend: {model_name}")
        except Exception as e:
            logger.warning(f"vLLM backend failed ({e}), falling back to from_pretrained")
            self.model = Qwen3ASRModel.from_pretrained(model_name)
            self._is_vllm = False
            logger.info(f"Loaded Qwen ASR with transformers backend: {model_name} (streaming disabled)")

    def set_context(self, context: Optional[str]) -> None:
        """Update the vocabulary biasing context string."""
        self.context = context

    def _strip_context_prefix(self, text: str, context: Optional[str]) -> str:
        """Remove the context prompt if the model echoed it back in the output."""
        if not context or not text:
            return text
        # The model sometimes echoes the context string at the start of the output
        if text.startswith(context):
            text = text[len(context):].lstrip()
        # Also handle partial echoes — the context ends with a period, so
        # check for a sentence that looks like the prompt
        prefix = "The following terms may appear in the audio:"
        if text.startswith(prefix):
            # Find the end of the echoed context sentence
            dot_idx = text.find(".", len(prefix))
            if dot_idx != -1:
                text = text[dot_idx + 1:].lstrip()
        return text

    def transcribe_file(self, path: str, context: Optional[str] = None) -> str:
        self.load_model()
        ctx = context if context is not None else self.context
        kwargs = {"language": self.language}
        if ctx:
            kwargs["context"] = ctx
        results = self.model.transcribe(path, **kwargs)
        # results is a list of ASRTranscription objects
        if results:
            texts = []
            for r in results:
                text = getattr(r, 'text', None) or str(r)
                if text.strip():
                    texts.append(text.strip())
            output = " ".join(texts)
            return self._strip_context_prefix(output, ctx)
        return ""

    def supports_streaming(self) -> bool:
        return self._is_vllm

    def _get_session_lock(self, session_id: str) -> threading.Lock:
        with self._sessions_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]

    def start_streaming(self, session_id: str = _DEFAULT_SESSION, context: Optional[str] = None) -> str:
        self.load_model()
        ctx = context if context is not None else self.context
        kwargs = {"language": self.language}
        if ctx:
            kwargs["context"] = ctx
        state = self.model.init_streaming_state(**kwargs)
        with self._sessions_lock:
            self._sessions[session_id] = state
            self._session_locks[session_id] = threading.Lock()
        return session_id

    def feed_chunk(self, chunk: np.ndarray, session_id: str = _DEFAULT_SESSION) -> None:
        with self._sessions_lock:
            state = self._sessions.get(session_id)
        if state is None:
            return
        # Convert float32 to int16 PCM (16kHz mono) as the API expects
        pcm = (chunk.flatten() * 32767).astype(np.int16)
        lock = self._get_session_lock(session_id)
        with lock:
            new_state = self.model.streaming_transcribe(pcm, state)
        with self._sessions_lock:
            self._sessions[session_id] = new_state

    def finish_streaming(self, session_id: str = _DEFAULT_SESSION) -> str:
        with self._sessions_lock:
            state = self._sessions.get(session_id)
        if state is None:
            return ""
        lock = self._get_session_lock(session_id)
        with lock:
            state = self.model.finish_streaming_transcribe(state)
        # Extract text from the streaming state
        text = getattr(state, 'text', None)
        if text:
            result = text.strip()
        else:
            # Try getting fixed_text or segments
            fixed = getattr(state, 'fixed_text', '')
            unfixed = getattr(state, 'unfixed_text', '')
            result = (fixed + unfixed).strip()
        # Clean up session
        with self._sessions_lock:
            self._sessions.pop(session_id, None)
            self._session_locks.pop(session_id, None)
        return self._strip_context_prefix(result, self.context)

    def get_partial_result(self, session_id: str = _DEFAULT_SESSION) -> Optional[str]:
        with self._sessions_lock:
            state = self._sessions.get(session_id)
        if state is None:
            return None
        fixed = getattr(state, 'fixed_text', '')
        unfixed = getattr(state, 'unfixed_text', '')
        partial = (fixed + unfixed).strip()
        if not partial:
            return None
        return self._strip_context_prefix(partial, self.context)

    def get_max_recording_seconds(self) -> Optional[float]:
        """Return the max safe recording duration in seconds, or None if no limit."""
        if not self._is_vllm:
            return None
        kv_bytes_per_token = 2 * 28 * 8 * 128 * 2  # 114688
        max_tokens = int((self.kv_cache_mb * 1024 * 1024) // kv_bytes_per_token * 0.95)
        tokens_per_sec = 13
        return max_tokens / tokens_per_sec * 0.95

    def cleanup_session(self, session_id: str) -> None:
        with self._sessions_lock:
            self._sessions.pop(session_id, None)
            self._session_locks.pop(session_id, None)


class QwenASRService(StreamingTranscriptionService):
    """Qwen ASR transcription service (GPU backend)."""

    def __init__(
        self,
        model_size: str = "0.6B",
        backend: str = "auto",
        language: str = "auto",
        kv_cache_mb: int = 256,
        context: Optional[str] = None,
    ):
        self.model_size = model_size
        self.backend_preference = backend
        self.language = language
        self.kv_cache_mb = kv_cache_mb
        self.context = context
        self._backend: Optional[QwenGPUBackend] = None
        self._loaded = False

    def set_context(self, context: Optional[str]) -> None:
        """Update the vocabulary biasing context string."""
        self.context = context
        if self._backend:
            self._backend.set_context(context)

    def _load_model(self) -> None:
        """Lazy-initialize the GPU backend."""
        if self._loaded:
            return

        if not QwenGPUBackend.is_available():
            raise TranscriptionError(
                "Qwen ASR not available. Install with: pip install qwen-asr"
            )
        self._backend = QwenGPUBackend(self.model_size, self.language,
                                       kv_cache_mb=self.kv_cache_mb,
                                       context=self.context)
        self._backend.load_model()
        self._loaded = True

    def transcribe(self, audio_file_path: str) -> str:
        self._load_model()
        return self._backend.transcribe_file(audio_file_path)

    def is_available(self) -> bool:
        return QwenGPUBackend.is_available()

    # -- Backward-compatible single-session API (used by desktop app) --

    def start_streaming(self) -> None:
        self._load_model()
        self._backend.start_streaming(_DEFAULT_SESSION)

    def feed_chunk(self, audio_chunk: np.ndarray) -> None:
        if self._backend:
            self._backend.feed_chunk(audio_chunk, _DEFAULT_SESSION)

    def finish_streaming(self) -> str:
        if not self._backend:
            return ""
        return self._backend.finish_streaming(_DEFAULT_SESSION)

    def supports_streaming(self) -> bool:
        if not self._loaded:
            try:
                self._load_model()
            except TranscriptionError:
                return False
        return self._backend.supports_streaming() if self._backend else False

    def get_partial_result(self, session_id: str = None) -> Optional[str]:
        if not self._backend:
            return None
        sid = session_id if session_id else _DEFAULT_SESSION
        return self._backend.get_partial_result(sid)

    # -- Multi-session API (used by the HTTP/WS server) --

    def start_streaming_session(self, language: str = None) -> str:
        """Start a new streaming session, returning its unique session ID."""
        self._load_model()
        session_id = str(uuid.uuid4())[:8]
        if language:
            # For per-session language, we create the state with resolved language
            resolved = _resolve_language(language)
            state = self._backend.model.init_streaming_state(language=resolved)
            with self._backend._sessions_lock:
                self._backend._sessions[session_id] = state
                self._backend._session_locks[session_id] = threading.Lock()
        else:
            self._backend.start_streaming(session_id)
        return session_id

    def feed_chunk_session(self, session_id: str, audio_chunk: np.ndarray) -> None:
        """Feed audio to a specific streaming session."""
        if self._backend:
            self._backend.feed_chunk(audio_chunk, session_id)

    def finish_streaming_session(self, session_id: str) -> str:
        """Finalize a specific streaming session and return text."""
        if not self._backend:
            return ""
        return self._backend.finish_streaming(session_id)

    def cleanup_session(self, session_id: str) -> None:
        """Clean up a streaming session without finalizing."""
        if self._backend:
            self._backend.cleanup_session(session_id)

    def get_max_recording_seconds(self) -> Optional[float]:
        """Return the max safe recording duration in seconds, or None if no limit."""
        if not self._backend:
            return None
        return self._backend.get_max_recording_seconds()

    def active_session_count(self) -> int:
        """Return number of active streaming sessions."""
        if not self._backend:
            return 0
        with self._backend._sessions_lock:
            return len(self._backend._sessions)
