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
    QProgressDialog,
    QScrollArea,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QAction

from src.main import VoiceBoxApp
from src.config.manager import ConfigManager
from src.ui.widgets import SearchableComboBox, HotkeyButton
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
            self.error_occurred.emit("Failed to start VoiceBox", "Startup", "Check transcription settings")
            return

        self.status_changed.emit("Ready")

        # Keep thread alive while app is running
        while self.running and self.voicebox_app._running:
            self.msleep(100)

    def stop(self):
        """Stop the worker thread."""
        self.running = False
        self.voicebox_app.stop()


class ModelReloadWorker(QThread):
    """Worker thread for reloading the transcription model after settings change."""

    status_update = pyqtSignal(str)
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, voicebox_app: VoiceBoxApp):
        super().__init__()
        self.voicebox_app = voicebox_app

    def run(self):
        """Reinitialize the transcription service in the background."""
        try:
            self.status_update.emit("Initializing transcription backend...")
            self.voicebox_app._initialize_transcription()
            self.finished.emit(True, "Model loaded successfully")
        except Exception as e:
            self.finished.emit(False, str(e))


class SettingsWindow(QMainWindow):
    """Settings configuration window."""

    def __init__(self, config_manager: ConfigManager, voicebox_app=None):
        super().__init__()
        self.config_manager = config_manager
        self.voicebox_app = voicebox_app  # Reference to running VoiceBox instance
        self.on_model_status = None  # Callback to main GUI for status updates
        self.model_fetcher = OpenRouterModels()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the settings UI."""
        self.setWindowTitle("VoiceBox Settings")
        self.setMinimumSize(700, 600)
        self.resize(700, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.create_general_tab()
        self.create_command_tab()
        self.create_corrections_tab()

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
        # Scroll area wrapper
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)

        # Transcription settings
        transcription_group = QGroupBox("Transcription")
        transcription_layout = QFormLayout(transcription_group)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["local", "api", "qwen"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
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

        self.hotkey_edit = HotkeyButton()
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

        # Qwen-ASR settings
        self.qwen_group = QGroupBox("Qwen-ASR Settings")
        qwen_layout = QFormLayout(self.qwen_group)

        self.qwen_model_combo = QComboBox()
        self.qwen_model_combo.addItems(["0.6B", "1.7B"])
        qwen_layout.addRow("Model Size:", self.qwen_model_combo)

        self.qwen_backend_combo = QComboBox()
        self.qwen_backend_combo.addItem("auto", "auto")
        self.qwen_backend_combo.addItem("GPU — fastest inference", "gpu")
        qwen_layout.addRow("Backend:", self.qwen_backend_combo)

        self.qwen_streaming_check = QCheckBox("Enable streaming during recording")
        self.qwen_streaming_check.setToolTip(
            "Transcribe audio chunks during recording for faster results"
        )
        qwen_layout.addRow("Streaming:", self.qwen_streaming_check)

        self.qwen_group.setVisible(False)
        layout.addWidget(self.qwen_group)

        layout.addStretch()
        scroll.setWidget(general_tab)
        self.tab_widget.addTab(scroll, "General")

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

    def _on_mode_changed(self, mode: str):
        """Show/hide Qwen settings based on selected transcription mode."""
        self.qwen_group.setVisible(mode == "qwen")

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

    def create_corrections_tab(self):
        """Create the text corrections tab (replaces old substitutions tab)."""
        corrections_tab = QWidget()
        layout = QVBoxLayout(corrections_tab)

        # --- Corrections Section ---
        header_label = QLabel("Text Corrections")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)

        desc_label = QLabel(
            "Define replacements for commonly misheard technical terms:"
        )
        layout.addWidget(desc_label)

        # Search filter
        search_layout = QHBoxLayout()
        search_label = QLabel("Filter:")
        self.corrections_search = QLineEdit()
        self.corrections_search.setPlaceholderText("Search corrections...")
        self.corrections_search.textChanged.connect(self._filter_corrections_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.corrections_search)
        layout.addLayout(search_layout)

        # Table for corrections
        self.corrections_table = QTableWidget()
        self.corrections_table.setColumnCount(2)
        self.corrections_table.setHorizontalHeaderLabels(
            ["Misheard Text", "Correct Text"]
        )
        self.corrections_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.corrections_table)

        # Buttons for managing corrections
        corr_button_layout = QHBoxLayout()

        self.add_corr_button = QPushButton("Add")
        self.add_corr_button.clicked.connect(self.add_correction)

        self.remove_corr_button = QPushButton("Remove Selected")
        self.remove_corr_button.clicked.connect(self.remove_correction)

        self.import_corr_button = QPushButton("Import...")
        self.import_corr_button.clicked.connect(self.import_corrections)

        self.export_corr_button = QPushButton("Export...")
        self.export_corr_button.clicked.connect(self.export_corrections)

        self.reset_corr_button = QPushButton("Reset to Defaults")
        self.reset_corr_button.clicked.connect(self.reset_corrections)

        corr_button_layout.addWidget(self.add_corr_button)
        corr_button_layout.addWidget(self.remove_corr_button)
        corr_button_layout.addStretch()
        corr_button_layout.addWidget(self.import_corr_button)
        corr_button_layout.addWidget(self.export_corr_button)
        corr_button_layout.addWidget(self.reset_corr_button)

        layout.addLayout(corr_button_layout)

        # --- Vocabulary Section ---
        vocab_group = QGroupBox("Vocabulary (ASR Context Biasing)")
        vocab_layout = QVBoxLayout(vocab_group)

        vocab_desc = QLabel(
            "Terms listed here bias the ASR model toward these words during transcription. "
            "Keep 20-50 focused terms for best results."
        )
        vocab_desc.setWordWrap(True)
        vocab_layout.addWidget(vocab_desc)

        self.vocab_list = QTextEdit()
        self.vocab_list.setMaximumHeight(100)
        self.vocab_list.setPlaceholderText("One term per line (e.g., Kubernetes, Claude, Supabase)")
        vocab_layout.addWidget(self.vocab_list)

        vocab_btn_layout = QHBoxLayout()
        self.vocab_add_btn = QPushButton("Add Term")
        self.vocab_add_btn.clicked.connect(self._add_vocab_term)
        self.vocab_clear_btn = QPushButton("Clear All")
        self.vocab_clear_btn.clicked.connect(self._clear_vocab)
        vocab_btn_layout.addWidget(self.vocab_add_btn)
        vocab_btn_layout.addWidget(self.vocab_clear_btn)
        vocab_btn_layout.addStretch()
        vocab_layout.addLayout(vocab_btn_layout)

        layout.addWidget(vocab_group)

        # --- Training Data Section ---
        training_group = QGroupBox("Training Data")
        training_layout = QFormLayout(training_group)

        self.training_stats_label = QLabel("Loading...")
        training_layout.addRow("Stats:", self.training_stats_label)

        self.training_max_spin = QSpinBox()
        self.training_max_spin.setRange(100, 10000)
        self.training_max_spin.setSuffix(" MB")
        self.training_max_spin.setValue(2048)
        training_layout.addRow("Max Storage:", self.training_max_spin)

        self.training_enabled_check = QCheckBox("Enable training data collection")
        training_layout.addRow("", self.training_enabled_check)

        training_btn_layout = QHBoxLayout()
        self.training_export_btn = QPushButton("Export...")
        self.training_export_btn.clicked.connect(self._export_training_data)
        self.training_clear_btn = QPushButton("Clear All Data")
        self.training_clear_btn.clicked.connect(self._clear_training_data)
        training_btn_layout.addWidget(self.training_export_btn)
        training_btn_layout.addWidget(self.training_clear_btn)
        training_btn_layout.addStretch()
        training_layout.addRow("", training_btn_layout)

        layout.addWidget(training_group)

        self.tab_widget.addTab(corrections_tab, "Corrections")

    def _snapshot_transcription_settings(self) -> dict:
        """Capture current transcription-related settings for change detection."""
        return {
            "mode": self.config_manager.get_transcription_mode(),
            "qwen_model_size": self.config_manager.get_setting("qwen_model_size"),
            "qwen_backend": self.config_manager.get_setting("qwen_backend"),
            "local_model_size": self.config_manager.get_local_model_size(),
            "api_key": self.config_manager.get_api_key(),
        }

    def load_settings(self):
        """Load current settings into the UI."""
        # Snapshot for change detection on save
        self._settings_before = self._snapshot_transcription_settings()

        self.mode_combo.setCurrentText(self.config_manager.get_transcription_mode())
        self.api_key_edit.setText(self.config_manager.get_api_key() or "")
        self.model_combo.setCurrentText(self.config_manager.get_local_model_size())

        # Set language combo
        current_language = self.config_manager.get_transcription_language()
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == current_language:
                self.language_combo.setCurrentIndex(i)
                break

        self.hotkey_edit.setHotkey(self.config_manager.get_hotkey())
        self.insertion_combo.setCurrentText(
            self.config_manager.get_text_insertion_method()
        )
        self.sample_rate_spin.setValue(self.config_manager.get_audio_sample_rate())
        self.channels_spin.setValue(self.config_manager.get_audio_channels())

        # Load Qwen settings
        qwen_config = self.config_manager.get_qwen_config()
        self.qwen_model_combo.setCurrentText(qwen_config["model_size"])
        # Set backend combo by data value
        for i in range(self.qwen_backend_combo.count()):
            if self.qwen_backend_combo.itemData(i) == qwen_config["backend"]:
                self.qwen_backend_combo.setCurrentIndex(i)
                break
        self.qwen_streaming_check.setChecked(qwen_config["streaming_enabled"])
        self._on_mode_changed(self.mode_combo.currentText())

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

        # Load corrections
        self.load_corrections_table()

        # Load vocabulary
        self._load_vocabulary()

        # Load training data settings
        self.training_enabled_check.setChecked(
            self.config_manager.get_setting("training_data_enabled", True)
        )
        self.training_max_spin.setValue(
            self.config_manager.get_setting("training_data_max_mb", 2048)
        )
        self._update_training_stats()

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
        self.config_manager.set_setting("hotkey", self.hotkey_edit.hotkey())
        self.config_manager.set_setting(
            "text_insertion_method", self.insertion_combo.currentText()
        )
        self.config_manager.set_setting(
            "audio_sample_rate", self.sample_rate_spin.value()
        )
        self.config_manager.set_setting("audio_channels", self.channels_spin.value())

        # Save Qwen settings
        self.config_manager.set_setting(
            "qwen_model_size", self.qwen_model_combo.currentText()
        )
        self.config_manager.set_setting(
            "qwen_backend", self.qwen_backend_combo.currentData()
        )
        self.config_manager.set_setting(
            "qwen_streaming_enabled", self.qwen_streaming_check.isChecked()
        )

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

        # Save corrections
        self.save_corrections()

        # Save vocabulary from text edit
        self._save_vocabulary()

        # Save training data settings
        self.config_manager.set_setting(
            "training_data_enabled", self.training_enabled_check.isChecked()
        )
        self.config_manager.set_setting(
            "training_data_max_mb", self.training_max_spin.value()
        )

        # Check if transcription settings changed (needs model reload)
        settings_after = self._snapshot_transcription_settings()
        model_changed = settings_after != self._settings_before

        if model_changed and self.voicebox_app:
            # Reload non-transcription settings first (hotkeys, corrections, etc.)
            self.voicebox_app.config_manager._load_config()
            if self.voicebox_app.correction_pipeline:
                self.voicebox_app.correction_pipeline.reload()

            # Show progress dialog and reload model in background
            self._show_model_reload_dialog()
        else:
            # No model change — reload in background to avoid blocking the GUI
            if self.voicebox_app and hasattr(self.voicebox_app, "reload_config"):
                import threading
                threading.Thread(
                    target=self.voicebox_app.reload_config, daemon=True
                ).start()
            self.close()

    def _show_model_reload_dialog(self):
        """Show a progress dialog while the transcription model reloads."""
        self.save_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

        self._progress_dialog = QProgressDialog(
            "Loading transcription model...", None, 0, 0, self
        )
        self._progress_dialog.setWindowTitle("VoiceBox")
        self._progress_dialog.setMinimumWidth(350)
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setCancelButton(None)  # No cancel — download must complete
        self._progress_dialog.show()

        self._reload_worker = ModelReloadWorker(self.voicebox_app)
        self._reload_worker.status_update.connect(self._on_reload_status)
        self._reload_worker.finished.connect(self._on_reload_finished)
        self._reload_worker.start()

    def _on_reload_status(self, message: str):
        """Update progress dialog text and main window status."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            self._progress_dialog.setLabelText(message)
        if self.on_model_status:
            self.on_model_status(message)

    def _on_reload_finished(self, success: bool, message: str):
        """Handle model reload completion."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        self.save_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

        if success:
            if self.on_model_status:
                self.on_model_status("Ready")
            QMessageBox.information(self, "VoiceBox", "Model loaded successfully.")
            self.close()
        else:
            if self.on_model_status:
                self.on_model_status(f"Error: {message}")
            QMessageBox.critical(
                self, "Model Load Failed",
                f"Failed to load model:\n\n{message}\n\n"
                "Previous model will continue to be used. "
                "Check your settings and try again.",
            )
            # Reload previous snapshot so user can fix settings
            self._settings_before = self._snapshot_transcription_settings()

    def load_corrections_table(self):
        """Load corrections into the table."""
        from src.text.corrections import TermReplacementStage

        config_dir = self.config_manager.config_dir
        stage = TermReplacementStage(config_dir)
        corrections = stage.get_all_corrections()

        self.corrections_table.setRowCount(len(corrections))
        for row, (pattern, replacement) in enumerate(corrections.items()):
            self.corrections_table.setItem(row, 0, QTableWidgetItem(pattern))
            self.corrections_table.setItem(row, 1, QTableWidgetItem(replacement))

    def _filter_corrections_table(self, query: str):
        """Filter corrections table by search query."""
        query = query.lower()
        for row in range(self.corrections_table.rowCount()):
            pattern_item = self.corrections_table.item(row, 0)
            replacement_item = self.corrections_table.item(row, 1)
            pattern_text = pattern_item.text().lower() if pattern_item else ""
            replacement_text = replacement_item.text().lower() if replacement_item else ""
            match = not query or query in pattern_text or query in replacement_text
            self.corrections_table.setRowHidden(row, not match)

    def add_correction(self):
        """Add a new correction row."""
        row_count = self.corrections_table.rowCount()
        self.corrections_table.insertRow(row_count)
        self.corrections_table.setItem(row_count, 0, QTableWidgetItem(""))
        self.corrections_table.setItem(row_count, 1, QTableWidgetItem(""))

    def remove_correction(self):
        """Remove selected correction."""
        current_row = self.corrections_table.currentRow()
        if current_row >= 0:
            self.corrections_table.removeRow(current_row)

    def import_corrections(self):
        """Import corrections from file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Corrections", "", "JSON Files (*.json)"
        )
        if file_path:
            from src.text.corrections import TermReplacementStage

            config_dir = self.config_manager.config_dir
            stage = TermReplacementStage(config_dir)

            if stage.import_corrections(file_path):
                self.load_corrections_table()
                QMessageBox.information(
                    self, "Success", "Corrections imported successfully!"
                )
            else:
                QMessageBox.warning(self, "Error", "Failed to import corrections.")

    def export_corrections(self):
        """Export corrections to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Corrections", "corrections.json", "JSON Files (*.json)"
        )
        if file_path:
            from src.text.corrections import TermReplacementStage

            config_dir = self.config_manager.config_dir
            stage = TermReplacementStage(config_dir)

            if stage.export_corrections(file_path):
                QMessageBox.information(
                    self, "Success", "Corrections exported successfully!"
                )
            else:
                QMessageBox.warning(self, "Error", "Failed to export corrections.")

    def reset_corrections(self):
        """Reset corrections to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Corrections",
            "Are you sure you want to reset all corrections to defaults? This will remove all custom corrections.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from src.text.corrections import TermReplacementStage

            config_dir = self.config_manager.config_dir
            stage = TermReplacementStage(config_dir)
            stage.reset_to_defaults()
            self.load_corrections_table()

    def save_corrections(self):
        """Save corrections from table."""
        from src.text.corrections import TermReplacementStage

        config_dir = self.config_manager.config_dir
        stage = TermReplacementStage(config_dir)

        # Clear current corrections (keep only defaults, clear deletions)
        stage.reset_to_defaults()

        # Collect all patterns from the table
        table_patterns = set()
        for row in range(self.corrections_table.rowCount()):
            pattern_item = self.corrections_table.item(row, 0)
            replacement_item = self.corrections_table.item(row, 1)

            if pattern_item and replacement_item:
                pattern = pattern_item.text().strip()
                replacement = replacement_item.text().strip()

                if pattern and replacement:
                    table_patterns.add(pattern.lower())
                    stage.add_correction(pattern, replacement)

        # Mark any defaults that are NOT in the table as deleted
        for default_pattern in stage.DEFAULT_CORRECTIONS:
            if default_pattern.lower() not in table_patterns:
                if default_pattern not in stage._deleted_defaults:
                    stage._deleted_defaults.append(default_pattern)

        # Save the updated state
        stage.save()

    def _load_vocabulary(self):
        """Load vocabulary terms into the text edit."""
        from src.text.vocabulary import VocabularyManager

        config_dir = self.config_manager.config_dir
        vocab = VocabularyManager(config_dir)
        terms = vocab.get_terms()
        self.vocab_list.setPlainText("\n".join(terms))

    def _save_vocabulary(self):
        """Save vocabulary terms from the text edit."""
        from src.text.vocabulary import VocabularyManager

        config_dir = self.config_manager.config_dir
        vocab = VocabularyManager(config_dir)
        vocab.clear()
        text = self.vocab_list.toPlainText().strip()
        if text:
            for line in text.splitlines():
                term = line.strip()
                if term:
                    vocab.add_term(term)

    def _add_vocab_term(self):
        """Add a vocabulary term via input dialog."""
        from PyQt6.QtWidgets import QInputDialog

        term, ok = QInputDialog.getText(self, "Add Vocabulary Term", "Term:")
        if ok and term.strip():
            from src.text.vocabulary import VocabularyManager

            config_dir = self.config_manager.config_dir
            vocab = VocabularyManager(config_dir)
            if vocab.add_term(term.strip()):
                self._load_vocabulary()
            else:
                QMessageBox.information(self, "Info", f"'{term}' is already in vocabulary")

    def _clear_vocab(self):
        """Clear all vocabulary terms."""
        reply = QMessageBox.question(
            self, "Clear Vocabulary",
            "Are you sure you want to clear all vocabulary terms?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from src.text.vocabulary import VocabularyManager

            config_dir = self.config_manager.config_dir
            vocab = VocabularyManager(config_dir)
            vocab.clear()
            self._load_vocabulary()

    def _update_training_stats(self):
        """Update training data statistics display."""
        try:
            from src.data.collector import TrainingDataCollector

            config_dir = self.config_manager.config_dir
            collector = TrainingDataCollector(config_dir, enabled=True)
            stats = collector.get_stats()
            self.training_stats_label.setText(
                f"{stats['total_samples']} samples, "
                f"{stats['user_edited']} corrected, "
                f"{stats['total_size_mb']} MB"
            )
        except Exception:
            self.training_stats_label.setText("Unable to load stats")

    def _export_training_data(self):
        """Export training data to a directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Export Training Data"
        )
        if dir_path:
            from src.data.collector import TrainingDataCollector

            config_dir = self.config_manager.config_dir
            collector = TrainingDataCollector(config_dir, enabled=True)
            if collector.export(dir_path):
                QMessageBox.information(self, "Success", "Training data exported!")
            else:
                QMessageBox.warning(self, "Error", "Failed to export training data.")

    def _clear_training_data(self):
        """Clear all training data."""
        reply = QMessageBox.question(
            self, "Clear Training Data",
            "Are you sure you want to delete all training data? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from src.data.collector import TrainingDataCollector

            config_dir = self.config_manager.config_dir
            collector = TrainingDataCollector(config_dir, enabled=True)
            collector.clear()
            self._update_training_stats()


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

        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(QLabel("Hotkey:"))
        self.hotkey_button = HotkeyButton(self.config_manager.get_hotkey())
        self.hotkey_button.hotkeyChanged.connect(self._on_hotkey_changed)
        hotkey_row.addWidget(self.hotkey_button)
        status_layout.addLayout(hotkey_row)

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
        """Handle window close event - quit the application."""
        self.quit_application()
        event.accept()

    def show_settings(self):
        """Show settings window."""
        if self.settings_window is None:
            self.settings_window = SettingsWindow(
                self.config_manager, self.voicebox_app
            )
            self.settings_window.on_model_status = self._on_model_status
        self.settings_window.load_settings()
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _on_model_status(self, status: str):
        """Update main window status when model is loading/loaded."""
        self.update_status(status)
        if status.startswith("Error"):
            self.tray_icon.showMessage(
                "VoiceBox", status,
                QSystemTrayIcon.MessageIcon.Critical, 5000,
            )

    def _on_hotkey_changed(self, hotkey: str) -> None:
        """Handle hotkey change from the capture button."""
        self.config_manager.set_setting("hotkey", hotkey)
        if self.voicebox_app and self.voicebox_app.hotkey_manager:
            try:
                self.voicebox_app.hotkey_manager.set_hotkey(hotkey)
                self.voicebox_app.hotkey_manager.start_listening()
            except Exception as e:
                self.update_status(f"Hotkey error: {e}")
                return
        self.update_status(f"Hotkey set to: {hotkey}")

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
    app.setQuitOnLastWindowClosed(True)

    # Set application properties
    app.setApplicationName("VoiceBox")
    app.setApplicationVersion("1.0.0")

    # Handle Ctrl+C properly
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    gui = VoiceBoxGUI()

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
