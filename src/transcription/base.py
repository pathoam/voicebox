from abc import ABC, abstractmethod


class TranscriptionService(ABC):
    """Abstract base class for transcription services."""
    
    @abstractmethod
    def transcribe(self, audio_file_path: str) -> str:
        """
        Transcribe audio file to text.
        
        Args:
            audio_file_path: Path to the audio file to transcribe
            
        Returns:
            Transcribed text as string
            
        Raises:
            TranscriptionError: If transcription fails
        """
        pass
        
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the transcription service is available and ready to use.
        
        Returns:
            True if service is available, False otherwise
        """
        pass


class TranscriptionError(Exception):
    """Exception raised when transcription fails."""
    pass