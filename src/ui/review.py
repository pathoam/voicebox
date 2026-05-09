"""
Correction overlay for editing the last transcription.
"""

from typing import Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


def _create_correction_dialog(original_text: str) -> Optional[str]:
    """
    Show a QDialog for correcting transcription text.
    Returns the corrected text, or None if cancelled.
    """
    try:
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QTextEdit,
            QPushButton, QHBoxLayout, QApplication,
        )
        from PyQt6.QtCore import Qt

        # Ensure QApplication exists
        app = QApplication.instance()
        if app is None:
            return None

        dialog = QDialog()
        dialog.setWindowTitle("VoiceBox - Correct Transcription")
        dialog.setMinimumSize(500, 200)
        dialog.setWindowFlags(
            dialog.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(dialog)

        label = QLabel("Edit the transcription and press Enter or click Apply:")
        layout.addWidget(label)

        text_edit = QTextEdit()
        text_edit.setPlainText(original_text)
        text_edit.setMaximumHeight(100)
        text_edit.selectAll()
        layout.addWidget(text_edit)

        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        result = {"text": None}

        def on_apply():
            result["text"] = text_edit.toPlainText().strip()
            dialog.accept()

        def on_cancel():
            dialog.reject()

        apply_btn.clicked.connect(on_apply)
        cancel_btn.clicked.connect(on_cancel)

        dialog.exec()
        return result["text"]

    except ImportError:
        return None
    except Exception as e:
        logger.error(f"Correction dialog error: {e}")
        return None


def prompt_correction_cli(original_text: str) -> Optional[str]:
    """
    CLI fallback for correction: prompts in terminal.
    Returns corrected text, or None if cancelled.
    """
    try:
        print(f"\n--- Correct Transcription ---")
        print(f"Original: {original_text}")
        corrected = input("Corrected (Enter to keep, Ctrl+C to cancel): ").strip()
        if not corrected:
            return None
        return corrected
    except (KeyboardInterrupt, EOFError):
        print()
        return None


def prompt_correction(original_text: str, use_gui: bool = True) -> Optional[str]:
    """
    Show correction prompt (GUI dialog or CLI).
    Returns corrected text, or None if cancelled/unchanged.
    """
    if use_gui:
        result = _create_correction_dialog(original_text)
        if result is not None:
            return result
        # Fall through to CLI if GUI failed
    return prompt_correction_cli(original_text)
