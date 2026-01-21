# Running VoiceBox

## Quick Start

VoiceBox runs in **GUI mode by default** (with system tray icon).

### GUI Mode (Default)
```bash
./voicebox
```

### GUI Mode with Debug Logging
```bash
./voicebox --debug
```

### CLI Mode (No GUI)
```bash
./voicebox --cli
```

### CLI Mode with Debug Logging
```bash
./voicebox --cli --debug
```

### Other Options
```bash
./voicebox --help           # Show help
./voicebox --config         # Show config file path
./voicebox --test           # Test initialization
./voicebox --test-hotkey    # Test hotkey capture (diagnose permission issues)
./voicebox --test-hotkey f11  # Test specific hotkey
```

### Using uv directly
```bash
uv run python3 src/main.py           # GUI mode (default)
uv run python3 src/main.py --cli     # CLI mode
uv run python3 src/main.py --debug   # Debug logging
```

## Installation Methods

### Method 1: pip install (Recommended)
```bash
pip install .
voicebox          # Run from anywhere
```

### Method 2: uv tool install
```bash
uv tool install .
voicebox          # Run from anywhere
```

### Method 3: Build Standalone Executable
```bash
python build.py   # Creates dist/voicebox executable
./dist/voicebox   # Run without Python
```

## Changes Made

### New Utilities
- `src/utils/logging.py` - Sparse logging system with --debug flag
- `src/utils/retry.py` - Retry decorator (1 retry, 1 second delay)
- `src/utils/error_suggestions.py` - Dynamic error suggestions

### Files Updated
- `src/main.py` - Removed debug code, added error reporting, --debug flag
- `src/system/text_insertion.py` - Removed forced clipboard overrides, debug prints, emojis
- `src/ui/gui.py` - Colored error display, --debug support
- `src/audio/capture.py` - Added logging and error suggestions
- `src/config/manager.py` - Fixed platform detection, added logging
- `src/commands/responder.py` - Added logging
- `src/transcription/api.py` - Added retry decorator, error suggestions
- `src/system/hotkeys.py` - Added logging
- `src/commands/processor.py` - Cleaned up emoji prints

## Logging Behavior

### Normal Mode (Default)
- **Console**: ERROR level only (critical errors)
- **File**: WARNING and above (`~/.config/VoiceBox/voicebox.log`)
- Sparse output for normal operation

### Debug Mode (`--debug` flag)
- **Console**: DEBUG and above with full details
- **File**: DEBUG and above with full stack traces
- Verbose output for troubleshooting

## Error Handling

- **Retry Logic**: API methods retry once on failure (1 second delay)
- **Error Suggestions**: Dynamic suggestions based on exception type
- **GUI Errors**: Displayed in color (red=error, orange=warning) with suggestions

## Import Errors (Expected)

You may see "Import utils.logging could not be resolved" errors in your editor. These are **expected** and will resolve at runtime when Python executes the code, as the utils modules exist in the correct location.
