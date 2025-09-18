#!/bin/bash

# Manual release creation script for VoiceBox
# This creates a GitHub release with all packages

set -e

echo "================================"
echo "VoiceBox Release Creator"
echo "================================"
echo

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed"
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Not in a git repository"
    exit 1
fi

# Get version from pyproject.toml
VERSION=$(grep -m1 'version' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')
if [ -z "$VERSION" ]; then
    echo "❌ Could not determine version from pyproject.toml"
    exit 1
fi

TAG="v$VERSION"

echo "Version: $VERSION"
echo "Tag: $TAG"
echo

# Check if tag already exists
if git tag -l "$TAG" | grep -q "$TAG"; then
    echo "⚠️  Tag $TAG already exists"
    read -p "Delete and recreate? (y/N): " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        git tag -d "$TAG"
        git push origin --delete "$TAG" 2>/dev/null || true
    else
        exit 1
    fi
fi

# Build packages
echo "Building packages..."
make release

# Check that packages exist
if ! ls dist/*-portable.* dist/*-installer.* >/dev/null 2>&1; then
    echo "❌ No packages found in dist/"
    echo "Run 'make release' first"
    exit 1
fi

# Create git tag
echo "Creating git tag $TAG..."
git tag -a "$TAG" -m "Release $VERSION"

# Push tag
echo "Pushing tag to origin..."
git push origin "$TAG"

# Create release notes
RELEASE_NOTES=$(cat <<EOF
## VoiceBox $VERSION

### Installation

#### 🚀 Quick Install (No Python Required)

**Portable Version (No Installation):**
- Download the \`-portable\` package for your platform
- Extract and run the launcher script
- No admin rights required

**Installer Version (Recommended):**
- Download the \`-installer\` package for your platform  
- Run the install script
- Adds VoiceBox to system path and application menu

**Linux (Debian/Ubuntu):**
\`\`\`bash
sudo dpkg -i voicebox_${VERSION}_*.deb
\`\`\`

### Usage

1. Launch VoiceBox
2. Press \`Ctrl+Shift+V\` (or \`Cmd+Shift+V\` on macOS) to start recording
3. Speak your text
4. Press the hotkey again to stop and insert text

### What's New

See [CHANGELOG](https://github.com/$(git remote get-url origin | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/blob/main/CHANGELOG.md) for details.

### Configuration

Configuration file location:
- **Linux**: \`~/.config/VoiceBox/config.json\`
- **macOS**: \`~/Library/Application Support/VoiceBox/config.json\`
- **Windows**: \`%APPDATA%\\VoiceBox\\config.json\`
EOF
)

# Create GitHub release
echo "Creating GitHub release..."
gh release create "$TAG" \
    --title "VoiceBox $VERSION" \
    --notes "$RELEASE_NOTES" \
    dist/*-portable.tar.gz \
    dist/*-portable.zip \
    dist/*-installer.tar.gz \
    dist/*-installer.zip \
    dist/*.deb 2>/dev/null || true

echo
echo "================================"
echo "✅ Release $VERSION created!"
echo "================================"
echo
echo "View at: https://github.com/$(git remote get-url origin | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/releases/tag/$TAG"
echo
echo "Next steps:"
echo "1. Check the release page"
echo "2. Edit release notes if needed"
echo "3. Announce the release"