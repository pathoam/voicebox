# VoiceBox Installation Guide

## Option 1: Download Pre-built Executable (Easiest)

1. **Download** the latest release for your platform:
   - `voicebox-linux-x86_64.tar.gz` (Linux)  
   - `voicebox-windows-x86_64.zip` (Windows)
   - `voicebox-macos-arm64.tar.gz` (macOS)

2. **Extract** the archive:
   ```bash
   tar -xzf voicebox-linux-x86_64.tar.gz
   cd voicebox-linux-x86_64/
   ```

3. **Install** using the included script:
   ```bash
   # Linux/macOS:
   ./install.sh
   
   # Windows:
   install.bat
   ```

4. **Run VoiceBox:**
   ```bash
   voicebox
   ```

## Option 2: Build from Source

### Prerequisites
- **Python 3.8+**
- **uv package manager** (faster than pip)

### Install uv
```bash
# Auto-installer
./install-uv.sh

# OR manual install
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Build and Run
```bash
# Quick setup
make dev         # Install dependencies  
make run         # Run from source

# OR step by step
uv sync                           # Install dependencies
uv run python src/main.py        # Run VoiceBox

# Build executable
make build       # Creates single executable
```

## First Run Setup

1. **Launch VoiceBox** - it will show configuration info
2. **Test the hotkey** - default is `Ctrl+Shift+V`
3. **Choose transcription mode:**
   - **Local mode** (default): Downloads Whisper model automatically
   - **API mode**: Requires OpenAI API key

### Configure API Mode (Optional)
```bash
# Edit config file (location shown on first run)
{
  "transcription_mode": "api",
  "api_key": "your-openai-api-key-here"
}
```

## Usage

1. **Start VoiceBox** (runs in background)
2. **Press hotkey** to start recording 
3. **Speak** into microphone
4. **Press hotkey again** to stop and transcribe
5. **Text appears** at cursor automatically!

## Troubleshooting

### Audio Issues
- Check microphone permissions
- Try different audio device
- On Linux: Install `portaudio19-dev`

### Build Issues  
```bash
# Missing system dependencies (Linux)
sudo apt update
sudo apt install build-essential portaudio19-dev

# Clean and rebuild
make clean build
```

### Permission Issues
- **Linux**: May need to run with sudo for global hotkeys
- **macOS**: Grant accessibility permissions when prompted
- **Windows**: Run as administrator if hotkeys don't work

## Development

```bash
# Development workflow
make dev         # Install dev dependencies
make test        # Test the app
make build       # Build executable
make clean       # Clean build files
```

For more details, see [README.md](README.md).