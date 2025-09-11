# VoiceBox Build Makefile

.PHONY: help install dev build clean test run

# Default target
help:
	@echo "VoiceBox Build Commands:"
	@echo "========================"
	@echo "install     - Install dependencies with uv"
	@echo "dev         - Install with development dependencies"
	@echo "run         - Run VoiceBox from source"
	@echo "test        - Test the application"
	@echo "build       - Build single executable"
	@echo "clean       - Clean build artifacts"
	@echo "dist        - Create distribution package"
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