#!/bin/bash

# Wireless Engineer's Diagnostic Suite - Setup Script
# Installs all required dependencies on a fresh macOS machine.

echo "=================================================="
echo "Wireless Engineer's Diagnostic Suite - Setup"
echo "=================================================="
echo ""

# --- Check Python 3 ---
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Install it from https://www.python.org/downloads/ or via Homebrew:"
    echo "    brew install python"
    exit 1
fi
echo "Found: $(python3 --version)"

# --- Check pip3 ---
if ! command -v pip3 &> /dev/null; then
    echo "ERROR: pip3 is not installed. Reinstall Python 3 to include pip."
    exit 1
fi
echo "Found: pip3"
echo ""

# --- Resolve script directory so this works from anywhere ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Recommend a virtual environment (optional but cleaner) ---
echo "Creating a local virtual environment (.venv)..."
python3 -m venv "$SCRIPT_DIR/.venv"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/.venv/bin/activate"
echo "Activated: $SCRIPT_DIR/.venv"
echo ""

# --- Install dependencies from the pinned requirements file ---
echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies from requirements.txt..."
pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "=================================================="
echo "Installation Complete"
echo "=================================================="
echo ""
echo "To run the tool:"
echo "    source .venv/bin/activate      # if not already active"
echo "    sudo python3 wl_tool12.py      # sudo gives full wireless access"
echo ""
echo "Note: 'sudo' may bypass the virtual environment. If you hit"
echo "'ModuleNotFoundError' under sudo, run instead:"
echo "    sudo .venv/bin/python wl_tool12.py"
echo ""
echo "Documentation: README.md, START_HERE.md, QUICK_START.md"
echo "=================================================="
