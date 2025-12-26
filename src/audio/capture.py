import sounddevice as sd
import numpy as np
import tempfile
import os
import wave
from typing import Optional
import threading
import queue

from utils.logging import get_logger


class AudioRecorder:
    """Cross-platform audio recorder using sounddevice."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording_flag = False
        self.audio_queue = queue.Queue()
        self.recording_thread: Optional[threading.Thread] = None
        self.temp_file_path: Optional[str] = None
        self.logger = get_logger(__name__)

    def start_recording(self) -> None:
        """Start recording audio from the default microphone."""
        if self.is_recording_flag:
            raise RuntimeError("Recording already in progress")

        self.is_recording_flag = True
        self.audio_queue = queue.Queue()

        # Create temporary file for this recording
        fd, self.temp_file_path = tempfile.mkstemp(suffix=".wav", prefix="voicebox_")
        os.close(fd)  # Close the file descriptor, we'll write to it later

        # Start recording in a separate thread
        self.recording_thread = threading.Thread(target=self._record_audio)
        self.recording_thread.start()

    def stop_recording(self) -> str:
        """Stop recording and return the path to the recorded audio file."""
        if not self.is_recording_flag:
            raise RuntimeError("No recording in progress")

        self.is_recording_flag = False

        # Wait for recording thread to finish
        if self.recording_thread:
            self.recording_thread.join()

        # Write all recorded audio to WAV file
        self._save_audio_to_file()

        if not self.temp_file_path:
            raise RuntimeError("No audio file was created")

        return self.temp_file_path

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.is_recording_flag

    def _record_audio(self) -> None:
        """Internal method to record audio in a separate thread."""

        def audio_callback(indata, frames, time, status):
            if status:
                self.logger.debug(f"Audio callback status: {status}")
            if self.is_recording_flag:
                self.audio_queue.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                callback=audio_callback,
                blocksize=1024,
            ):
                while self.is_recording_flag:
                    sd.sleep(100)  # Sleep for 100ms

        except Exception as e:
            from utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "audio_recording"})
            self.logger.error(f"Audio recording failed: {e}")
            self.is_recording_flag = False

    def _save_audio_to_file(self) -> None:
        """Save recorded audio chunks to WAV file."""
        if not self.temp_file_path:
            return

        # Collect all audio data
        audio_data = []
        while not self.audio_queue.empty():
            audio_data.append(self.audio_queue.get())

        if not audio_data:
            if self.temp_file_path and os.path.exists(self.temp_file_path):
                os.remove(self.temp_file_path)
            self.temp_file_path = None
            raise RuntimeError("No audio captured")

        # Concatenate all chunks
        full_audio = np.concatenate(audio_data, axis=0)

        # Convert to 16-bit PCM
        audio_int16 = (full_audio * 32767).astype(np.int16)

        # Write to WAV file
        with wave.open(self.temp_file_path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())

    def cleanup_temp_file(self, file_path: str) -> None:
        """Clean up temporary audio file."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError as e:
            print(f"Error cleaning up temp file {file_path}: {e}")

    @staticmethod
    def list_audio_devices():
        """List available audio input devices for debugging."""
        devices = sd.query_devices()
        input_devices = [d for d in devices if d["max_input_channels"] > 0]
        return input_devices
