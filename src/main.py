#!/usr/bin/env python3

import os
import sys
import time
import threading
from enum import Enum
from typing import Optional, TYPE_CHECKING

from src.audio.capture import AudioRecorder
from src.transcription.local import LocalWhisperService
from src.transcription.api import APIWhisperService
from src.transcription.base import TranscriptionService, StreamingTranscriptionService, TranscriptionError
from src.config.manager import ConfigManager
from src.text.corrections import CorrectionPipeline
from src.text.vocabulary import VocabularyManager
from src.data.collector import TrainingDataCollector
from src.commands.detector import CommandDetector
from src.commands.processor import CommandProcessor
from src.commands.responder import CommandResponder
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.system.hotkeys import HotkeyManager
    from src.system.text_insertion import TextInserter


class AppState(Enum):
    """Application state machine states."""

    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    PROCESSING_COMMAND = "processing_command"
    INSERTING = "inserting"
    ERROR = "error"


class VoiceBoxApp:
    """Main VoiceBox application coordinator."""

    def __init__(self):
        import random

        self.app_id = random.randint(1000, 9999)
        self.logger = get_logger(__name__)
        self.logger.debug(f"VoiceBoxApp instance created with ID: {self.app_id}")
        self.state = AppState.IDLE
        self.config_manager = ConfigManager()

        # Initialize components
        self.audio_recorder: Optional[AudioRecorder] = None
        self.transcription_service: Optional[TranscriptionService] = None
        self.hotkey_manager: Optional["HotkeyManager"] = None
        self.text_inserter: Optional["TextInserter"] = None
        self.correction_pipeline: Optional[CorrectionPipeline] = None
        self.vocabulary_manager: Optional[VocabularyManager] = None
        self.training_data_collector: Optional[TrainingDataCollector] = None

        # Command mode components
        self.command_detector: Optional[CommandDetector] = None
        self.command_processor: Optional[CommandProcessor] = None
        self.command_responder: Optional[CommandResponder] = None

        # Runtime state
        self.current_audio_file: Optional[str] = None
        self._running = False
        self._state_lock = threading.Lock()

        # Last insertion tracking for correction flow
        self._last_insertion: Optional[dict] = None  # {text, char_count, audio_file, data_id}

        # Recording duration safety
        self._recording_start_time: Optional[float] = None
        self._max_recording_sec: Optional[float] = None
        self._warned_recording_limit = False
        self._auto_stopping = False

        # GUI mode flag
        self._use_gui = False

        # Callbacks for GUI integration
        self.on_transcription_complete = None
        self.on_status_change = None
        self.on_error = None

    def _report_error(
        self, message: str, error_type: str = "General", suggestion: str = ""
    ) -> None:
        """
        Report error through callback and logger.

        Args:
            message: Error message
            error_type: Category of error (Audio, Transcription, etc.)
            suggestion: User-friendly suggestion
        """
        self.logger.error(f"{error_type}: {message}")

        if self.on_error:
            self.on_error(message, error_type, suggestion)

    def start(self) -> bool:
        """Initialize and start the application."""
        try:
            # Initialize components
            self._initialize_audio()
            self._initialize_vocabulary()
            self._initialize_transcription()
            self._initialize_text_inserter()
            self._initialize_corrections()
            self._initialize_training_data()
            self._initialize_commands()
            self._initialize_hotkeys()

            # Start listening for hotkeys
            self.hotkey_manager.start_listening()

            self._running = True
            self.state = AppState.IDLE

            print(
                f"✅ VoiceBox ready! Press {self.config_manager.get_hotkey()} to start recording"
            )

            return True

        except Exception as e:
            print(f"Failed to start VoiceBox: {e}")
            return False

    def stop(self) -> None:
        """Stop the application and cleanup resources."""
        self._running = False

        with self._state_lock:
            # Stop recording if active
            if self.audio_recorder and self.audio_recorder.is_recording():
                try:
                    self.audio_recorder.stop_recording()
                except Exception as e:
                    print(f"Error stopping recording: {e}")

            # Stop hotkey listener
            if self.hotkey_manager:
                self.hotkey_manager.stop_listening()

            # Cleanup temp files
            if self.current_audio_file:
                self._cleanup_audio_file(self.current_audio_file)

    def _initialize_audio(self) -> None:
        """Initialize audio recording component."""
        sample_rate = self.config_manager.get_audio_sample_rate()
        channels = self.config_manager.get_audio_channels()

        self.audio_recorder = AudioRecorder(sample_rate=sample_rate, channels=channels)

    def _initialize_transcription(self) -> None:
        """Initialize transcription service based on configuration."""
        mode = self.config_manager.get_transcription_mode()

        if mode == "local":
            model_size = self.config_manager.get_local_model_size()
            language = self.config_manager.get_transcription_language()
            self.transcription_service = LocalWhisperService(
                model_size=model_size, language=language
            )

        elif mode == "api":
            api_key = self.config_manager.get_api_key()
            if not api_key:
                raise RuntimeError("API mode selected but no API key configured")
            language = self.config_manager.get_transcription_language()
            self.transcription_service = APIWhisperService(
                api_key=api_key, language=language
            )

        elif mode == "qwen":
            from src.transcription.qwen_asr import QwenASRService
            qwen_config = self.config_manager.get_qwen_config()
            language = self.config_manager.get_transcription_language()
            context = self.vocabulary_manager.get_context_string() if self.vocabulary_manager else None
            self.transcription_service = QwenASRService(
                model_size=qwen_config["model_size"],
                backend=qwen_config["backend"],
                language=language,
                kv_cache_mb=self.config_manager.get_setting("vllm_kv_cache_mb", 256),
                context=context,
            )
            # Eagerly load model so downloads happen at startup (not in hotkey thread)
            print("Loading Qwen ASR model (may download on first run)...")
            self.transcription_service._load_model()
            print("Qwen ASR model loaded.")

        else:
            raise RuntimeError(f"Unknown transcription mode: {mode}")

        if not self.transcription_service.is_available():
            if mode == "qwen":
                # Fall back to local Whisper if Qwen backends aren't installed yet
                self.logger.warning(
                    "Qwen ASR not available. Falling back to local Whisper. "
                    "Install qwen-asr (pip install qwen-asr) then restart."
                )
                print(
                    "⚠️  Qwen ASR not available, falling back to local Whisper. "
                    "Install qwen-asr (pip install qwen-asr) then restart."
                )
                model_size = self.config_manager.get_local_model_size()
                language = self.config_manager.get_transcription_language()
                self.transcription_service = LocalWhisperService(
                    model_size=model_size, language=language
                )
                if not self.transcription_service.is_available():
                    raise RuntimeError(
                        "Neither Qwen ASR nor local Whisper is available"
                    )
            else:
                raise RuntimeError(
                    f"Transcription service ({mode}) is not available"
                )

    def _initialize_text_inserter(self) -> None:
        """Initialize text insertion component."""
        from src.system.text_insertion import TextInserter

        platform_name = self.config_manager.get_platform()
        self.text_inserter = TextInserter(platform_name=platform_name)

    def _initialize_vocabulary(self) -> None:
        """Initialize vocabulary manager for ASR context biasing."""
        config_dir = self.config_manager.config_dir
        # Include command trigger words as default vocabulary terms
        triggers = self.config_manager.get_command_triggers() if self.config_manager.is_command_mode_enabled() else []
        self.vocabulary_manager = VocabularyManager(config_dir, default_terms=triggers)

        # Register callback to push context changes to ASR service
        def _on_vocabulary_change(context_string):
            if self.transcription_service and hasattr(self.transcription_service, 'set_context'):
                self.transcription_service.set_context(context_string)
                self.logger.info(f"ASR context updated: {context_string}")

        self.vocabulary_manager.on_change(_on_vocabulary_change)

    def _initialize_corrections(self) -> None:
        """Initialize correction pipeline."""
        config_dir = self.config_manager.config_dir
        number_norm = self.config_manager.get_setting("number_normalization_enabled", True)
        self.correction_pipeline = CorrectionPipeline(config_dir, number_normalization_enabled=number_norm)

    def _initialize_training_data(self) -> None:
        """Initialize training data collector."""
        config_dir = self.config_manager.config_dir
        enabled = self.config_manager.get_setting("training_data_enabled", True)
        max_mb = self.config_manager.get_setting("training_data_max_mb", 2048)
        self.training_data_collector = TrainingDataCollector(config_dir, max_mb=max_mb, enabled=enabled)

    def _initialize_commands(self) -> None:
        """Initialize command mode components if enabled."""
        if self.config_manager.is_command_mode_enabled():
            # Initialize command detector with configured triggers
            triggers = self.config_manager.get_command_triggers()
            self.command_detector = CommandDetector(triggers)

            # Initialize command processor with LLM settings
            cmd_config = self.config_manager.get_command_mode_config()
            self.command_processor = CommandProcessor(
                openrouter_api_key=cmd_config.get("openrouter_api_key"),
                local_llm_endpoint=cmd_config.get("local_llm_endpoint"),
                model=cmd_config.get("openrouter_model"),
            )

            # Wire vocabulary and correction references into command processor
            self.command_processor.vocabulary_manager = self.vocabulary_manager
            self.command_processor.text_inserter = self.text_inserter
            self.command_processor.voicebox_app = self

            # Initialize responder
            response_method = cmd_config.get("response_method", "notification")
            self.command_responder = CommandResponder(
                method=response_method,
                gui_callback=None,  # Don't duplicate GUI callback
            )

    def _initialize_hotkeys(self) -> None:
        """Initialize hotkey management."""
        from src.system.hotkeys import HotkeyManager

        hotkey = self.config_manager.get_hotkey()
        self.hotkey_manager = HotkeyManager(callback=self._on_hotkey_pressed)

        # Register correction hotkey
        correction_hotkey = self.config_manager.get_setting("correction_hotkey", "ctrl+alt+space")
        if correction_hotkey:
            self.hotkey_manager.register_hotkey(correction_hotkey, self._on_correction_hotkey)

        self.hotkey_manager.set_hotkey(hotkey)

    def _on_hotkey_pressed(self) -> None:
        """Handle hotkey press events."""
        self.logger.debug(f"Hotkey pressed! Current state: {self.state.value}")
        with self._state_lock:
            if not self._running:
                self.logger.debug("App not running, ignoring hotkey")
                return

            if self.state == AppState.IDLE:
                self.logger.debug("Starting recording...")
                self._start_recording()
            elif self.state == AppState.RECORDING:
                self.logger.debug("Stopping recording and transcribing...")
                self._stop_recording_and_transcribe()
            else:
                self.logger.debug(
                    f"Hotkey pressed but app is in {self.state.value} state"
                )

    def _is_streaming_capable(self) -> bool:
        """Check if the current transcription service supports streaming."""
        return (
            isinstance(self.transcription_service, StreamingTranscriptionService)
            and self.transcription_service.supports_streaming()
            and self.config_manager.get_setting("qwen_streaming_enabled", True)
        )

    def _start_recording(self) -> None:
        """Start audio recording."""
        try:
            self.state = AppState.RECORDING
            self._recording_start_time = time.time()
            self._warned_recording_limit = False
            self._auto_stopping = False
            print("🎤 Recording...", end="", flush=True)

            # Compute max recording duration from transcription service
            self._max_recording_sec = None
            if hasattr(self.transcription_service, 'get_max_recording_seconds'):
                self._max_recording_sec = self.transcription_service.get_max_recording_seconds()
                if self._max_recording_sec:
                    self.logger.info(f"Max safe recording: {self._max_recording_sec:.0f}s")

            # Set up streaming if available
            if self._is_streaming_capable():
                self.logger.debug("Starting streaming transcription")
                self.transcription_service.start_streaming()

                # Wrap the feed_chunk callback with duration checking
                original_feed = self.transcription_service.feed_chunk

                def _checked_feed(chunk):
                    original_feed(chunk)
                    self._check_recording_duration()

                self.audio_recorder.set_chunk_callback(_checked_feed)
            else:
                # Even without streaming, check duration via a no-op wrapper
                if self._max_recording_sec:
                    def _duration_only_callback(chunk):
                        self._check_recording_duration()
                    self.audio_recorder.set_chunk_callback(_duration_only_callback)

            self.audio_recorder.start_recording()

        except Exception as e:
            print(f"Failed to start recording: {e}")
            self.state = AppState.ERROR
            time.sleep(2)  # Brief error state
            self.state = AppState.IDLE

    def _check_recording_duration(self) -> None:
        """Check elapsed recording time and warn/auto-stop if near the limit."""
        if not self._max_recording_sec or not self._recording_start_time:
            return
        elapsed = time.time() - self._recording_start_time

        # At 95% of max → auto-stop
        if elapsed >= self._max_recording_sec * 0.95:
            if not self._auto_stopping:
                self._auto_stopping = True
                self.logger.warning(f"Recording auto-stopped at {elapsed:.0f}s (limit {self._max_recording_sec:.0f}s)")
                self._auto_stop_recording()
            return

        # At 90% of max → warning toast (once)
        if not self._warned_recording_limit and elapsed >= self._max_recording_sec * 0.90:
            self._warned_recording_limit = True
            remaining = int(self._max_recording_sec - elapsed)
            self.logger.info(f"Recording duration warning at {elapsed:.0f}s, ~{remaining}s remaining")
            try:
                from src.utils.notify import notify
                notify("VoiceBox", f"~{remaining} seconds of recording remaining")
            except Exception:
                pass

    def _auto_stop_recording(self) -> None:
        """Auto-stop recording from the chunk callback thread."""
        # Run stop in a separate thread to avoid blocking the audio callback
        t = threading.Thread(target=self._auto_stop_recording_sync, daemon=True)
        t.start()

    def _auto_stop_recording_sync(self) -> None:
        """Perform the actual stop+transcribe, called from a helper thread."""
        try:
            with self._state_lock:
                if self.state != AppState.RECORDING:
                    return
                self._stop_recording_and_transcribe()
        except Exception as e:
            self.logger.error(f"Auto-stop failed: {e}")

    def _stop_recording_and_transcribe(self) -> None:
        """Stop recording and start transcription in background thread."""
        try:
            # Clear chunk callback before stopping
            streaming = self._is_streaming_capable()
            self.audio_recorder.clear_chunk_callback()

            print(" transcribing...", end="", flush=True)
            self.state = AppState.TRANSCRIBING

            # Stop recording and get audio file
            audio_file = self.audio_recorder.stop_recording()
            self.current_audio_file = audio_file

            # Choose streaming or normal transcription path
            if streaming:
                print(f"🧵 Creating streaming finish thread for: {audio_file}")
                transcription_thread = threading.Thread(
                    target=self._finish_streaming_and_insert, args=(audio_file,)
                )
            else:
                print(f"🧵 Creating transcription thread for: {audio_file}")
                transcription_thread = threading.Thread(
                    target=self._transcribe_and_insert, args=(audio_file,)
                )
            transcription_thread.daemon = True
            transcription_thread.start()
            print(f"🧵 Transcription thread started")

        except Exception as e:
            print(f"Failed to stop recording: {e}")
            self.state = AppState.ERROR
            time.sleep(2)
            self.state = AppState.IDLE

    def _process_transcribed_text(self, transcribed_text: str, audio_file: str = None) -> None:
        """Process transcribed text: apply corrections, detect commands, insert text."""
        if not transcribed_text or transcribed_text == "No speech detected":
            print(" (no speech detected)")
            self.state = AppState.IDLE
            return

        raw_text = transcribed_text
        corrections_applied = []

        # Apply correction pipeline (replaces old substitution manager)
        if self.correction_pipeline:
            original_text = transcribed_text
            result = self.correction_pipeline.apply(transcribed_text)
            transcribed_text = result.text
            corrections_applied = [
                {"stage": c.stage, "original": c.original, "corrected": c.corrected}
                for c in result.corrections
            ]

            # Show what was changed if different
            if original_text != transcribed_text:
                print(f" done!\nOriginal: {original_text}")
                print(f"Fixed:    {transcribed_text}")
            else:
                print(f" done!\n{transcribed_text}")
        else:
            print(f" done!\n{transcribed_text}")

        # Check if this is a command (after corrections for normalized triggers)
        is_command = False
        if self.command_detector and self.command_detector.is_command(
            transcribed_text
        ):
            is_command = True
            self.state = AppState.PROCESSING_COMMAND
            print("🎯 Command detected, processing...")

            # Extract command and check for clipboard flag
            trigger, command, has_clipboard = (
                self.command_detector.extract_command_with_clipboard(
                    transcribed_text
                )
            )
            if command:
                if has_clipboard:
                    # Get clipboard content and process with context
                    print("📋 Clipboard flag detected, reading clipboard...")
                    clipboard_data = (
                        self.text_inserter.get_clipboard_type_and_content()
                    )
                    result = self.command_processor.process_with_clipboard(
                        command, clipboard_data
                    )
                else:
                    # Process the command normally
                    result = self.command_processor.process(command)

                if result.get("success"):
                    # INSERT THE LLM RESPONSE AT CURSOR INSTEAD OF DISPLAYING
                    llm_response = result.get("response", "").strip()
                    if llm_response:
                        self.logger.debug(f"LLM Response: {llm_response}")

                        # Insert the LLM response at cursor
                        self.state = AppState.INSERTING
                        insertion_method = (
                            self.config_manager.get_text_insertion_method()
                        )
                        success = self.text_inserter.insert_text(
                            llm_response, method=insertion_method
                        )

                        # Notify GUI of command response
                        if self.on_transcription_complete:
                            self.on_transcription_complete(
                                f"[Command] {llm_response}"
                            )

                        if not success:
                            self.logger.error("Failed to insert LLM response")
                    else:
                        self.logger.warning("Empty LLM response")
                else:
                    # Show error but don't insert anything
                    error_msg = result.get("error", "Unknown error")
                    self.logger.error(f"Command failed: {error_msg}")

                    # Optionally display error via responder
                    self.command_responder.display_response(result)
            else:
                self.logger.warning("No command text found after trigger")

            # Save training data for commands too
            if self.training_data_collector and audio_file:
                self.training_data_collector.save_sample(
                    audio_file=audio_file,
                    raw_transcript=raw_text,
                    auto_corrected=transcribed_text,
                    corrections_applied=corrections_applied,
                    was_command=True,
                )

            # Skip normal text insertion for commands
            return

        # Normal text insertion flow
        if self.on_transcription_complete:
            self.logger.debug("Notifying GUI of transcription completion")
            self.on_transcription_complete(transcribed_text)

        # Insert text
        self.state = AppState.INSERTING
        insertion_method = self.config_manager.get_text_insertion_method()
        success = self.text_inserter.insert_text(
            transcribed_text, method=insertion_method
        )

        if not success:
            self.logger.error("Failed to insert text")
        else:
            self.logger.info("Text inserted successfully")

            # Save training data
            data_id = None
            if self.training_data_collector and audio_file:
                data_id = self.training_data_collector.save_sample(
                    audio_file=audio_file,
                    raw_transcript=raw_text,
                    auto_corrected=transcribed_text,
                    corrections_applied=corrections_applied,
                    was_command=False,
                )

            # Track last insertion for correction flow
            self._last_insertion = {
                "text": transcribed_text,
                "char_count": len(transcribed_text),
                "audio_file": audio_file,
                "data_id": data_id,
            }

    def _transcribe_and_insert(self, audio_file: str) -> None:
        """Transcribe audio and insert text (runs in background thread)."""
        print(f"🎙️ _transcribe_and_insert() called with audio file: {audio_file}")
        try:
            # Transcribe audio
            print("🎙️ Calling transcription service...")
            transcribed_text = self.transcription_service.transcribe(audio_file)
            print(f"🎙️ Transcription result: '{transcribed_text}'")

            self._process_transcribed_text(transcribed_text, audio_file=audio_file)

        except TranscriptionError as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "transcription"})
            self._report_error(
                f"Transcription failed: {str(e)}",
                error_type="Transcription",
                suggestion=suggestion,
            )

        except Exception as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "transcription"})
            self._report_error(
                f"Unexpected error: {e}", error_type="General", suggestion=suggestion
            )

        finally:
            # Cleanup and return to idle
            self._cleanup_audio_file(audio_file)
            self.current_audio_file = None
            self.state = AppState.IDLE

    def _finish_streaming_and_insert(self, audio_file: str) -> None:
        """Finish streaming transcription and insert text (runs in background thread)."""
        print(f"🎙️ _finish_streaming_and_insert() called with audio file: {audio_file}")
        try:
            print("🎙️ Finishing streaming transcription...")
            transcribed_text = self.transcription_service.finish_streaming()
            print(f"🎙️ Streaming result: '{transcribed_text}'")

            self._process_transcribed_text(transcribed_text, audio_file=audio_file)

        except TranscriptionError as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "transcription"})
            self._report_error(
                f"Streaming transcription failed: {str(e)}",
                error_type="Transcription",
                suggestion=suggestion,
            )

        except Exception as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "transcription"})
            self._report_error(
                f"Unexpected error: {e}", error_type="General", suggestion=suggestion
            )

        finally:
            # Cleanup and return to idle
            self._cleanup_audio_file(audio_file)
            self.current_audio_file = None
            self.state = AppState.IDLE

    def _on_correction_hotkey(self) -> None:
        """Handle correction hotkey press — open correction overlay for last transcription."""
        if not self._last_insertion:
            self.logger.debug("No recent transcription to correct")
            return

        last = self._last_insertion
        original_text = last["text"]

        # Show correction UI
        from src.ui.review import prompt_correction
        corrected = prompt_correction(original_text, use_gui=self._use_gui)

        if corrected is None or corrected == original_text:
            return

        # Select and replace old text in target app
        if self.text_inserter:
            success = self.text_inserter.select_and_replace(
                last["char_count"], corrected
            )
            if success:
                self.logger.info(f"Correction applied: '{original_text}' -> '{corrected}'")

                # Update training data
                if self.training_data_collector and last.get("data_id"):
                    self.training_data_collector.update_sample(
                        last["data_id"], corrected
                    )

                # Check for new vocabulary terms
                if self.vocabulary_manager:
                    existing_terms = {t.lower() for t in self.vocabulary_manager.get_terms()}
                    corrected_words = set(corrected.split())
                    original_words = set(original_text.split())
                    new_words = corrected_words - original_words
                    for word in new_words:
                        if len(word) > 2 and word.lower() not in existing_terms:
                            # Don't auto-add common words, only unusual ones
                            if word[0].isupper() or any(c.isdigit() for c in word):
                                self.vocabulary_manager.add_term(word)
                                self.logger.info(f"Auto-added '{word}' to vocabulary")

        # Clear last insertion
        self._last_insertion = None

    def _cleanup_audio_file(self, file_path: str) -> None:
        """Clean up temporary audio file."""
        # Don't clean up if training data collector already copied it
        if self.config_manager.get_setting("auto_cleanup_temp_files", True):
            self.audio_recorder.cleanup_temp_file(file_path)

    def run_forever(self) -> None:
        """Run the application until interrupted."""
        if not self.start():
            return

        try:
            print("Press Ctrl+C to exit\n")

            # Try to disable terminal echo to prevent F12 escape sequences (Unix-like systems only)
            old_settings = None
            try:
                import termios
                import tty

                if sys.stdin.isatty():
                    old_settings = termios.tcgetattr(sys.stdin)
                    # Disable echo
                    new_settings = termios.tcgetattr(sys.stdin)
                    new_settings[3] = new_settings[3] & ~termios.ECHO
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)
            except (ImportError, Exception):
                # termios not available on Windows or error occurred
                pass

            while self._running:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\n\nExiting...")
        finally:
            # Restore terminal settings if they were changed
            if old_settings is not None:
                try:
                    import termios

                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                except:
                    pass
            self.stop()

    def _handle_terminal_input(self) -> None:
        """Handle terminal input commands in a separate thread."""
        try:
            while self._running:
                try:
                    command = input().strip()
                    if not command:
                        continue

                    parts = command.split(" ", 1)
                    cmd = parts[0].lower()

                    if cmd in ["quit", "exit"]:
                        print("Exiting VoiceBox...")
                        self._running = False
                        break

                    elif cmd == "status":
                        self._print_status()

                    elif cmd == "hotkey":
                        if len(parts) < 2:
                            print("Usage: hotkey <combination>")
                            print("Examples: hotkey ctrl+alt+v, hotkey f12")
                            print(f"Current: {self.config_manager.get_hotkey()}")
                        else:
                            self._change_hotkey(parts[1])

                    elif cmd == "help":
                        self._print_help()

                    else:
                        print(f"Unknown command: {cmd}")
                        print("Type 'help' for available commands")

                except EOFError:
                    # Input stream closed
                    break
                except Exception as e:
                    print(f"Error processing command: {e}")

        except Exception as e:
            print(f"Terminal input handler error: {e}")

    def _print_status(self) -> None:
        """Print current application status."""
        status = self.get_status()
        print(f"\n--- VoiceBox Status ---")
        print(f"State: {status['state']}")
        print(f"Transcription mode: {status['transcription_mode']}")
        print(f"Hotkey: {status['hotkey']}")
        print(f"Recording: {status['recording']}")
        print(f"Running: {status['running']}")
        print()

    def _print_help(self) -> None:
        """Print help information."""
        print("\n--- Available Commands ---")
        print("hotkey <combination> - Change hotkey binding")
        print("                       Examples: ctrl+alt+v, f12, alt+space")
        print("status               - Show current status")
        print("help                 - Show this help")
        print("quit/exit            - Exit VoiceBox")
        print()

    def _change_hotkey(self, new_hotkey: str) -> None:
        """Change the hotkey combination."""
        try:
            # Validate the hotkey format
            old_hotkey = self.config_manager.get_hotkey()

            # Update the hotkey manager
            self.hotkey_manager.set_hotkey(new_hotkey)

            # Restart listening with new hotkey
            self.hotkey_manager.start_listening()

            # Save to config
            self.config_manager.set_setting("hotkey", new_hotkey)

            self.logger.info(f"Hotkey changed from '{old_hotkey}' to '{new_hotkey}'")

        except Exception as e:
            from src.utils.error_suggestions import get_suggestion

            suggestion = get_suggestion(e, {"operation": "hotkey_change"})
            self.logger.error(f"Failed to change hotkey: {e}")
            self.logger.info(f"Suggestion: {suggestion}")

    def reload_config(self) -> None:
        """Reload configuration and update components."""
        # Reload config manager
        self.config_manager._load_config()

        # Reload corrections
        if self.correction_pipeline:
            self.correction_pipeline.reload()

        # Reload vocabulary
        if self.vocabulary_manager:
            self.vocabulary_manager.load()

        # Reload hotkey if it changed
        new_hotkey = self.config_manager.get_hotkey()
        if (
            self.hotkey_manager
            and self.hotkey_manager.get_current_hotkey() != new_hotkey
        ):
            try:
                self.hotkey_manager.set_hotkey(new_hotkey)
                self.hotkey_manager.start_listening()
                self.logger.info(f"Hotkey updated to: {new_hotkey}")
            except Exception as e:
                self.logger.error(f"Failed to update hotkey: {e}")

        # Check if transcription settings changed (requires reinitialization)
        current_mode = self.config_manager.get_transcription_mode()
        current_model = self.config_manager.get_local_model_size()
        current_language = self.config_manager.get_transcription_language()
        current_api_key = self.config_manager.get_api_key()

        # Check if we need to reinitialize transcription service
        needs_transcription_reload = False
        if hasattr(self.transcription_service, "model_size"):
            # Local service
            if current_model != getattr(
                self.transcription_service, "model_size", None
            ) or current_language != getattr(
                self.transcription_service, "language", "auto"
            ):
                needs_transcription_reload = True
        elif hasattr(self.transcription_service, "api_key"):
            # API service
            if current_api_key != getattr(
                self.transcription_service, "api_key", None
            ) or current_language != getattr(
                self.transcription_service, "language", "auto"
            ):
                needs_transcription_reload = True

        if needs_transcription_reload:
            try:
                self.logger.debug("Reinitializing transcription service...")
                self._initialize_transcription()
                self.logger.info("Transcription service updated!")
            except Exception as e:
                self.logger.error(f"Failed to update transcription service: {e}")

        # Audio settings require restart notice (can't change during recording)
        current_sample_rate = self.config_manager.get_audio_sample_rate()
        current_channels = self.config_manager.get_audio_channels()
        if self.audio_recorder and (
            current_sample_rate != getattr(self.audio_recorder, "sample_rate", 16000)
            or current_channels != getattr(self.audio_recorder, "channels", 1)
        ):
            self.logger.warning(
                "Audio settings changed - restart VoiceBox for changes to take effect"
            )

        # Reload command mode settings
        if self.config_manager.is_command_mode_enabled():
            cmd_config = self.config_manager.get_command_mode_config()
            triggers = cmd_config.get("triggers", ["voicebox"])

            # Keep vocabulary default terms in sync with triggers
            if self.vocabulary_manager:
                self.vocabulary_manager.set_default_terms(triggers)

            # Initialize or update command components
            if not self.command_detector:
                self._initialize_commands()
                print("✅ Command mode enabled!")
            else:
                # Update existing components
                self.command_detector.triggers = triggers
                self.command_detector._build_trigger_pattern()

                if self.command_processor:
                    self.command_processor.set_openrouter_key(
                        cmd_config.get("openrouter_api_key", "")
                    )
                    self.command_processor.set_local_endpoint(
                        cmd_config.get("local_llm_endpoint", "")
                    )
                    self.command_processor.set_model(
                        cmd_config.get("openrouter_model", "")
                    )

                if self.command_responder:
                    self.command_responder.set_method(
                        cmd_config.get("response_method", "notification")
                    )

                print("✅ Command mode settings updated!")
        else:
            # Disable command mode if it was enabled
            if self.command_detector:
                self.command_detector = None
                self.command_processor = None
                self.command_responder = None
            # Clear trigger-based default terms
            if self.vocabulary_manager:
                self.vocabulary_manager.set_default_terms([])
                print("✅ Command mode disabled")

        print("🔄 Configuration reloaded!")

    def get_status(self) -> dict:
        """Get current application status."""
        return {
            "state": self.state.value,
            "running": self._running,
            "transcription_mode": self.config_manager.get_transcription_mode(),
            "hotkey": self.config_manager.get_hotkey(),
            "recording": self.audio_recorder.is_recording()
            if self.audio_recorder
            else False,
        }

    def test_hotkey_capture(self, timeout: int = 10) -> bool:
        """
        Test if hotkey capture is working.

        Useful for diagnosing macOS Accessibility permission issues.

        Args:
            timeout: Seconds to wait for hotkey press

        Returns:
            True if hotkey was captured, False otherwise
        """
        hotkey = self.config_manager.get_hotkey()
        platform = self.config_manager.get_platform()

        print(f"\nHotkey Test")
        print("=" * 40)
        print(f"Platform: {platform}")
        print(f"Hotkey: {hotkey}")
        print(f"Timeout: {timeout} seconds")
        print("=" * 40)

        if platform == "macos":
            print("\nNote: On macOS, this requires Accessibility permissions.")
            print("If the test fails, check System Settings → Privacy & Security → Accessibility")

        print(f"\nPress '{hotkey}' within {timeout} seconds...")

        captured = threading.Event()

        def on_hotkey():
            print("\n✅ Hotkey captured successfully!")
            captured.set()

        try:
            test_manager = HotkeyManager(callback=on_hotkey)
            test_manager.set_hotkey(hotkey)
            test_manager.start_listening()

            success = captured.wait(timeout=timeout)
            test_manager.stop_listening()

            if not success:
                print("\n❌ Hotkey was NOT captured.")
                print("\nPossible causes:")
                if platform == "macos":
                    print("  • Accessibility permissions not granted")
                    print("  • Terminal app not added to Accessibility list")
                print("  • Hotkey conflict with another application")
                print("  • Invalid hotkey combination")
                print(f"\nTry a different hotkey with: --test-hotkey f11")

            return success

        except Exception as e:
            print(f"\n❌ Error setting up hotkey listener: {e}")
            return False


