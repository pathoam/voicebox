# Publishing VoiceBox to PyPI

This guide explains how to publish VoiceBox to PyPI so users can install it with `uv add voicebox` or `pip install voicebox`.

## Prerequisites

1. **PyPI Account**: Register at [pypi.org](https://pypi.org/account/register/)
2. **API Token**: Generate an API token at [pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)
3. **Build Tools**: Ensure you have `uv` and `build` installed

## Preparation Steps

### 1. Update Package Information

Edit `pyproject.toml` and update:
- Version number (increment for each release)
- Author information
- Repository URLs (replace `your-username` with actual GitHub username)

### 2. Verify Package Structure

Ensure these files are present and up-to-date:
- `README.md` - Package description and usage
- `LICENSE` - MIT license file
- `pyproject.toml` - Package configuration
- All source files in `src/` directory

### 3. Test Local Build

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info/

# Build the package
uv run python -m build

# Verify the build
ls dist/
# Should show: voicebox-1.0.0-py3-none-any.whl and voicebox-1.0.0.tar.gz
```

### 4. Test Local Installation

```bash
# Test install from local build
uv add ./dist/voicebox-1.0.0-py3-none-any.whl

# Test that it works
voicebox --help
voicebox --gui

# Uninstall test version
uv remove voicebox
```

## Publishing to PyPI

### 1. Install Publishing Tools

```bash
uv add --dev twine
```

### 2. Upload to Test PyPI (Recommended First)

```bash
# Upload to TestPyPI first
uv run twine upload --repository testpypi dist/*

# Test install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ voicebox
```

### 3. Upload to Production PyPI

```bash
# Upload to production PyPI
uv run twine upload dist/*

# Enter your PyPI credentials when prompted
# Username: __token__
# Password: your-api-token-here
```

### 4. Verify Publication

Check that the package appears at: `https://pypi.org/project/voicebox/`

## Post-Publication

### 1. Test Installation

```bash
# Test that users can install
pip install voicebox
# or
uv add voicebox

# Test functionality
voicebox --gui
```

### 2. Update README

Once published, update the README.md to change:
```markdown
**Option 1: Install from PyPI** (Coming Soon)
```
to:
```markdown
**Option 1: Install from PyPI**
```

### 3. Tag the Release

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Future Updates

For each new version:

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG** (if you create one)
3. **Build and test** locally
4. **Upload to PyPI** using the same process
5. **Tag the release** in git

## Troubleshooting

### Common Issues

**"Package already exists"**: Increment the version number in `pyproject.toml`

**"Invalid credentials"**: Ensure you're using `__token__` as username and your API token as password

**"Missing files"**: Check that all required files are included in the build with:
```bash
uv run python -m build --wheel --sdist
tar -tzf dist/voicebox-*.tar.gz  # Check source distribution contents
```

**"Import errors after install"**: Verify the package structure and entry points in `pyproject.toml`

### Package Structure Verification

The published package should include:
- All files in `src/` directory
- `gui.py` entry point
- `README.md` and `LICENSE`
- Dependencies properly specified

## Automation (Optional)

You can automate publishing with GitHub Actions by creating `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v3
      with:
        python-version: '3.x'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

This will automatically publish to PyPI when you create a GitHub release.