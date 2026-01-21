#!/usr/bin/env python3

import sys
import threading
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QCheckBox,
    QTextEdit,
    QSystemTrayIcon,
    QMenu,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
    QTabWidget,
    QProgressBar,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QAction

from src.main import VoiceBoxApp
from src.config.manager import ConfigManager
from src.ui.widgets import SearchableComboBox
from src.commands.openrouter_models import OpenRouterModels


class VoiceBoxWorker(QThread):
    """Worker thread for VoiceBox operations."""

    status_changed = pyqtSignal(str)
    transcription_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str, str)  # (message, error_type, suggestion)

    def __init__(self, app: VoiceBoxApp):
        super().__init__()
        self.voicebox_app = app
        self.running = False

        # Connect callbacks
        self.voicebox_app.on_transcription_complete = self._on_transcription
        self.voicebox_app.on_status_change = self._on_status_change
        self.voicebox_app.on_error = self._on_error

    def _on_transcription(self, text: str):
        """Handle transcription completion."""
        self.transcription_complete.emit(text)

    def _on_status_change(self, status: str):
        """Handle status change."""
        self.status_changed.emit(status)

    def _on_error(self, message: str, error_type: str, suggestion: str):
        """Forward error to GUI thread."""
        self.error_occurred.emit(message, error_type, suggestion)

    def run(self):
        """Run VoiceBox in background thread."""
        self.running = True

        # Start VoiceBox
        if not self.voicebox_app.start():
            self.error_occurred.emit("Failed to start VoiceBox")
            return

        self.status_changed.emit("Ready")

        # Keep thread alive while app is running
        while self.running and self.voicebox_app._running:
            self.msleep(100)

    def stop(self):
        """Stop the worker thread."""
        self.running = False
        self.voicebox_app.stop()


