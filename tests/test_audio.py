#!/usr/bin/env python3
"""Test audio capture functionality."""

import sys
import os
import time
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from audio.capture import AudioRecorder


def test_audio_device_listing():
    """Test listing audio devices."""
    print("Testing audio device listing...")
    try:
        AudioRecorder.list_audio_devices()
        print("✅ Audio device listing successful")
        return True
    except Exception as e:
        print(f"❌ Audio device listing failed: {e}")
        return False


def test_audio_recorder_init():
    """Test audio recorder initialization."""
    print("Testing audio recorder initialization...")
    try:
        recorder = AudioRecorder()
        print(f"✅ Audio recorder initialized: {recorder.sample_rate}Hz, {recorder.channels} channels")
        return True
    except Exception as e:
        print(f"❌ Audio recorder initialization failed: {e}")
        return False


def test_audio_recording_simulation():
    """Test audio recording start/stop (simulation)."""
    print("Testing audio recording simulation...")
    try:
        recorder = AudioRecorder()
        
        # Test recording state
        if recorder.is_recording():
            print("❌ Recorder should not be recording initially")
            return False
        
        print("✅ Initial recording state correct")
        
        # Test start recording
        print("Starting recording simulation...")
        recorder.start_recording()
        
        if not recorder.is_recording():
            print("❌ Recorder should be recording after start")
            return False
        
        print("✅ Recording started successfully")
        
        # Simulate short recording
        time.sleep(1)
        
        # Test stop recording
        print("Stopping recording...")
        audio_file = recorder.stop_recording()
        
        if recorder.is_recording():
            print("❌ Recorder should not be recording after stop")
            return False
        
        if not os.path.exists(audio_file):
            print(f"❌ Audio file not created: {audio_file}")
            return False
        
        print(f"✅ Recording stopped, file created: {audio_file}")
        
        # Cleanup
        recorder.cleanup_temp_file(audio_file)
        print("✅ Cleanup successful")
        
        return True
    except Exception as e:
        print(f"❌ Audio recording test failed: {e}")
        return False


def main():
    """Run all audio tests."""
    print("=" * 50)
    print("AUDIO COMPONENT TESTS")
    print("=" * 50)
    
    tests = [
        test_audio_device_listing,
        test_audio_recorder_init,
        test_audio_recording_simulation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        print(f"\n{'-' * 30}")
        if test():
            passed += 1
        print(f"{'-' * 30}")
    
    print(f"\n{'=' * 50}")
    print(f"AUDIO TESTS SUMMARY: {passed}/{total} passed")
    print(f"{'=' * 50}")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)