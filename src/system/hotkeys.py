import re
import subprocess
from typing import Callable, Optional, Union
from pynput import keyboard
import threading
from src.utils.logging import get_logger


class HotkeyManager:
    """Cross-platform global hotkey manager supporting keyboard and mouse inputs."""

    def __init__(self, callback: Callable[[], None]):
        """
        Initialize hotkey manager.

        Args:
            callback: Function to call when hotkey is pressed
        """
        self.callback = callback
        self.current_hotkey: Optional[str] = None
        self.keyboard_listener: Optional[keyboard.GlobalHotKeys] = None
        self._xinput_procs: list[subprocess.Popen] = []
        self._xinput_stop = threading.Event()
        self.is_listening = False
        self._lock = threading.Lock()
        self._is_mouse_hotkey = False
        self._extra_hotkeys: dict = {}  # key_combination -> callback
        self.logger = get_logger(__name__)

    def set_hotkey(self, key_combination: str) -> None:
        """
        Set the hotkey combination.

        Args:
            key_combination: Hotkey string like 'ctrl+shift+v', 'f12', or 'button9'
        """
        # Stop outside the lock to avoid deadlock (stop_listening also acquires _lock)
        if self.is_listening:
            self.stop_listening()

        with self._lock:
            self.current_hotkey = key_combination
            self._is_mouse_hotkey = self._is_mouse_button(key_combination)

            try:
                if self._is_mouse_hotkey:
                    # Set up mouse listener
                    self._setup_mouse_listener(key_combination)
                else:
                    # Set up keyboard listener
                    self._setup_keyboard_listener(key_combination)

            except Exception as e:
                raise ValueError(f"Invalid hotkey combination '{key_combination}': {e}")

    def start_listening(self) -> None:
        """Start listening for hotkey presses."""
        with self._lock:
            if self.is_listening:
                return

            if not (self.keyboard_listener or self._is_mouse_hotkey):
                raise RuntimeError("No hotkey set. Call set_hotkey() first.")

            try:
                if self._is_mouse_hotkey:
                    self._start_xinput_listeners()
                elif self.keyboard_listener:
                    self.keyboard_listener.start()

                self.is_listening = True

            except Exception as e:
                raise RuntimeError(f"Failed to start hotkey listener: {e}")

    def stop_listening(self) -> None:
        """Stop listening for hotkey presses."""
        with self._lock:
            if not self.is_listening:
                return

            try:
                if self.keyboard_listener:
                    self.keyboard_listener.stop()
                    self.keyboard_listener = None
                self._stop_xinput_listeners()
            except Exception as e:
                self.logger.error(f"Error stopping listener: {e}")

        self.is_listening = False

    def _on_hotkey_pressed(self) -> None:
        """Internal callback when hotkey is pressed."""
        try:
            self.callback()
        except Exception as e:
            self.logger.error(f"Error in hotkey callback: {e}")

    def _normalize_hotkey(self, key_combination: str) -> str:
        """
        Normalize hotkey string for pynput.

        Args:
            key_combination: Input like 'ctrl+shift+v'

        Returns:
            Normalized string for pynput
        """
        # Convert to lowercase and split
        parts = key_combination.lower().replace(" ", "").split("+")

        # Map common key names to pynput format
        key_mapping = {
            "ctrl": "<ctrl>",
            "control": "<ctrl>",
            "shift": "<shift>",
            "alt": "<alt>",
            "option": "<alt>",  # macOS
            "cmd": "<cmd>",  # macOS
            "command": "<cmd>",  # macOS
            "win": "<cmd>",  # Windows key
            "super": "<cmd>",  # Linux super key
            "space": "<space>",
            "enter": "<enter>",
            "return": "<enter>",
            "tab": "<tab>",
            "esc": "<esc>",
            "escape": "<esc>",
            "backspace": "<backspace>",
            "delete": "<delete>",
            "up": "<up>",
            "down": "<down>",
            "left": "<left>",
            "right": "<right>",
        }

        # Process each part
        normalized_parts = []
        for part in parts:
            if part in key_mapping:
                normalized_parts.append(key_mapping[part])
            elif len(part) == 1 and part.isalpha():
                # Single letter - keep as is
                normalized_parts.append(part)
            elif part.startswith("f") and part[1:].isdigit():
                # Function keys like f1, f12
                normalized_parts.append(f"<{part}>")
            else:
                # Try to keep as is, pynput might understand it
                normalized_parts.append(part)

        return "+".join(normalized_parts)

    def is_hotkey_listening(self) -> bool:
        """Check if currently listening for hotkeys."""
        return self.is_listening

    def get_current_hotkey(self) -> Optional[str]:
        """Get the current hotkey combination."""
        return self.current_hotkey

    def _is_mouse_button(self, key_combination: str) -> bool:
        """Check if the hotkey is a mouse button."""
        return key_combination.startswith("button") and key_combination[6:].isdigit()

    def register_hotkey(self, key_combination: str, callback: Callable[[], None]) -> None:
        """
        Register an additional hotkey with its own callback.
        Must be called before start_listening() or will require restart.

        Args:
            key_combination: Hotkey string like 'ctrl+alt+space'
            callback: Function to call when this hotkey is pressed
        """
        self._extra_hotkeys[key_combination] = callback

    def _setup_keyboard_listener(self, key_combination: str) -> None:
        """Set up keyboard listener for keyboard hotkeys."""
        normalized_hotkey = self._normalize_hotkey(key_combination)
        hotkey_dict = {normalized_hotkey: self._on_hotkey_pressed}

        # Add extra registered hotkeys
        for combo, cb in self._extra_hotkeys.items():
            if not self._is_mouse_button(combo):
                normalized = self._normalize_hotkey(combo)
                hotkey_dict[normalized] = cb

        self.keyboard_listener = keyboard.GlobalHotKeys(hotkey_dict)

    def _setup_mouse_listener(self, key_combination: str) -> None:
        """Validate mouse button hotkey format. Actual listeners start in start_listening()."""
        button_num = int(key_combination[6:])
        if button_num < 8:
            raise ValueError(f"Mouse buttons below 8 are not supported as hotkeys (got {button_num})")
        self._target_button_num = button_num

    def _start_xinput_listeners(self) -> None:
        """Spawn xinput test processes on all pointer devices to detect the target button."""
        self._xinput_stop.clear()
        self._xinput_procs = []
        try:
            out = subprocess.check_output(["xinput", "list", "--short"], text=True)
        except FileNotFoundError:
            self.logger.error("xinput not found — mouse button hotkeys require xinput")
            return
        for line in out.splitlines():
            if "slave  pointer" not in line or "Virtual" in line or "XTEST" in line:
                continue
            m = re.search(r"id=(\d+)", line)
            if not m:
                continue
            dev_id = m.group(1)
            proc = subprocess.Popen(
                ["xinput", "test", dev_id],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
            self._xinput_procs.append(proc)
            t = threading.Thread(
                target=self._read_xinput, args=(proc,), daemon=True
            )
            t.start()

    def _read_xinput(self, proc: subprocess.Popen) -> None:
        """Read xinput output and fire callback on target button press."""
        try:
            for line in proc.stdout:
                if self._xinput_stop.is_set():
                    break
                m = re.match(r"button press\s+(\d+)", line.strip())
                if m and int(m.group(1)) == self._target_button_num:
                    self._on_hotkey_pressed()
        except Exception:
            pass

    def _stop_xinput_listeners(self) -> None:
        """Terminate all xinput test processes."""
        self._xinput_stop.set()
        for proc in self._xinput_procs:
            try:
                proc.terminate()
            except Exception:
                pass
        self._xinput_procs = []

    @staticmethod
    def get_suggested_hotkeys() -> list:
        """Get a list of suggested hotkey combinations that rarely conflict."""
        return [
            "f12",  # Function keys rarely used by apps
            "f11",  # Another safe function key
            "button9",  # Mouse side button (forward)
            "button8",  # Mouse side button (back)
            "ctrl+f12",  # Modified function keys
            "alt+f12",  # Even safer with modifier
            "shift+f12",  # Alternative modifier
            "ctrl+alt+q",  # Uncommon combination
        ]
