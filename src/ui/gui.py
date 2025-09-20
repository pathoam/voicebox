#!/usr/bin/env python3

import sys
import threading
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QTextEdit,
    QSystemTrayIcon, QMenu, QGroupBox, QFormLayout, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog, QTabWidget
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QAction

from main import VoiceBoxApp
from config.manager import ConfigManager


class VoiceBoxWorker(QThread):
    """Worker thread for VoiceBox operations."""
    
    status_changed = pyqtSignal(str)
    transcription_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, app: VoiceBoxApp):
        super().__init__()
        self.voicebox_app = app
        self.running = False
        
        # Connect callbacks
        self.voicebox_app.on_transcription_complete = self._on_transcription
        self.voicebox_app.on_status_change = self._on_status_change
    
    def _on_transcription(self, text: str):
        """Handle transcription completion."""
        self.transcription_complete.emit(text)
        
    def _on_status_change(self, status: str):
        """Handle status change."""
        self.status_changed.emit(status)
        
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
        self.create_substitutions_tab()
        
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
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v2", "large-v3"])
        transcription_layout.addRow("Local Model:", self.model_combo)
        
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
        
    def create_substitutions_tab(self):
        """Create the text substitutions tab."""
        subs_tab = QWidget()
        layout = QVBoxLayout(subs_tab)
        
        # Header
        header_label = QLabel("Text Substitutions")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)
        
        desc_label = QLabel("Define replacements for commonly misheard technical terms:")
        layout.addWidget(desc_label)
        
        # Table for substitutions
        self.substitutions_table = QTableWidget()
        self.substitutions_table.setColumnCount(2)
        self.substitutions_table.setHorizontalHeaderLabels(["Misheard Text", "Correct Text"])
        self.substitutions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
        self.hotkey_edit.setText(self.config_manager.get_hotkey())
        self.insertion_combo.setCurrentText(self.config_manager.get_text_insertion_method())
        self.sample_rate_spin.setValue(self.config_manager.get_audio_sample_rate())
        self.channels_spin.setValue(self.config_manager.get_audio_channels())
        
        # Load substitutions
        self.load_substitutions_table()
        
    def save_settings(self):
        """Save settings and close window."""
        self.config_manager.set_setting("transcription_mode", self.mode_combo.currentText())
        self.config_manager.set_setting("api_key", self.api_key_edit.text())
        self.config_manager.set_setting("local_model_size", self.model_combo.currentText())
        self.config_manager.set_setting("hotkey", self.hotkey_edit.text())
        self.config_manager.set_setting("text_insertion_method", self.insertion_combo.currentText())
        self.config_manager.set_setting("audio_sample_rate", self.sample_rate_spin.value())
        self.config_manager.set_setting("audio_channels", self.channels_spin.value())
        
        # Save substitutions
        self.save_substitutions()
        
        # Reload all settings in the running VoiceBox instance
        if self.voicebox_app and hasattr(self.voicebox_app, 'reload_config'):
            self.voicebox_app.reload_config()
        
        self.close()
        
    def load_substitutions_table(self):
        """Load substitutions into the table."""
        # Import substitution manager to access current substitutions
        from text.substitutions import SubstitutionManager
        
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
            from text.substitutions import SubstitutionManager
            config_dir = self.config_manager.config_dir
            sub_manager = SubstitutionManager(config_dir)
            
            if sub_manager.import_substitutions(file_path):
                self.load_substitutions_table()
                QMessageBox.information(self, "Success", "Substitutions imported successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to import substitutions.")
                
    def export_substitutions(self):
        """Export substitutions to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Substitutions", "substitutions.json", "JSON Files (*.json)"
        )
        if file_path:
            from text.substitutions import SubstitutionManager
            config_dir = self.config_manager.config_dir
            sub_manager = SubstitutionManager(config_dir)
            
            if sub_manager.export_substitutions(file_path):
                QMessageBox.information(self, "Success", "Substitutions exported successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to export substitutions.")
                
    def reset_substitutions(self):
        """Reset substitutions to defaults."""
        reply = QMessageBox.question(
            self, "Reset Substitutions",
            "Are you sure you want to reset all substitutions to defaults? This will remove all custom substitutions.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            from text.substitutions import SubstitutionManager
            config_dir = self.config_manager.config_dir
            sub_manager = SubstitutionManager(config_dir)
            sub_manager.reset_to_defaults()
            self.load_substitutions_table()
            
    def save_substitutions(self):
        """Save substitutions from table."""
        from text.substitutions import SubstitutionManager
        config_dir = self.config_manager.config_dir
        sub_manager = SubstitutionManager(config_dir)
        
        # Clear current substitutions (keep only defaults)
        sub_manager.reset_to_defaults()
        
        # Add substitutions from table
        for row in range(self.substitutions_table.rowCount()):
            pattern_item = self.substitutions_table.item(row, 0)
            replacement_item = self.substitutions_table.item(row, 1)
            
            if pattern_item and replacement_item:
                pattern = pattern_item.text().strip()
                replacement = replacement_item.text().strip()
                
                if pattern and replacement:
                    sub_manager.add_substitution(pattern, replacement)


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
        
        self.mode_label = QLabel(f"Mode: {self.config_manager.get_transcription_mode()}")
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
        self.tray_icon.showMessage("VoiceBox", "VoiceBox is running in the background", 
                                  QSystemTrayIcon.MessageIcon.Information, 2000)
        
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
        self.tray_icon.showMessage("VoiceBox", "Application was minimized to tray",
                                  QSystemTrayIcon.MessageIcon.Information, 2000)
        
    def show_settings(self):
        """Show settings window."""
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.config_manager, self.voicebox_app)
            
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
        
    def handle_error(self, error: str):
        """Handle error from worker thread."""
        self.status_label.setText(f"Error: {error}")
        self.tray_icon.showMessage("VoiceBox Error", error,
                                  QSystemTrayIcon.MessageIcon.Critical, 5000)
    
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
        self.tray_icon.showMessage("Transcription Complete", text[:100],
                                  QSystemTrayIcon.MessageIcon.Information, 2000)
        
    def quit_application(self):
        """Quit the application."""
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)  # Wait up to 3 seconds
            
        QApplication.instance().quit()


def run_gui():
    """Run the GUI application."""
    import signal
    
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