def _setup_signal_handlers():
    """Ensure Ctrl+C always exits, even during model downloads in threads."""
    import signal
    _first_interrupt = [True]

    def _handler(signum, frame):
        if _first_interrupt[0]:
            _first_interrupt[0] = False
            print("\nInterrupted. Press Ctrl+C again to force quit.")
            # Raise KeyboardInterrupt normally for clean shutdown
            raise KeyboardInterrupt
        else:
            # Second Ctrl+C: force exit immediately
            print("\nForce quitting...")
            os._exit(1)

    signal.signal(signal.SIGINT, _handler)


def _init_qwen_service(config_manager):
    """Initialize a QwenASRService from config for the API server."""
    from src.transcription.qwen_asr import QwenASRService
    from src.text.vocabulary import VocabularyManager

    qwen_config = config_manager.get_qwen_config()
    language = config_manager.get_transcription_language()

    # Load vocabulary context if available
    vocab = VocabularyManager(config_manager.config_dir)
    context = vocab.get_context_string()

    service = QwenASRService(
        model_size=qwen_config["model_size"],
        backend=qwen_config["backend"],
        language=language,
        kv_cache_mb=config_manager.get_setting("vllm_kv_cache_mb", 256),
        context=context,
    )
    print("Loading Qwen ASR model (may download on first run)...")
    service._load_model()
    print("Qwen ASR model loaded.")
    return service


