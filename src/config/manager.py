import json
import os
from typing import Any, Optional, Dict
from pathlib import Path


class ConfigManager:
    """Configuration management for VoiceBox."""
    
    DEFAULT_CONFIG = {
        "transcription_mode": "local",  # "local" or "api"  
        "hotkey": "ctrl+space",  # Clean combination that avoids terminal escape sequences
        "api_key": "",
        "local_model_size": "base",
        "audio_sample_rate": 16000,
        "audio_channels": 1,
        "text_insertion_method": "auto",  # "auto", "clipboard", "typing"
        "auto_cleanup_temp_files": True,
        "voice_detection_sensitivity": 0.5,
        "first_run": True
    }
    
    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "config.json"
        self.config: Dict[str, Any] = {}
        self._ensure_config_dir()
        self._load_config()
        
    def _get_config_dir(self) -> Path:
        """Get the configuration directory path."""
        # Use platform-appropriate config directory
        if os.name == 'nt':  # Windows
            base_dir = os.getenv('APPDATA', os.path.expanduser('~'))
        elif os.name == 'posix':  # macOS and Linux
            if 'darwin' in os.sys.platform.lower():  # macOS
                base_dir = os.path.expanduser('~/Library/Application Support')
            else:  # Linux
                base_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        else:
            base_dir = os.path.expanduser('~')
            
        return Path(base_dir) / "VoiceBox"
        
    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Failed to create config directory: {e}")
            # Fallback to home directory
            self.config_dir = Path.home() / ".voicebox"
            self.config_file = self.config_dir / "config.json"
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
    def _load_config(self) -> None:
        """Load configuration from file."""
        # Start with defaults
        self.config = self.DEFAULT_CONFIG.copy()
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    # Update defaults with saved values
                    self.config.update(saved_config)
                print(f"Configuration loaded from: {self.config_file}")
            except Exception as e:
                print(f"Failed to load config: {e}")
                print("Using default configuration")
        else:
            print("No configuration file found, using defaults")
            self._save_config()  # Create initial config file
            
    def _save_config(self) -> bool:
        """Save current configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to save config: {e}")
            return False
            
    def get_transcription_mode(self) -> str:
        """Get transcription mode (local or api)."""
        return self.config.get("transcription_mode", "local")
        
    def get_hotkey(self) -> str:
        """Get configured hotkey combination."""
        return self.config.get("hotkey", "ctrl+space")
        
    def get_api_key(self) -> Optional[str]:
        """Get OpenAI API key."""
        key = self.config.get("api_key", "")
        return key if key else None
        
    def get_local_model_size(self) -> str:
        """Get local Whisper model size."""
        return self.config.get("local_model_size", "base")
        
    def get_audio_sample_rate(self) -> int:
        """Get audio sample rate."""
        return self.config.get("audio_sample_rate", 16000)
        
    def get_audio_channels(self) -> int:
        """Get number of audio channels."""
        return self.config.get("audio_channels", 1)
        
    def get_text_insertion_method(self) -> str:
        """Get text insertion method."""
        return self.config.get("text_insertion_method", "auto")
        
    def is_first_run(self) -> bool:
        """Check if this is the first run."""
        return self.config.get("first_run", True)
        
    def set_setting(self, key: str, value: Any) -> bool:
        """
        Set a configuration value.
        
        Args:
            key: Configuration key
            value: Value to set
            
        Returns:
            True if successfully saved, False otherwise
        """
        if key in self.DEFAULT_CONFIG:
            old_value = self.config.get(key)
            self.config[key] = value
            
            if self._save_config():
                print(f"Setting updated: {key} = {value}")
                if key == "first_run" and value is False:
                    print("First run setup completed")
                return True
            else:
                # Revert on save failure
                self.config[key] = old_value
                return False
        else:
            print(f"Unknown configuration key: {key}")
            return False
            
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a configuration value with optional default."""
        return self.config.get(key, default)
        
    def reset_to_defaults(self) -> bool:
        """Reset configuration to defaults."""
        self.config = self.DEFAULT_CONFIG.copy()
        return self._save_config()
        
    def get_config_path(self) -> str:
        """Get the path to the configuration file."""
        return str(self.config_file)
        
    def validate_config(self) -> Dict[str, str]:
        """
        Validate current configuration.
        
        Returns:
            Dictionary of validation errors (empty if valid)
        """
        errors = {}
        
        # Validate transcription mode
        if self.config.get("transcription_mode") not in ["local", "api"]:
            errors["transcription_mode"] = "Must be 'local' or 'api'"
            
        # Validate API key if using API mode
        if self.config.get("transcription_mode") == "api":
            if not self.config.get("api_key"):
                errors["api_key"] = "API key required for API mode"
                
        # Validate model size
        valid_models = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
        if self.config.get("local_model_size") not in valid_models:
            errors["local_model_size"] = f"Must be one of: {valid_models}"
            
        # Validate sample rate
        sample_rate = self.config.get("audio_sample_rate")
        if not isinstance(sample_rate, int) or sample_rate < 8000:
            errors["audio_sample_rate"] = "Must be integer >= 8000"
            
        return errors
        
    def export_config(self, file_path: str) -> bool:
        """Export configuration to a file."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to export config: {e}")
            return False
            
    def import_config(self, file_path: str) -> bool:
        """Import configuration from a file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
                
            # Validate imported config
            for key, value in imported_config.items():
                if key in self.DEFAULT_CONFIG:
                    self.config[key] = value
                    
            return self._save_config()
        except Exception as e:
            print(f"Failed to import config: {e}")
            return False