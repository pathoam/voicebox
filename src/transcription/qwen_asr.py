import threading
from typing import Optional

import numpy as np

from src.transcription.base import StreamingTranscriptionService, TranscriptionError
from src.utils.logging import get_logger


logger = get_logger(__name__)

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

    def __init__(self, model_size: str = "0.6B", language: str = "auto"):
        self.model_size = model_size
        self.language = _resolve_language(language)
        self.model = None
        self._is_vllm = False
        self._lock = threading.Lock()
        # Streaming state
        self._streaming_state = None
        self._buffer_lock = threading.Lock()

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
            self.model = Qwen3ASRModel.LLM(model_name)
            self._is_vllm = True
            logger.info(f"Loaded Qwen ASR with vLLM backend: {model_name}")
        except Exception as e:
            logger.warning(f"vLLM backend failed ({e}), falling back to from_pretrained")
            self.model = Qwen3ASRModel.from_pretrained(model_name)
            self._is_vllm = False
            logger.info(f"Loaded Qwen ASR with transformers backend: {model_name} (streaming disabled)")

    def transcribe_file(self, path: str) -> str:
        self.load_model()
        results = self.model.transcribe(path, language=self.language)
        # results is a list of ASRTranscription objects
        if results:
            texts = []
            for r in results:
                text = getattr(r, 'text', None) or str(r)
                if text.strip():
                    texts.append(text.strip())
            return " ".join(texts)
        return ""

    def supports_streaming(self) -> bool:
        return self._is_vllm

    def start_streaming(self) -> None:
        self.load_model()
        self._streaming_state = self.model.init_streaming_state(
            language=self.language,
        )

    def feed_chunk(self, chunk: np.ndarray) -> None:
        if self._streaming_state is None:
            return
        # Convert float32 to int16 PCM (16kHz mono) as the API expects
        pcm = (chunk.flatten() * 32767).astype(np.int16)
        with self._buffer_lock:
            self._streaming_state = self.model.streaming_transcribe(
                pcm, self._streaming_state
            )

    def finish_streaming(self) -> str:
        if self._streaming_state is None:
            return ""
        with self._buffer_lock:
            self._streaming_state = self.model.finish_streaming_transcribe(
                self._streaming_state
            )
        # Extract text from the streaming state
        text = getattr(self._streaming_state, 'text', None)
        if text:
            result = text.strip()
        else:
            # Try getting fixed_text or segments
            fixed = getattr(self._streaming_state, 'fixed_text', '')
            unfixed = getattr(self._streaming_state, 'unfixed_text', '')
            result = (fixed + unfixed).strip()
        self._streaming_state = None
        return result


class QwenASRService(StreamingTranscriptionService):
    """Qwen ASR transcription service (GPU backend)."""

    def __init__(
        self,
        model_size: str = "0.6B",
        backend: str = "auto",
        language: str = "auto",
    ):
        self.model_size = model_size
        self.backend_preference = backend
        self.language = language
        self._backend: Optional[QwenGPUBackend] = None
        self._loaded = False

    def _load_model(self) -> None:
        """Lazy-initialize the GPU backend."""
        if self._loaded:
            return

        if not QwenGPUBackend.is_available():
            raise TranscriptionError(
                "Qwen ASR not available. Install with: pip install qwen-asr"
            )
        self._backend = QwenGPUBackend(self.model_size, self.language)
        self._backend.load_model()
        self._loaded = True

    def transcribe(self, audio_file_path: str) -> str:
        self._load_model()
        return self._backend.transcribe_file(audio_file_path)

    def is_available(self) -> bool:
        return QwenGPUBackend.is_available()

    def start_streaming(self) -> None:
        self._load_model()
        self._backend.start_streaming()

    def feed_chunk(self, audio_chunk: np.ndarray) -> None:
        if self._backend:
            self._backend.feed_chunk(audio_chunk)

    def finish_streaming(self) -> str:
        if not self._backend:
            return ""
        return self._backend.finish_streaming()

    def supports_streaming(self) -> bool:
        if not self._loaded:
            try:
                self._load_model()
            except TranscriptionError:
                return False
        return self._backend.supports_streaming() if self._backend else False
