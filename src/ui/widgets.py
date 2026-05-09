"""Custom widgets for VoiceBox GUI."""

import re
import subprocess
import threading
from typing import Optional

from PyQt6.QtWidgets import QComboBox, QCompleter, QLineEdit, QPushButton
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QStringListModel
from PyQt6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent


class SearchableComboBox(QComboBox):
    """ComboBox with search/filter functionality."""
    
    searchTextChanged = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        
        # Store full model data (id, display_name, price)
        self.model_data = []
        self._updating_data = False  # Flag to prevent search during updates
        
        # Set up completer for autocomplete
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(self.completer)
        
        # Connect signals
        self.lineEdit().textChanged.connect(self.on_text_changed)
        
        # Timer for delayed search (to avoid too many API calls)
        self.search_timer = QTimer()
        self.search_timer.timeout.connect(self.perform_search)
        self.search_timer.setSingleShot(True)
        
    def set_model_data(self, models):
        """
        Set the model data.
        
        Args:
            models: List of (id, display_name, price) tuples
        """
        print(f"Setting model data with {len(models)} models")
        
        # Block signals during update to prevent search triggers
        self._updating_data = True
        old_state = self.blockSignals(True)
        
        self.clear()
        self.model_data = models
        
        # Add all items to combo box
        display_names = []
        for i, (model_id, display_name, price) in enumerate(models):
            self.addItem(display_name, model_id)
            display_names.append(display_name)
            if i < 3:  # Debug first few
                print(f"  Added: {display_name} ({model_id})")
            
        # Update completer model
        model = QStringListModel(display_names)
        self.completer.setModel(model)
        
        # Restore signals
        self.blockSignals(old_state)
        self._updating_data = False
        
        print(f"Combo box now contains {self.count()} items")
        
    def on_text_changed(self, text):
        """Handle text changes with debouncing."""
        # Don't trigger search during data updates
        if self._updating_data:
            return
            
        self.search_timer.stop()
        self.search_timer.start(300)  # 300ms delay
        
    def perform_search(self):
        """Emit search signal."""
        # Don't search during data updates
        if self._updating_data:
            return
            
        text = self.lineEdit().text()
        self.searchTextChanged.emit(text)
        
    def get_current_model_id(self):
        """Get the model ID of current selection or text."""
        current_text = self.currentText()
        
        # First check if it's a selected item
        current_data = self.currentData()
        if current_data:
            return current_data
            
        # Check if the text matches any display name
        for model_id, display_name, price in self.model_data:
            if display_name == current_text:
                return model_id
                
        # Return the text as-is (user might have typed a custom model ID)
        return current_text
        
    def set_model_by_id(self, model_id):
        """Set selection by model ID."""
        for i in range(self.count()):
            if self.itemData(i) == model_id:
                self.setCurrentIndex(i)
                return
                
        # If not found, just set the text
        self.setCurrentText(model_id)
        
    def focusInEvent(self, event: QFocusEvent):
        """Select all text when gaining focus."""
        super().focusInEvent(event)
        self.lineEdit().selectAll()


