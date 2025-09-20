import os
from typing import Optional
from faster_whisper import WhisperModel
from .base import TranscriptionService, TranscriptionError


class LocalWhisperService(TranscriptionService):
    """Local Whisper transcription using faster-whisper."""
    
    AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
    
    def __init__(self, model_size: str = "base", device: str = "cpu", language: str = "auto"):
        """
        Initialize local Whisper service.
        
        Args:
            model_size: Size of the Whisper model to use
            device: Device to run inference on ("cpu", "cuda", "auto")
            language: Language for transcription ("auto" for auto-detection or ISO 639-1 codes)
        """
        if model_size not in self.AVAILABLE_MODELS:
            raise ValueError(f"Model size must be one of: {self.AVAILABLE_MODELS}")
            
        self.model_size = model_size
        self.device = device
        self.language = None if language == "auto" else language
        self.model: Optional[WhisperModel] = None
        self._model_loaded = False
        
    def _load_model(self) -> None:
        """Load the Whisper model if not already loaded."""
        if self._model_loaded:
            return
            
        try:
            self.model = WhisperModel(
                self.model_size, 
                device=self.device,
                compute_type="float32"  # Use float32 for better compatibility
            )
            self._model_loaded = True
        except Exception as e:
            raise TranscriptionError(f"Failed to load Whisper model {self.model_size}: {e}")
            
    def transcribe(self, audio_file_path: str) -> str:
        """
        Transcribe audio file using local Whisper model.
        
        Args:
            audio_file_path: Path to audio file
            
        Returns:
            Transcribed text
        """
        if not os.path.exists(audio_file_path):
            raise TranscriptionError(f"Audio file not found: {audio_file_path}")
            
        self._load_model()
        
        if not self.model:
            raise TranscriptionError("Model failed to load")
            
        try:
            # Transcribe with faster-whisper
            segments, info = self.model.transcribe(
                audio_file_path,
                beam_size=5,
                language=self.language,  # Use configured language or auto-detect
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Combine all segments into a single text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())
                
            transcribed_text = " ".join(text_parts).strip()
            
            if not transcribed_text:
                return "No speech detected"
                
            return transcribed_text
            
        except Exception as e:
            raise TranscriptionError(f"Transcription failed: {e}")
            
    def is_available(self) -> bool:
        """Check if local Whisper service is available."""
        try:
            # Try to import faster_whisper
            import faster_whisper
            return True
        except ImportError:
            return False
            
    def get_model_info(self) -> dict:
        """Get information about the current model."""
        return {
            "model_size": self.model_size,
            "device": self.device,
            "loaded": self._model_loaded
        }