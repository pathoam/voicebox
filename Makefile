# VoiceBox Build Makefile

.PHONY: help install dev build clean test run package package-all package-portable package-installer package-deb release

# Default target
help:
	@echo "VoiceBox Build Commands:"
	@echo "========================"
	@echo "Development:"
	@echo "  install          - Install dependencies with uv"
	@echo "  dev              - Install with development dependencies"
	@echo "  run              - Run VoiceBox from source"
	@echo "  test             - Test the application"
	@echo "  clean            - Clean build artifacts"
	@echo ""
	@echo "Building:"
	@echo "  build            - Build single executable"
	@echo "  dist             - Create simple distribution package"
	@echo ""
	@echo "Packaging:"
	@echo "  package          - Create all distribution packages"
	@echo "  package-portable - Create portable package (no install)"
	@echo "  package-installer- Create installer package"
	@echo "  package-deb      - Create Debian package (Linux only)"
	@echo ""
	@echo "Release:"
	@echo "  release          - Build and create all packages for release"
	@echo ""
	@echo "Quick start:"
	@echo "  make dev && make run"

# Install production dependencies
install:
	uv sync --no-dev

# Install with development dependencies  
dev:
	uv sync

# Run from source
run:
	uv run python src/main.py

# Test the application
test:
	uv run python src/main.py --test

# Build executable
build:
	uv run python build.py

# Clean build artifacts
clean:
	rm -rf build/ dist/ __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +

# Create distribution
dist: clean build
	@echo "Creating distribution package..."
	@system=$$(uname -s | tr '[:upper:]' '[:lower:]'); \
	arch=$$(uname -m); \
	dist_name="voicebox-$${system}-$${arch}"; \
	if [ -d "dist/$$dist_name" ]; then \
		cd dist && tar -czf "$$dist_name.tar.gz" "$$dist_name/" && \
		echo "✓ Distribution created: dist/$$dist_name.tar.gz"; \
	else \
		echo "❌ Distribution directory not found"; \
	fi

# Quick development setup
setup: dev
	@echo "✓ Development environment ready!"
	@echo "Run 'make run' to start VoiceBox"

# Packaging commands
package: package-all

package-all: build
	@echo "Creating all distribution packages..."
	@uv run python scripts/package.py all

package-portable: build
	@echo "Creating portable package..."
	@uv run python scripts/package.py portable

package-installer: build
	@echo "Creating installer package..."
	@uv run python scripts/package.py installer

package-deb: build
	@echo "Creating Debian package..."
	@uv run python scripts/package.py deb

# Full release build
release: clean build package-all
	@echo ""
	@echo "════════════════════════════════════════════"
	@echo "✅ Release build complete!"
	@echo "════════════════════════════════════════════"
	@echo "Packages created in dist/"
	@echo ""
	@ls -lh dist/*.tar.gz dist/*.zip 2>/dev/null || true
	@echo ""
	@echo "Next steps:"
	@echo "1. Test the packages"
	@echo "2. Create GitHub release"
	@echo "3. Upload the packages"