class SettingsWindow(QMainWindow):
    """Settings configuration window."""

    def __init__(self, config_manager: ConfigManager, voicebox_app=None):
        super().__init__()
        self.config_manager = config_manager
        self.voicebox_app = voicebox_app  # Reference to running VoiceBox instance
        self.model_fetcher = OpenRouterModels()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the settings UI."""
        self.setWindowTitle("VoiceBox Settings")
        self.setFixedSize(700, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.create_general_tab()
        self.create_command_tab()
        self.create_substitutions_tab()

        # Connect tab change signal to start model fetching
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # Buttons
        button_layout = QHBoxLayout()

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)

        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def create_general_tab(self):
        """Create the general settings tab."""
        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)

        # Transcription settings
        transcription_group = QGroupBox("Transcription")
        transcription_layout = QFormLayout(transcription_group)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["local", "api"])
        transcription_layout.addRow("Mode:", self.mode_combo)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        transcription_layout.addRow("API Key:", self.api_key_edit)

        self.model_combo = QComboBox()
        self.model_combo.addItems(
            ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
        )
        transcription_layout.addRow("Local Model:", self.model_combo)

        self.language_combo = QComboBox()
        languages = [
            ("auto", "Auto-detect"),
            ("en", "English"),
            ("es", "Spanish"),
            ("fr", "French"),
            ("de", "German"),
            ("it", "Italian"),
            ("pt", "Portuguese"),
            ("ru", "Russian"),
            ("ja", "Japanese"),
            ("ko", "Korean"),
            ("zh", "Chinese"),
            ("ar", "Arabic"),
            ("hi", "Hindi"),
            ("tr", "Turkish"),
            ("nl", "Dutch"),
            ("sv", "Swedish"),
            ("da", "Danish"),
            ("no", "Norwegian"),
            ("fi", "Finnish"),
            ("pl", "Polish"),
        ]
        for code, name in languages:
            self.language_combo.addItem(name, code)
        transcription_layout.addRow("Language:", self.language_combo)

        layout.addWidget(transcription_group)

        # Hotkey settings
        hotkey_group = QGroupBox("Hotkey")
        hotkey_layout = QFormLayout(hotkey_group)

        self.hotkey_edit = QLineEdit()
        hotkey_layout.addRow("Hotkey:", self.hotkey_edit)

        layout.addWidget(hotkey_group)

        # Text insertion settings
        insertion_group = QGroupBox("Text Insertion")
        insertion_layout = QFormLayout(insertion_group)

        self.insertion_combo = QComboBox()
        self.insertion_combo.addItems(["auto", "clipboard", "typing"])
        insertion_layout.addRow("Method:", self.insertion_combo)

        layout.addWidget(insertion_group)

        # Audio settings
        audio_group = QGroupBox("Audio")
        audio_layout = QFormLayout(audio_group)

        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setRange(8000, 48000)
        self.sample_rate_spin.setValue(16000)
        audio_layout.addRow("Sample Rate:", self.sample_rate_spin)

        self.channels_spin = QSpinBox()
        self.channels_spin.setRange(1, 2)
        self.channels_spin.setValue(1)
        audio_layout.addRow("Channels:", self.channels_spin)

        layout.addWidget(audio_group)

        self.tab_widget.addTab(general_tab, "General")

    def create_command_tab(self):
        """Create the command mode settings tab."""
        command_tab = QWidget()
        layout = QVBoxLayout(command_tab)

        # Enable/disable command mode
        self.command_enabled_check = QCheckBox("Enable Command Mode")
        self.command_enabled_check.setToolTip(
            "Enable voice commands with trigger words"
        )
        self.command_enabled_check.stateChanged.connect(self.on_command_mode_toggled)
        layout.addWidget(self.command_enabled_check)

        # Command settings group
        self.command_group = QGroupBox("Command Settings")
        command_layout = QFormLayout(self.command_group)

        # Trigger words
        trigger_label = QLabel("Trigger Words (comma-separated):")
        self.triggers_edit = QLineEdit()
        self.triggers_edit.setPlaceholderText("voicebox, assistant, computer")
        self.triggers_edit.setToolTip("Words that activate command mode")
        command_layout.addRow(trigger_label, self.triggers_edit)

        # Response method
        self.response_method_combo = QComboBox()
        self.response_method_combo.addItems(["notification", "clipboard", "console"])
        self.response_method_combo.setToolTip("How command responses are displayed")
        command_layout.addRow("Response Method:", self.response_method_combo)

        layout.addWidget(self.command_group)

        # LLM Configuration group
        llm_group = QGroupBox("LLM Configuration")
        llm_layout = QFormLayout(llm_group)

        # OpenRouter settings
        openrouter_label = QLabel("<b>OpenRouter API</b>")
        llm_layout.addRow(openrouter_label, QLabel())

        self.openrouter_key_edit = QLineEdit()
        self.openrouter_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.openrouter_key_edit.setPlaceholderText("sk-or-v1-...")
        self.openrouter_key_edit.setToolTip("Get key from openrouter.ai")
        llm_layout.addRow("API Key:", self.openrouter_key_edit)

        # Model selection with refresh button
        model_layout = QHBoxLayout()
        self.openrouter_model_combo = SearchableComboBox()
        self.openrouter_model_combo.setToolTip("Select or search for OpenRouter models")

        self.refresh_models_btn = QPushButton("🔄")
        self.refresh_models_btn.setFixedSize(30, 30)
        self.refresh_models_btn.setToolTip("Refresh model list from OpenRouter")
        self.refresh_models_btn.clicked.connect(self.refresh_models)

        model_layout.addWidget(self.openrouter_model_combo)
        model_layout.addWidget(self.refresh_models_btn)

        model_widget = QWidget()
        model_widget.setLayout(model_layout)
        llm_layout.addRow("Model:", model_widget)

        # Connect search functionality (but it will be disabled during data updates)
        self.openrouter_model_combo.searchTextChanged.connect(self.search_models)

        # Local LLM settings
        local_label = QLabel("<b>Local LLM (vLLM/Ollama)</b>")
        llm_layout.addRow(local_label, QLabel())

        self.local_endpoint_edit = QLineEdit()
        self.local_endpoint_edit.setPlaceholderText("http://localhost:8000")
        self.local_endpoint_edit.setToolTip("Endpoint for local LLM server")
        llm_layout.addRow("Endpoint:", self.local_endpoint_edit)

        layout.addWidget(llm_group)

        # Info text
        info_text = QLabel(
            "<i>Command mode allows you to speak commands starting with trigger words.<br>"
            'Example: "voicebox, create a shell script to delete all PNGs"<br>'
            "Configure either OpenRouter API or a local LLM endpoint.</i>"
        )
        info_text.setWordWrap(True)
        layout.addWidget(info_text)

        layout.addStretch()

        self.tab_widget.addTab(command_tab, "Commands")

        # Set initial enabled state
        self.on_command_mode_toggled()

    def on_command_mode_toggled(self):
        """Handle command mode checkbox toggle."""
        enabled = self.command_enabled_check.isChecked()
        self.command_group.setEnabled(enabled)

        # Load models when command mode is first enabled
        if enabled and self.openrouter_model_combo.count() == 0:
            self.start_model_fetching()

    def on_tab_changed(self, index):
        """Handle tab changes to start model fetching."""
        # Check if this is the Commands tab
        if self.tab_widget.tabText(index) == "Commands":
            # Start fetching models if not already done
            if self.openrouter_model_combo.count() == 0:
                self.start_model_fetching()

    def start_model_fetching(self):
        """Start fetching models from OpenRouter API."""
        # Show loading state
        self.openrouter_model_combo.clear()
        self.openrouter_model_combo.addItem("Loading models...", "")
        self.openrouter_model_combo.setEnabled(False)

        # Update API key if provided
        api_key = self.openrouter_key_edit.text().strip()
        if api_key:
            self.model_fetcher.api_key = api_key

        # Start the fetch in background
        QTimer.singleShot(100, self.fetch_models_background)

    def fetch_models_background(self):
        """Fetch models in background thread."""
        try:
            # First try to get cached models (fast)
            models = self.model_fetcher.get_model_list(force_refresh=False)

            if models:
                # Update UI immediately with cached models
                self.openrouter_model_combo.clear()
                self.openrouter_model_combo.set_model_data(models)
                self.openrouter_model_combo.setEnabled(True)

                # Set the pending model if we have one
                if hasattr(self, "pending_model_id") and self.pending_model_id:
                    self.openrouter_model_combo.set_model_by_id(self.pending_model_id)
                    pass  # Model set from cache

            # Then refresh from API in background (if cache is old)
            # This will update the persistent cache for next time
            try:
                fresh_models = self.model_fetcher.get_model_list(force_refresh=True)
                if fresh_models and len(fresh_models) != len(models):
                    # Only update UI if the list changed
                    current_selection = (
                        self.openrouter_model_combo.get_selected_model_id()
                    )
                    self.openrouter_model_combo.clear()
                    self.openrouter_model_combo.set_model_data(fresh_models)
                    if current_selection:
                        self.openrouter_model_combo.set_model_by_id(current_selection)
            except Exception as e:
                # Silent refresh failure is OK if we have cached models
                pass

        except Exception:
            # Show error state instead of placeholders
            self.openrouter_model_combo.clear()
            self.openrouter_model_combo.addItem(
                "Failed to load models - click refresh", ""
            )
            self.openrouter_model_combo.setEnabled(True)

            # If we have a pending model ID, at least show that as an option
            if hasattr(self, "pending_model_id") and self.pending_model_id:
                self.openrouter_model_combo.addItem(
                    f"Custom: {self.pending_model_id}", self.pending_model_id
                )
                self.openrouter_model_combo.setCurrentIndex(
                    1
                )  # Select the custom model

    def refresh_models(self):
        """Refresh model list from OpenRouter API."""
        print("Refresh button clicked")
        self.refresh_models_btn.setEnabled(False)
        self.refresh_models_btn.setText("...")

        # Update API key in model fetcher
        api_key = self.openrouter_key_edit.text().strip()
        if api_key:
            self.model_fetcher.api_key = api_key
            print(f"Using API key: {api_key[:10]}...")
        else:
            print("No API key provided")

        try:
            # Force refresh from API
            print("Calling get_model_list with force_refresh=True")
            models = self.model_fetcher.get_model_list(force_refresh=True)
            print(f"Refresh got {len(models)} models")

            self.openrouter_model_combo.set_model_data(models)

            # Show success message
            self.refresh_models_btn.setText("✅")
            QTimer.singleShot(2000, lambda: self.refresh_models_btn.setText("🔄"))

        except Exception as e:
            print(f"Failed to refresh models: {e}")
            import traceback

            traceback.print_exc()
            self.refresh_models_btn.setText("❌")
            QTimer.singleShot(2000, lambda: self.refresh_models_btn.setText("🔄"))

        finally:
            self.refresh_models_btn.setEnabled(True)

    def search_models(self, query):
        """Filter models based on search query."""
        try:
            # Don't search if query is empty or just whitespace
            if not query or not query.strip():
                print("Empty search query, ignoring")
                return

            print(f"Searching models for: '{query}'")
            filtered_models = self.model_fetcher.search_models(query)
            print(f"Search returned {len(filtered_models)} models")
            self.openrouter_model_combo.set_model_data(filtered_models)
        except Exception as e:
            print(f"Search failed: {e}")

    def create_substitutions_tab(self):
        """Create the text substitutions tab."""
        subs_tab = QWidget()
        layout = QVBoxLayout(subs_tab)

        # Header
        header_label = QLabel("Text Substitutions")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)

        desc_label = QLabel(
            "Define replacements for commonly misheard technical terms:"
        )
        layout.addWidget(desc_label)

        # Table for substitutions
        self.substitutions_table = QTableWidget()
        self.substitutions_table.setColumnCount(2)
        self.substitutions_table.setHorizontalHeaderLabels(
            ["Misheard Text", "Correct Text"]
        )
        self.substitutions_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.substitutions_table)

        # Buttons for managing substitutions
        subs_button_layout = QHBoxLayout()

        self.add_sub_button = QPushButton("Add")
        self.add_sub_button.clicked.connect(self.add_substitution)

        self.remove_sub_button = QPushButton("Remove Selected")
        self.remove_sub_button.clicked.connect(self.remove_substitution)

        self.import_sub_button = QPushButton("Import...")
        self.import_sub_button.clicked.connect(self.import_substitutions)

        self.export_sub_button = QPushButton("Export...")
        self.export_sub_button.clicked.connect(self.export_substitutions)

        self.reset_sub_button = QPushButton("Reset to Defaults")
        self.reset_sub_button.clicked.connect(self.reset_substitutions)

        subs_button_layout.addWidget(self.add_sub_button)
        subs_button_layout.addWidget(self.remove_sub_button)
        subs_button_layout.addStretch()
        subs_button_layout.addWidget(self.import_sub_button)
        subs_button_layout.addWidget(self.export_sub_button)
        subs_button_layout.addWidget(self.reset_sub_button)

        layout.addLayout(subs_button_layout)

        self.tab_widget.addTab(subs_tab, "Substitutions")

    def load_settings(self):
        """Load current settings into the UI."""
        self.mode_combo.setCurrentText(self.config_manager.get_transcription_mode())
        self.api_key_edit.setText(self.config_manager.get_api_key() or "")
        self.model_combo.setCurrentText(self.config_manager.get_local_model_size())

        # Set language combo
        current_language = self.config_manager.get_transcription_language()
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == current_language:
                self.language_combo.setCurrentIndex(i)
                break

        self.hotkey_edit.setText(self.config_manager.get_hotkey())
        self.insertion_combo.setCurrentText(
            self.config_manager.get_text_insertion_method()
        )
        self.sample_rate_spin.setValue(self.config_manager.get_audio_sample_rate())
        self.channels_spin.setValue(self.config_manager.get_audio_channels())

        # Load command mode settings
        cmd_config = self.config_manager.get_command_mode_config()
        self.command_enabled_check.setChecked(cmd_config.get("enabled", False))
        self.triggers_edit.setText(", ".join(cmd_config.get("triggers", ["voicebox"])))
        self.response_method_combo.setCurrentText(
            cmd_config.get("response_method", "notification")
        )
        self.openrouter_key_edit.setText(cmd_config.get("openrouter_api_key", ""))

        # Set model combo box - store the model ID for later setting
        self.pending_model_id = cmd_config.get(
            "openrouter_model", "meta-llama/llama-3.2-3b-instruct:free"
        )

        # If models are already loaded, set it now
        if self.openrouter_model_combo.count() > 0:
            self.openrouter_model_combo.set_model_by_id(self.pending_model_id)

        self.local_endpoint_edit.setText(cmd_config.get("local_llm_endpoint", ""))

        # Load substitutions
        self.load_substitutions_table()

    def save_settings(self):
        """Save settings and close window."""
        self.config_manager.set_setting(
            "transcription_mode", self.mode_combo.currentText()
        )
        self.config_manager.set_setting("api_key", self.api_key_edit.text())
        self.config_manager.set_setting(
            "local_model_size", self.model_combo.currentText()
        )
        self.config_manager.set_setting(
            "transcription_language", self.language_combo.currentData()
        )
        self.config_manager.set_setting("hotkey", self.hotkey_edit.text())
        self.config_manager.set_setting(
            "text_insertion_method", self.insertion_combo.currentText()
        )
        self.config_manager.set_setting(
            "audio_sample_rate", self.sample_rate_spin.value()
        )
        self.config_manager.set_setting("audio_channels", self.channels_spin.value())

        # Save command mode settings
        triggers_text = self.triggers_edit.text().strip()
        triggers = (
            [t.strip() for t in triggers_text.split(",") if t.strip()]
            if triggers_text
            else ["voicebox"]
        )

        cmd_config = {
            "enabled": self.command_enabled_check.isChecked(),
            "triggers": triggers,
            "response_method": self.response_method_combo.currentText(),
            "openrouter_api_key": self.openrouter_key_edit.text(),
            "openrouter_model": self.openrouter_model_combo.get_current_model_id()
            or "meta-llama/llama-3.2-3b-instruct:free",
            "local_llm_endpoint": self.local_endpoint_edit.text(),
        }
        self.config_manager.set_setting("command_mode", cmd_config)

        # Save substitutions
        self.save_substitutions()

        # Reload all settings in the running VoiceBox instance
        if self.voicebox_app and hasattr(self.voicebox_app, "reload_config"):
            self.voicebox_app.reload_config()

        self.close()

    def load_substitutions_table(self):
        """Load substitutions into the table."""
        # Import substitution manager to access current substitutions
        from src.text.substitutions import SubstitutionManager

        config_dir = self.config_manager.config_dir
        sub_manager = SubstitutionManager(config_dir)
        substitutions = sub_manager.get_all_substitutions()

        # Set table size
        self.substitutions_table.setRowCount(len(substitutions))

        # Populate table
        for row, (pattern, replacement) in enumerate(substitutions.items()):
            self.substitutions_table.setItem(row, 0, QTableWidgetItem(pattern))
            self.substitutions_table.setItem(row, 1, QTableWidgetItem(replacement))

    def add_substitution(self):
        """Add a new substitution row."""
        row_count = self.substitutions_table.rowCount()
        self.substitutions_table.insertRow(row_count)
        self.substitutions_table.setItem(row_count, 0, QTableWidgetItem(""))
        self.substitutions_table.setItem(row_count, 1, QTableWidgetItem(""))

    def remove_substitution(self):
        """Remove selected substitution."""
        current_row = self.substitutions_table.currentRow()
        if current_row >= 0:
            self.substitutions_table.removeRow(current_row)

    def import_substitutions(self):
        """Import substitutions from file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Substitutions", "", "JSON Files (*.json)"
        )
        if file_path:
            from src.text.substitutions import SubstitutionManager

            config_dir = self.config_manager.config_dir
            sub_manager = SubstitutionManager(config_dir)

            if sub_manager.import_substitutions(file_path):
                self.load_substitutions_table()
                QMessageBox.information(
                    self, "Success", "Substitutions imported successfully!"
                )
            else:
                QMessageBox.warning(self, "Error", "Failed to import substitutions.")

    def export_substitutions(self):
        """Export substitutions to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Substitutions", "substitutions.json", "JSON Files (*.json)"
        )
        if file_path:
            from src.text.substitutions import SubstitutionManager

            config_dir = self.config_manager.config_dir
            sub_manager = SubstitutionManager(config_dir)

            if sub_manager.export_substitutions(file_path):
                QMessageBox.information(
                    self, "Success", "Substitutions exported successfully!"
                )
            else:
                QMessageBox.warning(self, "Error", "Failed to export substitutions.")

    def reset_substitutions(self):
        """Reset substitutions to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Substitutions",
            "Are you sure you want to reset all substitutions to defaults? This will remove all custom substitutions.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from src.text.substitutions import SubstitutionManager

            config_dir = self.config_manager.config_dir
            sub_manager = SubstitutionManager(config_dir)
            sub_manager.reset_to_defaults()
            self.load_substitutions_table()

    def save_substitutions(self):
        """Save substitutions from table."""
        from src.text.substitutions import SubstitutionManager

        config_dir = self.config_manager.config_dir
        sub_manager = SubstitutionManager(config_dir)

        # Clear current substitutions (keep only defaults, clear deletions)
        sub_manager.reset_to_defaults()

        # Collect all patterns from the table
        table_patterns = set()
        for row in range(self.substitutions_table.rowCount()):
            pattern_item = self.substitutions_table.item(row, 0)
            replacement_item = self.substitutions_table.item(row, 1)

            if pattern_item and replacement_item:
                pattern = pattern_item.text().strip()
                replacement = replacement_item.text().strip()

                if pattern and replacement:
                    table_patterns.add(pattern.lower())
                    sub_manager.add_substitution(pattern, replacement)

        # Mark any defaults that are NOT in the table as deleted
        for default_pattern in sub_manager.DEFAULT_SUBSTITUTIONS:
            if default_pattern.lower() not in table_patterns:
                if default_pattern not in sub_manager._deleted_defaults:
                    sub_manager._deleted_defaults.append(default_pattern)

        # Save the updated state
        sub_manager.save_substitutions()


