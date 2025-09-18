# VoiceBox - Voice-to-Text Transcription Tool

A cross-platform voice-to-text transcription application that allows users to quickly transcribe speech using hotkey activation. The application captures audio from the microphone, transcribes it using speech-to-text technology, and automatically inserts the transcribed text at the cursor position.

## Features

- **Global Hotkey Activation**: Press a configurable hotkey to start/stop recording
- **Dual Transcription Modes**: Local Whisper models or OpenAI Whisper API
- **Automatic Text Insertion**: Transcribed text is automatically inserted at cursor
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Simple Configuration**: JSON-based configuration with sensible defaults

## Quick Start

### Quick Install (Recommended)

**Option 1: Download Pre-built Package** (When available)
1. Go to [Releases](../../releases) page
2. Download the package for your platform:
   - `-portable` = No installation, run from anywhere
   - `-installer` = Install to system with menu integration
3. Extract and run - no Python required!

**Option 2: Build from Source** (Current method)
```bash
# Requires Python 3.8+ and uv
git clone <repository-url>
cd voicebox
make release  # Creates all packages in dist/
```

### Development Installation

**Prerequisites:**
- Python 3.8+ 
- [uv](https://docs.astral.sh/uv/) package manager
- Microphone access
- For API mode: OpenAI API key

**Setup:**
```bash
# Clone repository
git clone <repository-url>
cd voicebox

# Install with uv (recommended)
make dev
# OR manually: uv sync

# Run from source
make run  
# OR manually: uv run python src/main.py
```

### Usage

1. **From executable:** Just run `voicebox` (after installation)
2. **From source:** `make run` or `uv run python src/main.py`

2. Press the hotkey (default: `Ctrl+Space`) to start recording
3. Speak into your microphone
4. Press the hotkey again to stop recording and transcribe
5. The transcribed text will be automatically inserted at your cursor

## Configuration

Configuration is stored in a JSON file in your system's config directory:
- **Windows**: `%APPDATA%\VoiceBox\config.json`
- **macOS**: `~/Library/Application Support/VoiceBox/config.json`
- **Linux**: `~/.config/VoiceBox/config.json`

### Key Settings

```json
{
  "transcription_mode": "local",
  "hotkey": "ctrl+space",
  "api_key": "",
  "local_model_size": "base"
}
```

#### Transcription Modes

- **local**: Uses faster-whisper for offline transcription
  - Models: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`
  - No internet required after initial model download
  
- **api**: Uses OpenAI Whisper API
  - Requires internet connection and API key
  - Generally faster and more accurate

#### Hotkey Options

Common hotkey combinations:
- `ctrl+space` (default)
- `ctrl+shift+v`
- `ctrl+alt+v`
- `button9` (mouse side button)

### Setting up API Mode

1. Get an OpenAI API key from https://platform.openai.com/api-keys
2. Set the API key in config:
```json
{
  "transcription_mode": "api",
  "api_key": "your-api-key-here"
}
```

## Command Line Options

```bash
python main.py --help     # Show help
python main.py --test     # Test initialization
python main.py --config   # Show config file path
```

## Troubleshooting

### Audio Issues
- Check microphone permissions
- Try listing audio devices: modify the code to call `AudioRecorder.list_audio_devices()`

### Hotkey Not Working
- Check for conflicting applications using the same hotkey
- Try a different hotkey combination
- On Linux, you may need to run with appropriate permissions

### Transcription Issues
- **Local mode**: First run downloads the model (may take time)
- **API mode**: Check API key and internet connection
- Check console output for detailed error messages

### Text Insertion Issues
- Ensure the target application has focus
- Try different text insertion methods in config
- On macOS, you may need to grant accessibility permissions

## Development

### Project Structure
```
src/
├── main.py                 # Application entry point
├── audio/
│   └── capture.py         # Audio recording
├── transcription/
│   ├── base.py           # Service interface
│   ├── local.py          # Local Whisper
│   └── api.py            # OpenAI API
├── system/
│   ├── hotkeys.py        # Global hotkey handling
│   └── text_insertion.py # Text insertion
└── config/
    └── manager.py        # Configuration management
```

### Testing Components

Each component can be tested independently:

```python
# Test audio recording
from audio.capture import AudioRecorder
recorder = AudioRecorder()
recorder.start_recording()
# ... wait ...
audio_file = recorder.stop_recording()

# Test transcription
from transcription.local import LocalWhisperService
service = LocalWhisperService()
text = service.transcribe(audio_file)

# Test text insertion
from system.text_insertion import TextInserter
inserter = TextInserter()
inserter.insert_text("Hello world")
```

## Building Executable

**Simple build:**
```bash
make build
# OR: python build.py
```

**Cross-platform distribution:**
```bash
make dist              # Creates .tar.gz
./scripts/build-all.sh # Multi-platform (requires Docker)
```

**Manual PyInstaller:**
```bash
uv run pyinstaller build_config/voicebox.spec
```

Executables appear in `dist/` directory with installers included.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly on your platform
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) for efficient local transcription
- [OpenAI Whisper](https://openai.com/research/whisper) for the underlying speech recognition technology
- [pynput](https://github.com/moses-palmer/pynput) for cross-platform input handling