"""Cross-platform desktop notifications."""

import platform
import subprocess

from src.utils.logging import get_logger

logger = get_logger(__name__)


def notify(title: str, message: str, duration_ms: int = 3000) -> None:
    """Show a desktop toast notification.

    Args:
        title: Notification title.
        message: Notification body.
        duration_ms: Display duration in milliseconds (Linux only).
    """
    system = platform.system().lower()
    try:
        if system == "linux":
            subprocess.run(
                ["notify-send", "-t", str(duration_ms), title, message],
                check=False,
                capture_output=True,
            )
        elif system == "darwin":
            escaped_msg = message.replace("\\", "\\\\").replace('"', '\\"')
            escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
            script = f'display notification "{escaped_msg}" with title "{escaped_title}"'
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
            )
        else:
            print(f"[{title}] {message}")
    except Exception as e:
        logger.debug(f"Notification failed: {e}")
        print(f"[{title}] {message}")
