#!/usr/bin/env python3
"""
Simple test to see if PyQt6 GUI works at all
"""

import sys
import signal
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel

# Allow Ctrl+C to work
signal.signal(signal.SIGINT, signal.SIG_DFL)

app = QApplication(sys.argv)

window = QMainWindow()
window.setWindowTitle("VoiceBox Test")
window.setGeometry(100, 100, 300, 200)
label = QLabel("If you see this, PyQt6 is working!", window)
label.setGeometry(50, 50, 200, 50)

window.show()

print("GUI should be visible now. Press Ctrl+C to exit.")
sys.exit(app.exec())