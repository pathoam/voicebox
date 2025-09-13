# VoiceBox Packaging & Distribution Guide

## Best Installation Methods for Users

### 1. **Portable Package (Easiest - No Installation)**
Best for users who want to try VoiceBox without installing anything.

**How to use:**
```bash
# Download the portable package for your platform
tar -xzf voicebox-linux-x86_64-v1.0.0-portable.tar.gz
cd voicebox-linux-x86_64-v1.0.0
./run_voicebox.sh
```

**Benefits:**
- No installation required
- Can run from USB/external drive
- Leaves no traces on system
- Perfect for testing

### 2. **Installer Package (Recommended)**
Best for regular users who want proper system integration.

**How to use:**
```bash
# Download the installer package
tar -xzf voicebox-linux-x86_64-v1.0.0-installer.tar.gz
cd voicebox-linux-x86_64-v1.0.0-installer
sudo ./install.sh  # Or without sudo for user-only install
```

**Benefits:**
- Proper system integration
- Available in application menu
- Command line access (`voicebox`)
- Clean uninstaller included

### 3. **Platform-Specific Packages**

#### Linux (Debian/Ubuntu)
```bash
# Download .deb package
sudo dpkg -i voicebox_1.0.0_x86_64.deb
# Or
sudo apt install ./voicebox_1.0.0_x86_64.deb
```

#### macOS
- Installer creates .app bundle in /Applications
- Adds command line tool to /usr/local/bin

#### Windows
- Double-click installer.bat
- Creates Start Menu shortcut
- Installs to %LOCALAPPDATA%\VoiceBox

## Building Packages

### For Developers/Maintainers

```bash
# Build executable first
make build

# Create all packages
make package

# Or specific packages:
make package-portable    # Portable archive
make package-installer   # Installer with scripts  
make package-deb        # Debian package (Linux only)

# Full release (clean, build, package all)
make release
```

## Package Contents

### Portable Package
```
voicebox-linux-x86_64-v1.0.0/
├── voicebox              # Main executable
├── run_voicebox.sh       # Launcher script
└── README_PORTABLE.txt   # Quick start guide
```

### Installer Package
```
voicebox-linux-x86_64-v1.0.0-installer/
├── voicebox              # Main executable
├── install.sh            # Installation script
└── uninstall.sh          # Uninstallation script
```

## Distribution Recommendations

1. **GitHub Releases**: Upload all package types
2. **Package Managers**: Submit platform-specific packages
   - Debian/Ubuntu: Submit .deb to repositories
   - macOS: Consider Homebrew formula
   - Windows: Consider Chocolatey or Scoop

3. **Website Download**: Offer both portable and installer
   - Portable for "Try Now"
   - Installer for "Download"

## File Sizes

Typical package sizes:
- Portable: ~130MB compressed
- Installer: ~130MB compressed  
- Debian: ~130MB

The large size is due to bundled Python runtime and dependencies.
Consider offering a "lite" version that requires Python for advanced users.

## Version Management

Version is read from `pyproject.toml`. Update there before building releases.

## Testing Packages

Always test packages before release:

```bash
# Test portable
tar -xzf package.tar.gz
./run_voicebox.sh --test

# Test installer
./install.sh
voicebox --test
./uninstall.sh
```

## Security Considerations

- Sign packages when possible
- Provide checksums (SHA256)
- Use HTTPS for all downloads
- Include virus scan results

## Support Matrix

| Package Type | Windows | macOS | Linux |
|-------------|---------|-------|-------|
| Portable    | ✅      | ✅    | ✅    |
| Installer   | ✅      | ✅    | ✅    |
| .deb        | ❌      | ❌    | ✅    |
| .msi        | 🔄      | ❌    | ❌    |
| .dmg        | ❌      | 🔄    | ❌    |
| AppImage    | ❌      | ❌    | 🔄    |

✅ = Supported, ❌ = Not Applicable, 🔄 = Planned