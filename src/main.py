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
from commands.detector import CommandDetector
from commands.processor import CommandProcessor
from commands.responder import CommandResponder


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
        print(f"🏷️ VoiceBoxApp instance created with ID: {self.app_id}")
        self.state = AppState.IDLE
        self.config_manager = ConfigManager()
        
        # Initialize components
        self.audio_recorder: Optional[AudioRecorder] = None
        self.transcription_service: Optional[TranscriptionService] = None
        self.hotkey_manager: Optional[HotkeyManager] = None
        self.text_inserter: Optional[TextInserter] = None
        self.substitution_manager: Optional[SubstitutionManager] = None
        
        # Command mode components
        self.command_detector: Optional[CommandDetector] = None
        self.command_processor: Optional[CommandProcessor] = None
        self.command_responder: Optional[CommandResponder] = None
        
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
            self._initialize_commands()
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
        platform_name = self.config_manager.get_platform()
        self.text_inserter = TextInserter(platform_name=platform_name)
        
    def _initialize_substitutions(self) -> None:
        """Initialize text substitution manager."""
        config_dir = self.config_manager.config_dir
        self.substitution_manager = SubstitutionManager(config_dir)
        
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
                model=cmd_config.get("openrouter_model")
            )
            
            # Initialize responder
            response_method = cmd_config.get("response_method", "notification")
            self.command_responder = CommandResponder(
                method=response_method,
                gui_callback=None  # Don't duplicate GUI callback
            )
            
    def _initialize_hotkeys(self) -> None:
        """Initialize hotkey management."""
        hotkey = self.config_manager.get_hotkey()
        self.hotkey_manager = HotkeyManager(callback=self._on_hotkey_pressed)
        self.hotkey_manager.set_hotkey(hotkey)
        
    def _on_hotkey_pressed(self) -> None:
        """Handle hotkey press events."""
        print(f"🔥 Hotkey pressed! Current state: {self.state.value}")
        with self._state_lock:
            if not self._running:
                print("🔥 App not running, ignoring hotkey")
                return
                
            if self.state == AppState.IDLE:
                print("🔥 Starting recording...")
                self._start_recording()
            elif self.state == AppState.RECORDING:
                print("🔥 Stopping recording and transcribing...")
                self._stop_recording_and_transcribe()
            else:
                print(f"🔥 Hotkey pressed but app is in {self.state.value} state")
                
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
            print(f"🧵 Creating transcription thread for: {audio_file}")
            transcription_thread = threading.Thread(
                target=self._transcribe_and_insert,
                args=(audio_file,)
            )
            transcription_thread.daemon = True
            transcription_thread.start()
            print(f"🧵 Transcription thread started")
            
        except Exception as e:
            print(f"Failed to stop recording: {e}")
            self.state = AppState.ERROR
            time.sleep(2)
            self.state = AppState.IDLE
            
    def _transcribe_and_insert(self, audio_file: str) -> None:
        """Transcribe audio and insert text (runs in background thread)."""
        print(f"🎙️ _transcribe_and_insert() called with audio file: {audio_file}")
        try:
            # Transcribe audio
            print("🎙️ Calling transcription service...")
            transcribed_text = self.transcription_service.transcribe(audio_file)
            print(f"🎙️ Transcription result: '{transcribed_text}'")
            
            if not transcribed_text or transcribed_text == "No speech detected":
                print(" (no speech detected)")
                self.state = AppState.IDLE
                return
            
            # Apply text substitutions (this normalizes command triggers too)
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
            
            # Check if this is a command (after substitutions for normalized triggers)
            if self.command_detector and self.command_detector.is_command(transcribed_text):
                self.state = AppState.PROCESSING_COMMAND
                print("🎯 Command detected, processing...")
                
                # Extract command and check for clipboard flag
                trigger, command, has_clipboard = self.command_detector.extract_command_with_clipboard(transcribed_text)
                if command:
                    if has_clipboard:
                        # Get clipboard content and process with context
                        print("📋 Clipboard flag detected, reading clipboard...")
                        clipboard_data = self.text_inserter.get_clipboard_type_and_content()
                        result = self.command_processor.process_with_clipboard(command, clipboard_data)
                    else:
                        # Process the command normally
                        result = self.command_processor.process(command)
                    
                    if result.get("success"):
                        # INSERT THE LLM RESPONSE AT CURSOR INSTEAD OF DISPLAYING
                        llm_response = result.get("response", "").strip()
                        if llm_response:
                            print(f"🤖 LLM Response: {llm_response}")
                            
                            # Insert the LLM response at cursor
                            self.state = AppState.INSERTING
                            insertion_method = self.config_manager.get_text_insertion_method()
                            success = self.text_inserter.insert_text(llm_response, method=insertion_method)
                            
                            # Notify GUI of command response
                            if self.on_transcription_complete:
                                self.on_transcription_complete(f"[Command] {llm_response}")
                                
                            if not success:
                                print("❌ Failed to insert LLM response")
                        else:
                            print("❌ Empty LLM response")
                    else:
                        # Show error but don't insert anything
                        error_msg = result.get("error", "Unknown error")
                        print(f"❌ Command failed: {error_msg}")
                        
                        # Optionally display error via responder
                        self.command_responder.display_response(result)
                else:
                    print("❌ No command text found after trigger")
                
                # Skip normal text insertion for commands
                return
            
            # Normal text insertion flow
            print(f"📝 App {self.app_id}: About to insert normal text: '{transcribed_text}'")
            
            # TEMPORARILY DISABLE GUI CALLBACK TO DEBUG
            # Notify GUI if callback is set
            if False:  # self.on_transcription_complete:
                print("📢 Calling GUI callback")
                self.on_transcription_complete(transcribed_text)
            
            # Insert text
            self.state = AppState.INSERTING
            print("✏️ Calling text_inserter.insert_text()")
            
            insertion_method = self.config_manager.get_text_insertion_method()
            print(f"🔧 Config insertion method: {insertion_method}")
            
            # TEMPORARILY FORCE CLIPBOARD TO TEST
            insertion_method = "clipboard"
            print(f"🔧 Forced insertion method: {insertion_method}")
            
            # RE-ENABLE TEXT INSERTION WITH DEBUGGING
            success = self.text_inserter.insert_text(transcribed_text, method=insertion_method)
            
            if not success:
                print("❌ Failed to insert text")
            else:
                print("✅ Text insertion completed (but disabled)")
                
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
        
        # Reload command mode settings
        if self.config_manager.is_command_mode_enabled():
            cmd_config = self.config_manager.get_command_mode_config()
            
            # Initialize or update command components
            if not self.command_detector:
                self._initialize_commands()
                print("✅ Command mode enabled!")
            else:
                # Update existing components
                triggers = cmd_config.get("triggers", ["voicebox"])
                self.command_detector.triggers = triggers
                self.command_detector._build_trigger_pattern()
                
                if self.command_processor:
                    self.command_processor.set_openrouter_key(cmd_config.get("openrouter_api_key", ""))
                    self.command_processor.set_local_endpoint(cmd_config.get("local_llm_endpoint", ""))
                    self.command_processor.set_model(cmd_config.get("openrouter_model", ""))
                
                if self.command_responder:
                    self.command_responder.set_method(cmd_config.get("response_method", "notification"))
                
                print("✅ Command mode settings updated!")
        else:
            # Disable command mode if it was enabled
            if self.command_detector:
                self.command_detector = None
                self.command_processor = None
                self.command_responder = None
                print("✅ Command mode disabled")
                
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
            if __package__:
                from .ui.gui import run_gui  # type: ignore[import-not-found]
            else:
                from ui.gui import run_gui  # type: ignore[import-not-found]
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
