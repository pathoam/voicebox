"""
Singleton instance management for VoiceBox.

Ensures only one instance of VoiceBox can run at a time using a PID lock file.
"""

import os
import sys
import signal
import atexit
from pathlib import Path
from typing import Optional


class SingletonInstance:
    """Manages single-instance enforcement using a PID lock file."""

    def __init__(self, app_name: str = "voicebox"):
        self.app_name = app_name
        self.lock_file = self._get_lock_file_path()
        self._lock_acquired = False

    def _get_lock_file_path(self) -> Path:
        """Get platform-appropriate lock file path."""
        if sys.platform == "win32":
            # Windows: use temp directory
            base_dir = Path(os.environ.get("TEMP", os.path.expanduser("~")))
        else:
            # Unix: use /tmp or XDG_RUNTIME_DIR
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            if runtime_dir:
                base_dir = Path(runtime_dir)
            else:
                base_dir = Path("/tmp")

        return base_dir / f"{self.app_name}.lock"

    def _read_lock_file(self) -> Optional[int]:
        """Read PID from lock file. Returns None if file doesn't exist or is invalid."""
        try:
            if self.lock_file.exists():
                content = self.lock_file.read_text().strip()
                return int(content)
        except (ValueError, OSError):
            pass
        return None

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with the given PID is running."""
        if pid <= 0:
            return False

        try:
            if sys.platform == "win32":
                # Windows: use ctypes or subprocess
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                # Unix: send signal 0 to check if process exists
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError, PermissionError):
            return False

    def _write_lock_file(self) -> bool:
        """Write current PID to lock file."""
        try:
            self.lock_file.write_text(str(os.getpid()))
            return True
        except OSError:
            return False

    def _remove_lock_file(self) -> None:
        """Remove the lock file."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except OSError:
            pass

    def acquire(self) -> bool:
        """
        Try to acquire the singleton lock.

        Returns:
            True if lock acquired (we're the only instance),
            False if another instance is running.
        """
        existing_pid = self._read_lock_file()

        if existing_pid is not None:
            if self._is_process_running(existing_pid):
                # Another instance is actually running
                return False
            else:
                # Stale lock file from crashed instance - remove it
                self._remove_lock_file()

        # Write our PID to the lock file
        if self._write_lock_file():
            self._lock_acquired = True
            # Register cleanup on exit
            atexit.register(self._remove_lock_file)
            return True

        return False

    def release(self) -> None:
        """Release the singleton lock."""
        if self._lock_acquired:
            self._remove_lock_file()
            self._lock_acquired = False

    def get_existing_pid(self) -> Optional[int]:
        """Get the PID of an existing instance, if any."""
        existing_pid = self._read_lock_file()
        if existing_pid and self._is_process_running(existing_pid):
            return existing_pid
        return None

    def kill_existing(self) -> bool:
        """
        Kill an existing instance if one is running.

        Returns:
            True if an instance was killed, False otherwise.
        """
        existing_pid = self.get_existing_pid()
        if existing_pid is None:
            return False

        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.run(["taskkill", "/PID", str(existing_pid), "/F"],
                             capture_output=True)
            else:
                os.kill(existing_pid, signal.SIGTERM)
                # Give it a moment to clean up
                import time
                time.sleep(0.5)
                # Force kill if still running
                if self._is_process_running(existing_pid):
                    os.kill(existing_pid, signal.SIGKILL)

            # Remove the stale lock file
            self._remove_lock_file()
            return True

        except (OSError, ProcessLookupError, PermissionError):
            return False


def ensure_single_instance(kill_existing: bool = True) -> bool:
    """
    Ensure only one instance of VoiceBox is running.

    Args:
        kill_existing: If True, kill any existing instance. If False, just exit.

    Returns:
        True if we can proceed (either no other instance, or we killed it).
        False if another instance is running and we couldn't/didn't kill it.
    """
    singleton = SingletonInstance()

    if singleton.acquire():
        return True

    # Another instance is running
    existing_pid = singleton.get_existing_pid()

    if kill_existing and existing_pid:
        print(f"Another VoiceBox instance is running (PID {existing_pid}). Stopping it...")
        if singleton.kill_existing():
            print("Previous instance stopped.")
            # Try to acquire again
            import time
            time.sleep(0.2)
            if singleton.acquire():
                return True

    print(f"VoiceBox is already running (PID {existing_pid}).")
    print("Use --force to replace the existing instance.")
    return False
