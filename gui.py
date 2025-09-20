#!/usr/bin/env python3
"""
GUI entry point for VoiceBox.
Run this script to start VoiceBox with GUI interface.
"""

import sys
import os

# Add src directory to path so we can import modules
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

from ui.gui import run_gui

if __name__ == "__main__":
    sys.exit(run_gui())