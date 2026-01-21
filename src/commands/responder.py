"""Response display mechanisms for command outputs."""

import sys
import platform
import subprocess
from typing import Dict, Any, Optional
import pyperclip

from src.utils.logging import get_logger


class CommandResponder:
    """Handles displaying command responses to the user."""

    def __init__(
        self, method: str = "notification", gui_callback: Optional[callable] = None
    ):
        """
        Initialize responder.

        Args:
            method: Response display method ("notification", "clipboard", "console")
            gui_callback: Optional GUI callback for displaying responses
        """
        self.method = method
        self.gui_callback = gui_callback
        self.platform = platform.system().lower()
        self.logger = get_logger(__name__)

    def display_response(self, response: Dict[str, Any]):
        """
        Display command response to user.

        Args:
            response: Response dict with 'success', 'response'/'error'
        """
        if not response.get("success"):
            message = f"❌ Command failed: {response.get('error', 'Unknown error')}"
        else:
            message = response.get("response", "No response")

        # Route to appropriate display method
        if self.method == "notification":
            self._show_notification(message)
        elif self.method == "clipboard":
            self._copy_to_clipboard(message)
        elif self.method == "console":
            self._print_to_console(message)
        else:
            # Default to console
            self._print_to_console(message)

        # Also send to GUI if callback is set
        if self.gui_callback:
            self.gui_callback(message)

    def _show_notification(self, message: str):
        """Show system notification."""
        title = "VoiceBox Command"

        # Truncate long messages for notifications
        if len(message) > 200:
            message = message[:197] + "..."

        try:
            if self.platform == "darwin":  # macOS
                # Use osascript for macOS notifications
                script = f'display notification "{self._escape_quotes(message)}" with title "{title}"'
                subprocess.run(
                    ["osascript", "-e", script], check=False, capture_output=True
                )

            elif self.platform == "linux":
                # Try notify-send for Linux
                subprocess.run(
                    ["notify-send", title, message], check=False, capture_output=True
                )

            elif self.platform == "windows":
                # Use plyer for Windows (would need to add to dependencies)
                # For now, fall back to console
                self._show_windows_notification(title, message)

        except Exception as e:
            # Fall back to console if notification fails
            self.logger.error(f"Notification failed: {e}")
            self._print_to_console(message)

    def _show_windows_notification(self, title: str, message: str):
        """Show Windows notification using win10toast or fallback."""
        try:
            # Try using Windows 10 toast notifications
            from win10toast import ToastNotifier  # type: ignore

            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=10, threaded=True)
        except ImportError:
            # Fall back to console
            self._print_to_console(f"{title}: {message}")

    def _copy_to_clipboard(self, message: str):
        """Copy response to clipboard."""
        try:
            pyperclip.copy(message)
            print("✅ Response copied to clipboard")

            # Also show a brief preview in console
            preview = message[:100] + "..." if len(message) > 100 else message
            print(f"Preview: {preview}")

        except Exception as e:
            print(f"Failed to copy to clipboard: {e}")
            self._print_to_console(message)

    def _print_to_console(self, message: str):
        """Print response to console."""
        print("\n" + "=" * 50)
        print("🤖 Command Response:")
        print("-" * 50)
        print(message)
        print("=" * 50 + "\n")

    def _escape_quotes(self, text: str) -> str:
        """Escape quotes for shell commands."""
        return text.replace('"', '\\"').replace("'", "\\'")

    def set_method(self, method: str):
        """Change response display method."""
        self.method = method

    def set_gui_callback(self, callback: callable):
        """Set GUI callback for responses."""
        self.gui_callback = callback