def _get_api_port(config_manager):
    """Return API port, allowing the host launcher to override config."""
    env_port = os.environ.get("VOICEBOX_API_PORT")
    if env_port:
        try:
            port = int(env_port)
            if 0 < port <= 65535:
                return port
        except ValueError:
            pass
        print(f"Ignoring invalid VOICEBOX_API_PORT={env_port!r}")

    return config_manager.get_setting("api_port", 9876)


def _get_api_max_streams(config_manager):
    """Return API stream cap, allowing the host launcher to override config."""
    env_max = os.environ.get("VOICEBOX_API_MAX_STREAMS")
    if env_max:
        try:
            max_streams = int(env_max)
            if max_streams > 0:
                return max_streams
        except ValueError:
            pass
        print(f"Ignoring invalid VOICEBOX_API_MAX_STREAMS={env_max!r}")

    return config_manager.get_setting("api_max_streams", 8)


def _get_api_host():
    """Return API bind host, allowing containers to bind all interfaces."""
    return os.environ.get("VOICEBOX_API_HOST", "127.0.0.1")


def _start_api_server_only(config_manager):
    """Run the API server in the foreground (blocking). No GUI/hotkeys."""
    from src.api.server import configure, start_server

    host = _get_api_host()
    port = _get_api_port(config_manager)
    max_streams = _get_api_max_streams(config_manager)
    configure(None, max_streams=max_streams)
    print(f"Starting API server on http://{host}:{port}")
    server_thread = start_server(host=host, port=port, daemon=False)

    try:
        service = _init_qwen_service(config_manager)
    except Exception as exc:
        print(f"Failed to load Qwen ASR model: {exc}")
        os._exit(1)

    configure(service, max_streams=max_streams)
    server_thread.join()


