#!/usr/bin/env python3

import sys
import time
import threading
import select
from enum import Enum
from typing import Optional

from audio.capture import AudioRecorder
from transcription.local import LocalWhisperService
from transcription.api import APIWhisperService
from transcription.base import TranscriptionService, TranscriptionError
from system.hotkeys import HotkeyManager
from system.text_insertion import TextInserter
from config.manager import ConfigManager
from text.substitutions import SubstitutionManager


class AppState(Enum):
    """Application state machine states."""
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    INSERTING = "inserting"
    ERROR = "error"


class VoiceBoxApp:
    """Main VoiceBox application coordinator."""
    
    def __init__(self):
        self.state = AppState.IDLE
        self.config_manager = ConfigManager()
        
        # Initialize components
        self.audio_recorder: Optional[AudioRecorder] = None
        self.transcription_service: Optional[TranscriptionService] = None
        self.hotkey_manager: Optional[HotkeyManager] = None
        self.text_inserter: Optional[TextInserter] = None
        self.substitution_manager: Optional[SubstitutionManager] = None
        
        # Runtime state
        self.current_audio_file: Optional[str] = None
        self._running = False
        self._state_lock = threading.Lock()
        
        # Callbacks for GUI integration
        self.on_transcription_complete = None
        self.on_status_change = None
        
    def start(self) -> bool:
        """Initialize and start the application."""
        try:
            # Check if first run
            if self.config_manager.is_first_run():
                self._show_first_run_info()
                
            # Initialize components
            self._initialize_audio()
            self._initialize_transcription()
            self._initialize_text_inserter()
            self._initialize_substitutions()
            self._initialize_hotkeys()
            
            # Start listening for hotkeys
            self.hotkey_manager.start_listening()
            
            self._running = True
            self.state = AppState.IDLE
            
            print(f"✅ VoiceBox ready! Press {self.config_manager.get_hotkey()} to start recording")
            
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
        
        self.audio_recorder = AudioRecorder(
            sample_rate=sample_rate,
            channels=channels
        )
        
    def _initialize_transcription(self) -> None:
        """Initialize transcription service based on configuration."""
        mode = self.config_manager.get_transcription_mode()
        
        if mode == "local":
            model_size = self.config_manager.get_local_model_size()
            language = self.config_manager.get_transcription_language()
            self.transcription_service = LocalWhisperService(model_size=model_size, language=language)
            
        elif mode == "api":
            api_key = self.config_manager.get_api_key()
            if not api_key:
                raise RuntimeError("API mode selected but no API key configured")
            language = self.config_manager.get_transcription_language()
            self.transcription_service = APIWhisperService(api_key=api_key, language=language)
            
        else:
            raise RuntimeError(f"Unknown transcription mode: {mode}")
            
        if not self.transcription_service.is_available():
            raise RuntimeError(f"Transcription service ({mode}) is not available")
            
    def _initialize_text_inserter(self) -> None:
        """Initialize text insertion component."""
        self.text_inserter = TextInserter()
        
    def _initialize_substitutions(self) -> None:
        """Initialize text substitution manager."""
        config_dir = self.config_manager.config_dir
        self.substitution_manager = SubstitutionManager(config_dir)
        
    def _initialize_hotkeys(self) -> None:
        """Initialize hotkey management."""
        hotkey = self.config_manager.get_hotkey()
        self.hotkey_manager = HotkeyManager(callback=self._on_hotkey_pressed)
        self.hotkey_manager.set_hotkey(hotkey)
        
    def _on_hotkey_pressed(self) -> None:
        """Handle hotkey press events."""
        with self._state_lock:
            if not self._running:
                return
                
            if self.state == AppState.IDLE:
                self._start_recording()
            elif self.state == AppState.RECORDING:
                self._stop_recording_and_transcribe()
            else:
                print(f"Hotkey pressed but app is in {self.state.value} state")
                
    def _start_recording(self) -> None:
        """Start audio recording."""
        try:
            self.state = AppState.RECORDING
            print("🎤 Recording...", end="", flush=True)
            
            self.audio_recorder.start_recording()
            
        except Exception as e:
            print(f"Failed to start recording: {e}")
            self.state = AppState.ERROR
            time.sleep(2)  # Brief error state
            self.state = AppState.IDLE
            
    def _stop_recording_and_transcribe(self) -> None:
        """Stop recording and start transcription in background thread."""
        try:
            print(" transcribing...", end="", flush=True)
            self.state = AppState.TRANSCRIBING
            
            # Stop recording and get audio file
            audio_file = self.audio_recorder.stop_recording()
            self.current_audio_file = audio_file
            
            # Start transcription in background
            transcription_thread = threading.Thread(
                target=self._transcribe_and_insert,
                args=(audio_file,)
            )
            transcription_thread.daemon = True
            transcription_thread.start()
            
        except Exception as e:
            print(f"Failed to stop recording: {e}")
            self.state = AppState.ERROR
            time.sleep(2)
            self.state = AppState.IDLE
            
    def _transcribe_and_insert(self, audio_file: str) -> None:
        """Transcribe audio and insert text (runs in background thread)."""
        try:
            # Transcribe audio
            transcribed_text = self.transcription_service.transcribe(audio_file)
            
            if not transcribed_text or transcribed_text == "No speech detected":
                print(" (no speech detected)")
                self.state = AppState.IDLE
                return
            
            # Apply text substitutions
            if self.substitution_manager:
                original_text = transcribed_text
                transcribed_text = self.substitution_manager.apply_substitutions(transcribed_text)
                
                # Show what was changed if different
                if original_text != transcribed_text:
                    print(f" done!\nOriginal: {original_text}")
                    print(f"Fixed:    {transcribed_text}")
                else:
                    print(f" done!\n{transcribed_text}")
            else:
                print(f" done!\n{transcribed_text}")
            
            # Notify GUI if callback is set
            if self.on_transcription_complete:
                self.on_transcription_complete(transcribed_text)
            
            # Insert text
            self.state = AppState.INSERTING
            
            insertion_method = self.config_manager.get_text_insertion_method()
            success = self.text_inserter.insert_text(transcribed_text, method=insertion_method)
            
            if not success:
                print("❌ Failed to insert text")
                
        except TranscriptionError as e:
            print(f"❌ Transcription failed: {e}")
            
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            
        finally:
            # Cleanup and return to idle
            self._cleanup_audio_file(audio_file)
            self.current_audio_file = None
            self.state = AppState.IDLE
            
    def _cleanup_audio_file(self, file_path: str) -> None:
        """Clean up temporary audio file."""
        if self.config_manager.get_setting("auto_cleanup_temp_files", True):
            self.audio_recorder.cleanup_temp_file(file_path)
            
    def _show_first_run_info(self) -> None:
        """Show first run information and setup."""
        print("\n" + "="*50)
        print("Welcome to VoiceBox!")
        print("="*50)
        print(f"Configuration file: {self.config_manager.get_config_path()}")
        print(f"Hotkey: {self.config_manager.get_hotkey()}")
        print(f"Transcription mode: {self.config_manager.get_transcription_mode()}")
        
        if self.config_manager.get_transcription_mode() == "api":
            if not self.config_manager.get_api_key():
                print("\n⚠️  API mode selected but no API key configured!")
                print("Please set your OpenAI API key in the config file or switch to local mode.")
                
        print("\nPress Ctrl+C to exit at any time")
        print("="*50 + "\n")
        
        # Mark first run as complete
        self.config_manager.set_setting("first_run", False)
        
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
                        
                    parts = command.split(' ', 1)
                    cmd = parts[0].lower()
                    
                    if cmd in ['quit', 'exit']:
                        print("Exiting VoiceBox...")
                        self._running = False
                        break
                        
                    elif cmd == 'status':
                        self._print_status()
                        
                    elif cmd == 'hotkey':
                        if len(parts) < 2:
                            print("Usage: hotkey <combination>")
                            print("Examples: hotkey ctrl+alt+v, hotkey f12")
                            print(f"Current: {self.config_manager.get_hotkey()}")
                        else:
                            self._change_hotkey(parts[1])
                            
                    elif cmd == 'help':
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
            
            print(f"✅ Hotkey changed from '{old_hotkey}' to '{new_hotkey}'")
            
        except Exception as e:
            print(f"❌ Failed to change hotkey: {e}")
            print("Make sure the hotkey format is valid (e.g., 'ctrl+shift+v')")
            
    def reload_config(self) -> None:
        """Reload configuration and update components."""
        # Reload config manager
        self.config_manager._load_config()
        
        # Reload substitutions
        if self.substitution_manager:
            self.substitution_manager.load_substitutions()
            
        # Reload hotkey if it changed
        new_hotkey = self.config_manager.get_hotkey()
        if self.hotkey_manager and self.hotkey_manager.get_current_hotkey() != new_hotkey:
            try:
                self.hotkey_manager.set_hotkey(new_hotkey)
                self.hotkey_manager.start_listening()
                print(f"✅ Hotkey updated to: {new_hotkey}")
            except Exception as e:
                print(f"❌ Failed to update hotkey: {e}")
        
        # Check if transcription settings changed (requires reinitialization)
        current_mode = self.config_manager.get_transcription_mode()
        current_model = self.config_manager.get_local_model_size()
        current_language = self.config_manager.get_transcription_language()
        current_api_key = self.config_manager.get_api_key()
        
        # Check if we need to reinitialize transcription service
        needs_transcription_reload = False
        if hasattr(self.transcription_service, 'model_size'):
            # Local service
            if (current_model != getattr(self.transcription_service, 'model_size', None) or
                current_language != getattr(self.transcription_service, 'language', 'auto')):
                needs_transcription_reload = True
        elif hasattr(self.transcription_service, 'api_key'):
            # API service  
            if (current_api_key != getattr(self.transcription_service, 'api_key', None) or
                current_language != getattr(self.transcription_service, 'language', 'auto')):
                needs_transcription_reload = True
        
        if needs_transcription_reload:
            try:
                print("🔄 Reinitializing transcription service...")
                self._initialize_transcription()
                print("✅ Transcription service updated!")
            except Exception as e:
                print(f"❌ Failed to update transcription service: {e}")
        
        # Audio settings require restart notice (can't change during recording)
        current_sample_rate = self.config_manager.get_audio_sample_rate()
        current_channels = self.config_manager.get_audio_channels()
        if (self.audio_recorder and 
            (current_sample_rate != getattr(self.audio_recorder, 'sample_rate', 16000) or
             current_channels != getattr(self.audio_recorder, 'channels', 1))):
            print("⚠️  Audio settings changed - restart VoiceBox for changes to take effect")
                
        print("🔄 Configuration reloaded!")
    
    def get_status(self) -> dict:
        """Get current application status."""
        return {
            "state": self.state.value,
            "running": self._running,
            "transcription_mode": self.config_manager.get_transcription_mode(),
            "hotkey": self.config_manager.get_hotkey(),
            "recording": self.audio_recorder.is_recording() if self.audio_recorder else False
        }


def main():
    """Main entry point."""
    # Handle command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--gui":
            # Run GUI mode
            from .ui.gui import run_gui
            sys.exit(run_gui())
        elif sys.argv[1] == "--test":
            print("VoiceBox - Voice-to-Text Transcription Tool")
            print("-" * 40)
            print("Running in test mode...")
            app = VoiceBoxApp()
            if not app.start():
                sys.exit(1)
            print("Test completed, exiting...")
            app.stop()
            return
        elif sys.argv[1] == "--config":
            app = VoiceBoxApp()
            print(f"Configuration file: {app.config_manager.get_config_path()}")
            return
        elif sys.argv[1] == "--help":
            print("Usage: python main.py [--gui|--test|--config|--help]")
            print("  --gui    : Run with graphical interface")
            print("  --test   : Test initialization and exit")
            print("  --config : Show configuration file path")
            print("  --help   : Show this help")
            return
    
    # Run CLI mode by default        
    print("VoiceBox - Voice-to-Text Transcription Tool")
    print("-" * 40)
    
    app = VoiceBoxApp()
    app.run_forever()


if __name__ == "__main__":
    main()