class VoiceBoxGUI(QMainWindow):
    """Main GUI application for VoiceBox."""

    def __init__(self):
        super().__init__()

        self.config_manager = ConfigManager()
        self.voicebox_app = VoiceBoxApp()
        self.worker: Optional[VoiceBoxWorker] = None
        self.settings_window: Optional[SettingsWindow] = None

        # Check if system tray is available
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray is not available on this system.")
            sys.exit(1)

        self.init_ui()
        self.create_tray_icon()
        self.start_voicebox()

    def init_ui(self):
        """Initialize the main UI."""
        self.setWindowTitle("VoiceBox")
        self.setFixedSize(400, 300)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Status display
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("Starting...")
        status_layout.addWidget(self.status_label)

        self.hotkey_label = QLabel(f"Hotkey: {self.config_manager.get_hotkey()}")
        status_layout.addWidget(self.hotkey_label)

        self.mode_label = QLabel(
            f"Mode: {self.config_manager.get_transcription_mode()}"
        )
        status_layout.addWidget(self.mode_label)

        layout.addWidget(status_group)

        # Recent transcriptions
        transcription_group = QGroupBox("Recent Transcriptions")
        transcription_layout = QVBoxLayout(transcription_group)

        self.transcription_log = QTextEdit()
        self.transcription_log.setMaximumHeight(150)
        self.transcription_log.setReadOnly(True)
        transcription_layout.addWidget(self.transcription_log)

        layout.addWidget(transcription_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.show_settings)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.quit_application)

        button_layout.addWidget(self.settings_button)
        button_layout.addWidget(self.quit_button)

        layout.addLayout(button_layout)

        # Show window on startup instead of hiding
        self.show()

    def create_tray_icon(self):
        """Create system tray icon and menu."""
        self.tray_icon = QSystemTrayIcon(self)

        # Create a simple icon with "V" for VoiceBox
        from PyQt6.QtGui import QPainter, QFont

        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setBrush(Qt.GlobalColor.blue)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawEllipse(0, 0, 32, 32)
        painter.setPen(Qt.GlobalColor.white)
        font = QFont("Arial", 18, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "V")
        painter.end()

        icon = QIcon(pixmap)
        self.tray_icon.setIcon(icon)

        # Create tray menu
        tray_menu = QMenu()

        show_action = QAction("Show VoiceBox", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings)
        tray_menu.addAction(settings_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)

        self.tray_icon.show()
        self.tray_icon.showMessage(
            "VoiceBox",
            "VoiceBox is running in the background",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def tray_icon_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def show_window(self):
        """Show the main window."""
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """Handle window close event - minimize to tray instead."""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "VoiceBox",
            "Application was minimized to tray",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def show_settings(self):
        """Show settings window."""
        if self.settings_window is None:
            self.settings_window = SettingsWindow(
                self.config_manager, self.voicebox_app
            )

        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def start_voicebox(self):
        """Start VoiceBox in worker thread."""
        self.worker = VoiceBoxWorker(self.voicebox_app)
        self.worker.status_changed.connect(self.update_status)
        self.worker.transcription_complete.connect(self.add_transcription)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.start()

    def update_status(self, status: str):
        """Update status display."""
        self.status_label.setText(f"Status: {status}")

    def handle_error(self, error: str, error_type: str = "", suggestion: str = ""):
        """Handle error from worker thread with colored display."""
        from datetime import datetime
        from PyQt6.QtGui import QColor

        self.status_label.setText(f"Error: {error}")

        # Add to transcription log with color coding
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Build error message with color
        if error_type == "Warning":
            color = "#FFA500"  # Orange/yellow for warnings
            prefix = "WARNING"
            icon = "⚠"
        else:
            color = "#FF4444"  # Red for errors
            prefix = "ERROR"
            icon = "X"

        # Format: [timestamp] X ERROR: message
        error_msg = f'<span style="color: {color}">[{timestamp}] {icon} {prefix}: {error}</span>'

        if suggestion:
            error_msg += (
                f'<br><span style="color: #8888FF">Suggestion: {suggestion}</span>'
            )

        self.transcription_log.append(error_msg)
        self.transcription_log.verticalScrollBar().setValue(
            self.transcription_log.verticalScrollBar().maximum()
        )

        # Also show tray notification (plain text, truncated)
        self.tray_icon.showMessage(
            "VoiceBox Error", error[:200], QSystemTrayIcon.MessageIcon.Critical, 5000
        )

    def add_transcription(self, text: str):
        """Add transcription to the log."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_text = f"[{timestamp}] {text}\n"
        self.transcription_log.append(formatted_text)

        # Auto-scroll to bottom
        scrollbar = self.transcription_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Also show notification
        self.tray_icon.showMessage(
            "Transcription Complete",
            text[:100],
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def quit_application(self):
        """Quit the application."""
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)  # Wait up to 3 seconds

        QApplication.instance().quit()


def run_gui():
    """Run the GUI application."""
    from src.utils.logging import set_debug_mode, get_logger
    import signal

    # Check for --debug flag
    debug_mode = "--debug" in sys.argv
    if debug_mode:
        set_debug_mode(True)

    logger = get_logger(__name__)

    if debug_mode:
        logger.info("GUI running in debug mode")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running when window is closed

    # Set application properties
    app.setApplicationName("VoiceBox")
    app.setApplicationVersion("1.0.0")

    # Handle Ctrl+C properly
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    gui = VoiceBoxGUI()

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
