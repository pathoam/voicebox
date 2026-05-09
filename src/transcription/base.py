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


class StreamingTranscriptionService(TranscriptionService):
    """Abstract base class for transcription services that support streaming."""

    @abstractmethod
    def start_streaming(self) -> None:
        """Prepare to receive audio chunks for streaming transcription."""
        pass

    @abstractmethod
    def feed_chunk(self, audio_chunk: 'np.ndarray') -> None:
        """
        Feed a chunk of audio data for streaming transcription.

        Args:
            audio_chunk: numpy float32 audio data
        """
        pass

    @abstractmethod
    def finish_streaming(self) -> str:
        """
        Finalize streaming transcription and return complete text.

        Returns:
            Complete transcribed text from all chunks
        """
        pass

    @abstractmethod
    def supports_streaming(self) -> bool:
        """
        Check if streaming is currently available.

        Returns:
            True if streaming is supported and ready
        """
        pass

    def get_partial_result(self, session_id: str = None) -> 'Optional[str]':
        """
        Get partial transcription result from an active streaming session.

        Args:
            session_id: Optional session identifier for multi-session support

        Returns:
            Partial text if available, None otherwise
        """
        return None


class TranscriptionError(Exception):
    """Exception raised when transcription fails."""
    pass
