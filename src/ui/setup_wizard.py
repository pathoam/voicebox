"""First-run setup wizard for VoiceBox."""

import sys
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from src.config.manager import ConfigManager


@dataclass
class SystemInfo:
    """Detected system capabilities."""

    gpu_available: bool = False
    gpu_name: str = "unknown"
    vram_gb: float = 0.0
    ram_gb: float = 0.0
    disk_free_gb: float = 0.0
    platform: str = "unknown"


def _scan_system(config_manager: ConfigManager) -> SystemInfo:
    """Detect system capabilities. Each field detected independently."""
    info = SystemInfo()

    info.platform = config_manager.get_platform()

    # GPU detection via torch, with nvidia-smi fallback
    try:
        import torch

        info.gpu_available = torch.cuda.is_available()
        if info.gpu_available:
            props = torch.cuda.get_device_properties(0)
            info.gpu_name = props.name
            info.vram_gb = round(props.total_memory / (1024**3), 1)
    except (ImportError, Exception):
        pass

    if not info.gpu_available:
        try:
            import subprocess

            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                line = result.stdout.strip().split("\n")[0]
                name, mem_mib = line.rsplit(",", 1)
                info.gpu_available = True
                info.gpu_name = name.strip()
                info.vram_gb = round(float(mem_mib.strip()) / 1024, 1)
        except Exception:
            pass

    # RAM detection
    try:
        import psutil

        info.ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    except (ImportError, Exception):
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        info.ram_gb = round(kb / (1024**2), 1)
                        break
        except Exception:
            pass

    # Disk free space
    try:
        usage = shutil.disk_usage(Path.home())
        info.disk_free_gb = round(usage.free / (1024**3), 1)
    except Exception:
        pass

    return info


def _recommend(info: SystemInfo) -> Tuple[str, str]:
    """Return (model_size, reason). Always recommends GPU Qwen."""
    if info.gpu_available and info.vram_gb >= 6:
        return (
            "1.7B",
            f"GPU with {info.vram_gb}g VRAM \u2014 1.7B for best accuracy",
        )
    if info.gpu_available:
        return (
            "0.6B",
            f"GPU with {info.vram_gb}g VRAM \u2014 0.6B for speed",
        )
    return ("0.6B", "No GPU detected \u2014 0.6B (will fall back to Whisper if needed)")


def _prompt(text: str, valid: List[str], default: str) -> str:
    """Prompt user for input, looping until valid. Returns default on failure."""
    max_retries = 5
    for _ in range(max_retries):
        try:
            raw = input(text).strip()
            if raw == "" and default:
                return default
            if raw in valid:
                return raw
            print(f"  Invalid choice. Please enter one of: {', '.join(valid)}")
        except KeyboardInterrupt:
            print("\n\nSetup cancelled.")
            raise SystemExit(0)
        except (EOFError, OSError):
            return default
    return default


def _save_choices(
    config_manager: ConfigManager,
    mode: str,
    model_size: str = "",
    api_key: str = "",
) -> None:
    """Persist wizard choices to config."""
    config_manager.set_setting("transcription_mode", mode)

    if mode == "qwen":
        config_manager.set_setting("qwen_model_size", model_size)
        config_manager.set_setting("qwen_backend", "gpu")
    elif mode == "local":
        config_manager.set_setting("local_model_size", model_size)
    elif mode == "api":
        if api_key:
            config_manager.set_setting("api_key", api_key)

    config_manager.set_setting("first_run", False)


def run_setup_wizard(config_manager: ConfigManager) -> bool:
    """Run the first-run setup wizard. Returns True on success."""

    # --- System scan ---
    print()
    print("\u2550" * 54)
    print("  VoiceBox Setup")
    print("\u2550" * 54)
    print()
    print("Scanning system...")
    print()

    info = _scan_system(config_manager)

    # Display system info
    if info.gpu_available:
        print(f"  GPU:        {info.gpu_name} ({info.vram_gb} GB VRAM)")
    else:
        print("  GPU:        None detected")
    if info.ram_gb > 0:
        print(f"  RAM:        {info.ram_gb} GB")
    if info.disk_free_gb > 0:
        print(f"  Disk free:  {info.disk_free_gb} GB")

    rec_size, rec_reason = _recommend(info)

    print()
    print("\u2500" * 54)
    print(f"Recommended: Qwen ASR {rec_size}")
    print(f"  {rec_reason}")
    print("\u2500" * 54)

    # --- Non-interactive mode ---
    if not sys.stdin.isatty():
        _save_choices(config_manager, "qwen", rec_size)
        return True

    # --- Model size choice ---
    _choose_model(config_manager, info, rec_size)

    _print_confirmation(config_manager)
    return True


