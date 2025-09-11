#!/bin/bash
# Install uv package manager
echo "Installing uv package manager..."
curl -LsSf https://astral.sh/uv/install.sh | sh
echo "✓ uv installed"
echo "Add to PATH: export PATH=\"\$HOME/.cargo/bin:\$PATH\""
echo "Or restart your shell"