class HotkeyButton(QPushButton):
    """Button that captures a hotkey when clicked.

    Displays the current hotkey text.  When the user clicks it, it enters
    capture mode and listens for the next key combination or mouse button,
    then emits ``hotkeyChanged`` with the normalized string.
    """

    hotkeyChanged = pyqtSignal(str)

    # Map Qt modifier flags to short names
    _MOD_MAP = [
        (Qt.KeyboardModifier.ControlModifier, "ctrl"),
        (Qt.KeyboardModifier.AltModifier, "alt"),
        (Qt.KeyboardModifier.ShiftModifier, "shift"),
        (Qt.KeyboardModifier.MetaModifier, "super"),
    ]

    # Map Qt key codes to readable names
    _KEY_NAMES = {
        Qt.Key.Key_Space: "space",
        Qt.Key.Key_Return: "enter",
        Qt.Key.Key_Enter: "enter",
        Qt.Key.Key_Tab: "tab",
        Qt.Key.Key_Escape: "escape",
        Qt.Key.Key_Backspace: "backspace",
        Qt.Key.Key_Delete: "delete",
        Qt.Key.Key_Up: "up",
        Qt.Key.Key_Down: "down",
        Qt.Key.Key_Left: "left",
        Qt.Key.Key_Right: "right",
        Qt.Key.Key_ScrollLock: "scroll_lock",
        Qt.Key.Key_Pause: "pause",
        Qt.Key.Key_Insert: "insert",
        Qt.Key.Key_Home: "home",
        Qt.Key.Key_End: "end",
        Qt.Key.Key_PageUp: "page_up",
        Qt.Key.Key_PageDown: "page_down",
    }

    def __init__(self, hotkey: str = "", parent=None):
        super().__init__(parent)
        self._hotkey = hotkey
        self._capturing = False
        self._held_modifiers: list[str] = []
        self._update_display()
        self.clicked.connect(self._start_capture)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # xinput-based mouse button listener
        self._xinput_procs: list[subprocess.Popen] = []
        self._xinput_stop = threading.Event()

    def hotkey(self) -> str:
        """Return the current hotkey string."""
        return self._hotkey

    def setHotkey(self, hotkey: str) -> None:
        """Set the hotkey string and update the display."""
        self._hotkey = hotkey
        if not self._capturing:
            self._update_display()

    def _update_display(self) -> None:
        if self._capturing:
            self.setText("Press a key or mouse button...")
            self.setStyleSheet("QPushButton { background-color: #553333; border: 2px solid #ff6666; }")
        else:
            self.setText(self._hotkey or "(none)")
            self.setStyleSheet("")

    def _start_capture(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._held_modifiers = []
        self._update_display()
        self.grabKeyboard()
        # Start xinput-based mouse button listener on all pointer devices
        self._xinput_stop.clear()
        self._xinput_procs = []
        try:
            self._start_xinput_listeners()
        except Exception:
            pass

    def _finish_capture(self, hotkey: str) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self.releaseKeyboard()
        self._stop_xinput_listeners()
        self._hotkey = hotkey
        self._update_display()
        self.hotkeyChanged.emit(hotkey)

    def _cancel_capture(self) -> None:
        self._capturing = False
        self.releaseKeyboard()
        self._stop_xinput_listeners()
        self._update_display()

    def _start_xinput_listeners(self) -> None:
        """Spawn xinput test processes on all pointer devices to detect side buttons."""
        out = subprocess.check_output(["xinput", "list", "--short"], text=True)
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
        """Read xinput output and detect side button presses."""
        try:
            for line in proc.stdout:
                if self._xinput_stop.is_set():
                    break
                m = re.match(r"button press\s+(\d+)", line.strip())
                if m:
                    btn = int(m.group(1))
                    if btn >= 8:  # skip left/right/middle/scroll (1-7)
                        hotkey = f"button{btn}"
                        QTimer.singleShot(0, lambda h=hotkey: self._finish_capture(h))
                        break
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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Escape cancels capture
        if key == Qt.Key.Key_Escape:
            self._cancel_capture()
            return

        # Pure modifier press — just track it, don't finish yet
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            return

        # Build the hotkey string
        parts = []
        modifiers = event.modifiers()
        for flag, name in self._MOD_MAP:
            if modifiers & flag:
                parts.append(name)

        # Resolve the key name
        if key in self._KEY_NAMES:
            parts.append(self._KEY_NAMES[key])
        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35:
            parts.append(f"f{key - Qt.Key.Key_F1 + 1}")
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            parts.append(chr(key).lower())
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            parts.append(chr(key))
        else:
            text = event.text()
            if text and text.isprintable():
                parts.append(text.lower())
            else:
                # Unknown key, ignore
                return

        hotkey = "+".join(parts)
        self._finish_capture(hotkey)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if not self._capturing:
            super().keyReleaseEvent(event)
            return
        # Swallow key releases during capture
        event.accept()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        if self._capturing:
            self._cancel_capture()
        super().focusOutEvent(event)