def _start_api_daemon(app, config_manager):
    """Start the API server as a daemon thread, sharing the app's transcription service."""
    from src.api.server import configure, start_server

    # The app must have initialized transcription already via start()
    # We hook into it after the app starts — but start() is called inside run_forever.
    # Instead, use the app's service after start() by wrapping.
    host = _get_api_host()
    port = _get_api_port(config_manager)
    max_streams = _get_api_max_streams(config_manager)

    original_start = app.start

    def _patched_start():
        result = original_start()
        if result and app.transcription_service:
            configure(app.transcription_service, max_streams=max_streams)
            start_server(host=host, port=port, daemon=True)
            print(f"API server running on http://{host}:{port}")
        return result

    app.start = _patched_start


def _start_api_headless_for_gui(config_manager):
    """Start API server daemon before the GUI launches (standalone service)."""
    from src.api.server import configure, start_server

    service = _init_qwen_service(config_manager)
    host = _get_api_host()
    port = _get_api_port(config_manager)
    max_streams = _get_api_max_streams(config_manager)
    configure(service, max_streams=max_streams)
    start_server(host=host, port=port, daemon=True)
    print(f"API server running on http://{host}:{port}")


def main():
    """Main entry point."""
    _setup_signal_handlers()

    # Parse --debug flag first (before other args)
    debug_mode = "--debug" in sys.argv
    if debug_mode:
        from src.utils.logging import set_debug_mode

        set_debug_mode(True)

    # Import logger after debug mode is set
    logger = get_logger(__name__)

    if debug_mode:
        logger.info("Debug mode enabled - verbose logging active")

    # Handle command line arguments
    cli_mode = "--cli" in sys.argv
    force_mode = "--force" in sys.argv
    serve_mode = "--serve" in sys.argv
    serve_only_mode = "--serve-only" in sys.argv

    if len(sys.argv) > 1:
        if sys.argv[1] == "--test":
            logger.info("Running in test mode...")
            app = VoiceBoxApp()
            if not app.start():
                sys.exit(1)
            logger.info("Test completed, exiting...")
            app.stop()
            return
        elif sys.argv[1] == "--config":
            app = VoiceBoxApp()
            print(f"Configuration file: {app.config_manager.get_config_path()}")
            return
        elif sys.argv[1] == "--test-hotkey":
            # Test hotkey capture (useful for debugging macOS permissions)
            app = VoiceBoxApp()
            # Allow optional hotkey override: --test-hotkey f11
            if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
                app.config_manager.config["hotkey"] = sys.argv[2]
            success = app.test_hotkey_capture()
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--help":
            print("Usage: voicebox [--cli|--test|--test-hotkey|--config|--help|--debug|--force|--serve|--serve-only]")
            print("")
            print("VoiceBox runs in GUI mode by default (with system tray icon).")
            print("")
            print("Options:")
            print("  --cli         : Run in command-line mode (no GUI)")
            print("  --serve       : GUI mode + local API server on configured port")
            print("  --serve-only  : Headless API server only (no GUI/hotkeys)")
            print("  --test        : Test initialization and exit")
            print("  --test-hotkey : Test hotkey capture (diagnose permission issues)")
            print("                  Optionally specify hotkey: --test-hotkey f11")
            print("  --config      : Show configuration file path")
            print("  --force       : Kill any existing VoiceBox instance before starting")
            print("  --help        : Show this help")
            print("  --debug       : Enable verbose debug logging (can combine with other flags)")
            return

    # Ensure only one instance is running
    from src.utils.singleton import ensure_single_instance

    lock_name = "voicebox-api" if serve_only_mode else "voicebox"
    if not ensure_single_instance(kill_existing=force_mode, app_name=lock_name):
        if not force_mode:
            print("Hint: Use --force to stop the existing instance and start a new one.")
        sys.exit(1)

    # First-run setup wizard — runs in terminal before GUI or CLI launch
    config_manager = ConfigManager()
    if config_manager.is_first_run():
        from src.ui.setup_wizard import run_setup_wizard
        run_setup_wizard(config_manager)

    # --serve-only: headless API server, no GUI or hotkeys
    if serve_only_mode:
        logger.info("VoiceBox - Headless API server mode")
        _start_api_server_only(config_manager)
        return

    # CLI mode if --cli flag is present
    if cli_mode:
        logger.info("VoiceBox - Voice-to-Text Transcription Tool (CLI mode)")
        app = VoiceBoxApp()
        if serve_mode:
            _start_api_daemon(app, config_manager)
        app.run_forever()
    else:
        # GUI mode is the default
        if serve_mode:
            # Start API server in background before launching GUI
            _start_api_headless_for_gui(config_manager)
        from src.ui.gui import run_gui
        sys.exit(run_gui())


if __name__ == "__main__":
    main()