def _choose_model(
    config_manager: ConfigManager,
    info: SystemInfo,
    rec_size: str,
) -> None:
    """Choose Qwen model size."""
    rec = "2" if rec_size == "1.7B" else "1"
    print()
    print("Choose model size:")
    print()
    if rec == "1":
        print("  1. Qwen 0.6B  \u2014 ~1.9 GB download, fast           (recommended)")
        print("  2. Qwen 1.7B  \u2014 ~3.4 GB download, best accuracy")
    else:
        print("  1. Qwen 0.6B  \u2014 ~1.9 GB download, fast")
        print("  2. Qwen 1.7B  \u2014 ~3.4 GB download, best accuracy  (recommended)")
    print("  3. Advanced options...")
    print()

    choice = _prompt(f"Enter choice [1-3] (default: {rec}): ", ["1", "2", "3"], rec)

    if choice == "1":
        _save_choices(config_manager, "qwen", "0.6B")
    elif choice == "2":
        _save_choices(config_manager, "qwen", "1.7B")
    elif choice == "3":
        _advanced_menu(config_manager, rec_size)


def _advanced_menu(
    config_manager: ConfigManager,
    rec_size: str,
) -> None:
    """Show advanced options sub-menu (Whisper legacy backends)."""
    print()
    print("Advanced options:")
    print()
    print("  1. Whisper (local)  \u2014 Legacy backend, CPU-only")
    print("  2. Whisper (API)    \u2014 OpenAI API, needs key, no download")
    print("  3. Back")
    print()

    choice = _prompt("Enter choice [1-3] (default: 3): ", ["1", "2", "3"], "3")

    if choice == "1":
        _whisper_local_menu(config_manager)
    elif choice == "2":
        _whisper_api_menu(config_manager)
    elif choice == "3":
        # Back — apply recommendation
        _save_choices(config_manager, "qwen", rec_size)


def _whisper_local_menu(config_manager: ConfigManager) -> None:
    """Choose local Whisper model size."""
    print()
    print("Choose Whisper model size:")
    print()
    print("  1. tiny       \u2014 ~75 MB,  fastest, least accurate")
    print("  2. base       \u2014 ~150 MB, good balance")
    print("  3. small      \u2014 ~500 MB, better accuracy")
    print("  4. medium     \u2014 ~1.5 GB, high accuracy")
    print("  5. large-v3   \u2014 ~3 GB,   best accuracy")
    print()

    sizes = {"1": "tiny", "2": "base", "3": "small", "4": "medium", "5": "large-v3"}
    choice = _prompt(
        "Enter choice [1-5] (default: 2): ", ["1", "2", "3", "4", "5"], "2"
    )
    _save_choices(config_manager, "local", model_size=sizes.get(choice, "base"))


def _whisper_api_menu(config_manager: ConfigManager) -> None:
    """Prompt for OpenAI API key."""
    print()
    try:
        api_key = input("Enter your OpenAI API key: ").strip()
    except (EOFError, OSError):
        api_key = ""

    if not api_key:
        print("  No API key provided. Falling back to Qwen 0.6B.")
        _save_choices(config_manager, "qwen", "0.6B")
    else:
        _save_choices(config_manager, "api", api_key=api_key)


def _print_confirmation(config_manager: ConfigManager) -> None:
    """Print post-setup confirmation and platform warnings."""
    mode = config_manager.get_transcription_mode()
    print()
    print("\u2550" * 54)

    if mode == "qwen":
        size = config_manager.get_setting("qwen_model_size", "0.6B")
        dl = "~1.9 GB" if size == "0.6B" else "~3.4 GB"
        print(f"  Setup complete! Qwen ASR {size} (GPU) \u2014 {dl} download")
    elif mode == "local":
        size = config_manager.get_local_model_size()
        print(f"  Setup complete! Whisper (local) \u2014 {size}")
    elif mode == "api":
        print("  Setup complete! Whisper (API)")

    print("\u2550" * 54)

    # macOS accessibility warning
    if config_manager.get_platform() == "macos":
        print()
        print("\u2500" * 54)
        print("macOS Setup Required:")
        print("\u2500" * 54)
        print("VoiceBox needs Accessibility permissions to capture")
        print("hotkeys and insert text.")
        print()
        print("1. Open System Settings \u2192 Privacy & Security \u2192 Accessibility")
        print("2. Click the '+' button and add your terminal app")
        print("   (Terminal, iTerm2, VS Code, etc.)")
        print("3. Restart VoiceBox after granting permission")
        print()
        print("Without this, hotkeys will not be detected.")
        print("\u2500" * 54)

    print()
