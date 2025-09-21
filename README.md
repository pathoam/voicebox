# VoiceBox - Voice-to-Text Transcription Tool

A cross-platform voice-to-text transcription application that allows users to quickly transcribe speech using hotkey activation. The application captures audio from the microphone, transcribes it using speech-to-text technology, and automatically inserts the transcribed text at the cursor position.

## Features

- **Modern GUI Interface**: Professional system tray application with settings management
- **Global Hotkey Activation**: Press a configurable hotkey to start/stop recording
- **Multi-Language Support**: 20+ languages with auto-detection or manual selection
- **Intelligent Text Substitutions**: Automatic correction of technical terms (e.g., "superbase" → "Supabase")
- **Dual Transcription Modes**: Local Whisper models or OpenAI Whisper API
- **Terminal-Compatible Text Insertion**: Smart Ctrl+Shift+V insertion that works in terminals
- **Live Configuration Reload**: Settings changes take effect immediately without restart
- **Transcription History**: Real-time log of recent transcriptions with timestamps
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Simple Configuration**: GUI-based settings with JSON persistence

## Quick Start

### Quick Install (Recommended)

**Option 1: Install from PyPI** (Not yet published - use Option 2 for now)
```bash
# Install with uv (recommended) - Coming soon!
uv add voicebox

# Or with pip - Coming soon!
pip install voicebox

# Run immediately
voicebox --gui
```

**Option 2: Install from Source** (Current recommended method)
```bash
# Clone and install
git clone <repository-url>
cd voicebox
uv sync
uv run python gui.py
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

**GUI Mode (Recommended):**
1. **From executable:** `voicebox --gui` (after installation)
2. **From source:** `uv run python gui.py`

**CLI Mode:**
1. **From executable:** Just run `voicebox` (after installation)
2. **From source:** `make run` or `uv run python src/main.py`

**Using VoiceBox:**
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
  "local_model_size": "base",
  "transcription_language": "auto"
}
```

#### Transcription Modes

- **local**: Uses faster-whisper for offline transcription
  - Models: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`
  - No internet required after initial model download
  
- **api**: Uses OpenAI Whisper API
  - Requires internet connection and API key
  - Generally faster and more accurate

#### Language Selection

VoiceBox supports 20+ languages for improved accuracy:
- **auto**: Auto-detect language (default)
- **en**: English, **es**: Spanish, **fr**: French, **de**: German
- **ja**: Japanese, **zh**: Chinese, **ru**: Russian, **ar**: Arabic
- And many more available in the GUI settings

Specifying the correct language significantly improves transcription accuracy for technical terms.

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

## Advanced Features

### Text Substitutions

VoiceBox includes intelligent text correction for commonly misheard technical terms:

**Built-in corrections include:**
- `superbase` → `Supabase`
- `versel` → `Vercel`
- `get hub` → `GitHub`
- `java script` → `JavaScript`
- `mongo db` → `MongoDB`
- `a p i` → `API`
- And 70+ more technical terms

**Managing substitutions:**
1. Open Settings → Substitutions tab
2. Add custom corrections for your specific terminology
3. Import/export substitution lists
4. Changes take effect immediately (no restart needed)

### GUI Features

**System Tray Integration:**
- Minimizes to system tray for background operation
- Right-click menu for quick access
- Visual status indicators

**Settings Management:**
- Tabbed interface for organized configuration
- Real-time validation and feedback
- Import/export functionality

**Transcription History:**
- Real-time log of all transcriptions
- Timestamp tracking
- Auto-scrolling display

## Command Line Options

```bash
python main.py --help     # Show help
python main.py --gui      # Run with GUI (system tray)
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
│   ├── local.py          # Local Whisper with language support
│   └── api.py            # OpenAI API with language support
├── system/
│   ├── hotkeys.py        # Global hotkey handling
│   └── text_insertion.py # Text insertion with terminal support
├── text/
│   └── substitutions.py  # Intelligent text corrections
├── ui/
│   └── gui.py            # PyQt6 GUI interface
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

# Test text substitutions
from text.substitutions import SubstitutionManager
sub_manager = SubstitutionManager()
corrected = sub_manager.apply_substitutions("I'm using superbase with versel")
print(corrected)  # "I'm using Supabase with Vercel"
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

**PyPI Package:**
```bash
# Build package for PyPI
uv run python -m build

# Publish to PyPI (see PUBLISHING.md for details)
uv run twine upload dist/*
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