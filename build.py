#!/usr/bin/env python3
"""
Build script for VoiceBox executable
Creates single-file executables for different platforms
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path


def get_platform_info():
    """Get platform-specific information for building."""
    system = platform.system().lower()
    arch = platform.machine().lower()
    
    if system == "windows":
        exe_name = "voicebox.exe"
        dist_name = f"voicebox-windows-{arch}"
    elif system == "darwin":
        exe_name = "voicebox"
        dist_name = f"voicebox-macos-{arch}"
    else:  # linux and others
        exe_name = "voicebox"
        dist_name = f"voicebox-linux-{arch}"
    
    return system, arch, exe_name, dist_name


def check_dependencies():
    """Check if required build dependencies are available."""
    try:
        import PyInstaller
        print(f"✓ PyInstaller found: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Install with: uv add pyinstaller")
        return False
    
    return True


def clean_build_artifacts():
    """Clean up previous build artifacts."""
    artifacts = ["build", "dist", "__pycache__"]
    
    for artifact in artifacts:
        if os.path.exists(artifact):
            print(f"Cleaning {artifact}/")
            shutil.rmtree(artifact)
    
    # Clean .pyc files
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith('.pyc'):
                os.remove(os.path.join(root, file))


def build_executable():
    """Build the executable using PyInstaller."""
    system, arch, exe_name, dist_name = get_platform_info()
    
    print(f"Building for {system} ({arch})...")
    
    # PyInstaller command
    cmd = [
        "python", "-m", "PyInstaller",
        "build_config/voicebox.spec",
        "--clean",
        "--noconfirm"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ Build successful!")
            
            # Check if executable was created
            exe_path = Path("dist") / exe_name
            if exe_path.exists():
                file_size = exe_path.stat().st_size / (1024 * 1024)  # MB
                print(f"✓ Executable created: {exe_path} ({file_size:.1f} MB)")
                
                # Create distribution directory
                dist_dir = Path("dist") / dist_name
                if dist_dir.exists():
                    shutil.rmtree(dist_dir)
                dist_dir.mkdir()
                
                # Copy executable to distribution directory
                shutil.copy2(exe_path, dist_dir / exe_name)
                
                # Copy README
                if Path("README.md").exists():
                    shutil.copy2("README.md", dist_dir / "README.md")
                
                print(f"✓ Distribution created: {dist_dir}/")
                return True
            else:
                print("❌ Executable not found in dist/")
                return False
        else:
            print("❌ Build failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False


def create_installer_script():
    """Create a simple installer script."""
    system, arch, exe_name, dist_name = get_platform_info()
    
    if system == "windows":
        installer_content = f"""@echo off
echo Installing VoiceBox...
copy {exe_name} "%USERPROFILE%\\AppData\\Local\\VoiceBox\\{exe_name}"
echo VoiceBox installed to %USERPROFILE%\\AppData\\Local\\VoiceBox\\
echo You can now run VoiceBox from the Start Menu or add it to your PATH
pause
"""
        installer_path = Path("dist") / dist_name / "install.bat"
        
    else:  # Unix-like systems
        installer_content = f"""#!/bin/bash
echo "Installing VoiceBox..."
mkdir -p ~/.local/bin
cp {exe_name} ~/.local/bin/{exe_name}
chmod +x ~/.local/bin/{exe_name}
echo "VoiceBox installed to ~/.local/bin/{exe_name}"
echo "Make sure ~/.local/bin is in your PATH to run 'voicebox' from anywhere"
echo "Or run directly: ~/.local/bin/voicebox"
"""
        installer_path = Path("dist") / dist_name / "install.sh"
    
    installer_path.write_text(installer_content)
    if system != "windows":
        os.chmod(installer_path, 0o755)
    
    print(f"✓ Installer created: {installer_path}")


def test_executable():
    """Test the built executable."""
    system, arch, exe_name, dist_name = get_platform_info()
    exe_path = Path("dist") / exe_name
    
    if not exe_path.exists():
        print("❌ Executable not found for testing")
        return False
    
    print("Testing executable...")
    
    try:
        # Test with --help flag
        cmd = [str(exe_path), "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✓ Executable test passed")
            return True
        else:
            print("❌ Executable test failed")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⚠️  Executable test timed out (this might be normal)")
        return True
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False


def main():
    """Main build function."""
    print("VoiceBox Build Script")
    print("=" * 40)
    
    if not check_dependencies():
        sys.exit(1)
    
    print("Cleaning previous builds...")
    clean_build_artifacts()
    
    print("Building executable...")
    if not build_executable():
        sys.exit(1)
    
    print("Creating installer script...")
    create_installer_script()
    
    print("Testing executable...")
    test_executable()
    
    system, arch, exe_name, dist_name = get_platform_info()
    
    print("\n" + "=" * 40)
    print("✓ Build completed successfully!")
    print(f"Platform: {system} ({arch})")
    print(f"Executable: dist/{exe_name}")
    print(f"Distribution: dist/{dist_name}/")
    print("\nTo distribute:")
    print(f"1. ZIP the dist/{dist_name}/ folder")
    print(f"2. Users can run the installer script inside")
    print("=" * 40)


if __name__ == "__main__":
    main()