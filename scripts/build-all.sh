#!/bin/bash
"""
Cross-platform build script for VoiceBox
Builds executables for multiple platforms using GitHub Actions or local Docker
"""

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "VoiceBox Cross-Platform Builder"
echo "==============================="

# Function to build for a specific platform
build_platform() {
    local platform=$1
    local arch=$2
    
    echo "Building for $platform-$arch..."
    
    case $platform in
        "linux")
            docker run --rm \
                -v "$PROJECT_DIR:/workspace" \
                -w /workspace \
                python:3.9-slim \
                /bin/bash -c "
                    apt-get update && apt-get install -y build-essential portaudio19-dev &&
                    pip install uv &&
                    uv sync &&
                    uv run python build.py
                "
            ;;
        "windows")
            echo "Windows builds require Windows environment or cross-compilation"
            echo "Use GitHub Actions or Windows machine"
            ;;
        "macos")
            echo "macOS builds require macOS environment"  
            echo "Use GitHub Actions or macOS machine"
            ;;
        *)
            echo "Unknown platform: $platform"
            return 1
            ;;
    esac
}

# Check if running in appropriate environment
if command -v docker &> /dev/null; then
    echo "Docker available - can build Linux executables"
else
    echo "No Docker found - building for current platform only"
fi

# Build for current platform
echo "Building for current platform..."
cd "$PROJECT_DIR"
python build.py

echo "✓ Build completed"
echo "Check dist/ directory for executables"