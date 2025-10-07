"""Custom widgets for VoiceBox GUI."""

from PyQt6.QtWidgets import QComboBox, QCompleter, QLineEdit
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QStringListModel
from PyQt6.QtGui import QFocusEvent


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