import os
from typing import Optional
from openai import OpenAI
from .base import TranscriptionService, TranscriptionError

from src.utils.logging import get_logger
from src.utils.retry import retry_once
import requests


class APIWhisperService(TranscriptionService):
    """OpenAI Whisper API transcription service."""

    def __init__(self, api_key: Optional[str] = None, language: str = "auto"):
        """
        Initialize API Whisper service.

        Args:
            api_key: OpenAI API key. If None, will try to get from environment variable.
            language: Language for transcription ("auto" for auto-detection or ISO 639-1 codes)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.language = None if language == "auto" else language
        self.client: Optional[OpenAI] = None
        self.logger = get_logger(__name__)

        if self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception as e:
                raise TranscriptionError(f"Failed to initialize OpenAI client: {e}")

    def transcribe(self, audio_file_path: str) -> str:
        """
        Transcribe audio file using OpenAI Whisper API.

        Args:
            audio_file_path: Path to audio file

        Returns:
            Transcribed text
        """
        if not self.client:
            raise TranscriptionError(
                "OpenAI client not initialized. Please provide a valid API key."
            )

    def transcribe(self, audio_file_path: str) -> str:
        """
        Transcribe audio file using OpenAI Whisper API.

        Args:
            audio_file_path: Path to audio file

        Returns:
            Transcribed text
        """
        if not self.client:
            raise TranscriptionError(
                "OpenAI client not initialized. Please provide a valid API key."
            )

        if not os.path.exists(audio_file_path):
            raise TranscriptionError(f"Audio file not found: {audio_file_path}")

        try:
            self.logger.debug(f"Transcribing with OpenAI API: {audio_file_path}")

            with open(audio_file_path, "rb") as audio_file:
                # Prepare API parameters
                api_params = {
                    "model": "whisper-1",
                    "file": audio_file,
                    "response_format": "text",
                }

                # Add language if specified
                if self.language:
                    api_params["language"] = self.language

                transcript = self.client.audio.transcriptions.create(**api_params)

            transcribed_text = transcript.strip() if isinstance(transcript, str) else ""

            if not transcribed_text:
                return "No speech detected"

            self.logger.info(
                f"API transcription completed: {len(transcribed_text)} characters"
            )
            return transcribed_text

        except requests.Timeout as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "api_transcription"})
            self.logger.warning(f"OpenAI API timeout: {e}")
            raise TranscriptionError(f"API timeout: {e}")

        except requests.ConnectionError as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "api_transcription"})
            self.logger.warning(f"OpenAI API connection failed: {e}")
            raise TranscriptionError(f"Connection failed: {e}")

        except Exception as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "api_transcription"})
            self.logger.error(f"API transcription failed: {e}")
            raise

    def is_available(self) -> bool:
        """Check if API service is available."""
        if not self.api_key:
            return False

        try:
            # Try to create a client to validate the API key format
            if not self.client:
                self.client = OpenAI(api_key=self.api_key)
            return True
        except Exception:
            return False

    def set_api_key(self, api_key: str) -> None:
        """Set or update the API key."""
        self.api_key = api_key
        try:
            self.client = OpenAI(api_key=api_key)
        except Exception as e:
            raise TranscriptionError(f"Invalid API key: {e}")

    def get_api_info(self) -> dict:
        """Get information about the API configuration."""
        return {
            "has_api_key": bool(self.api_key),
            "client_initialized": bool(self.client),
        }
