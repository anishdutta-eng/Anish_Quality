#!/bin/bash
# =============================================================
#  WiFi Diagnostic Suite — One-Click Launcher (macOS)
#
#  HOW TO USE:
#    Just double-click this file in Finder.
#    The first run sets everything up automatically.
# =============================================================

# Always run from the folder this script lives in
cd "$(dirname "$0")" || exit 1

clear
echo "=================================================="
echo "   WiFi Diagnostic Suite"
echo "=================================================="
echo ""

# --- 0. Make sure we're in the real package folder ---
if [ ! -f "requirements.txt" ] || [ ! -f "wl_tool12.py" ]; then
    echo "ERROR: This launcher must stay inside the WiFiDiagnosticSuite folder."
    echo "       (requirements.txt and wl_tool12.py must be next to it.)"
    echo ""
    echo "Current folder: $(pwd)"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

# --- 1. Check Python 3 ---
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed on this Mac."
    echo ""
    echo "Please install it first:"
    echo "  - Easiest: download from https://www.python.org/downloads/"
    echo "  - Or with Homebrew:  brew install python3"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

VENV_PY="$(pwd)/.venv/bin/python3"

# --- 2. Create venv if missing ---
if [ ! -x "$VENV_PY" ]; then
    echo "First-time setup — creating an isolated environment..."
    python3 -m venv .venv || { echo "Failed to create environment."; read -p "Press Enter..."; exit 1; }
fi

# --- 3. Verify dependencies; install if anything is missing ---
# Check the REQUIRED modules only. CoreWLAN is the macOS WiFi binding the tool
# needs; sklearn/joblib are optional (only the offline viewer uses them) so they
# must NOT gate this check, otherwise a failed optional install would make the
# launcher re-download everything on every start.
REQUIRED_IMPORTS="import speedtest, numpy, matplotlib, scipy, reportlab, plotly, CoreWLAN"
if ! "$VENV_PY" -c "$REQUIRED_IMPORTS" 2>/dev/null; then
    echo "Installing what the tool needs (one time, a few minutes)..."
    echo ""
    "$VENV_PY" -m pip install --upgrade pip >/dev/null
    if ! "$VENV_PY" -m pip install -r requirements.txt; then
        echo ""
        echo "ERROR: Dependency installation failed. Check your internet connection"
        echo "       and try again."
        read -p "Press Enter to close..."
        exit 1
    fi
    # Verify again
    if ! "$VENV_PY" -c "$REQUIRED_IMPORTS" 2>/dev/null; then
        echo ""
        echo "ERROR: Some dependencies are still missing after install."
        "$VENV_PY" -c "$REQUIRED_IMPORTS" 2>&1 | tail -3
        read -p "Press Enter to close..."
        exit 1
    fi
    # macOS certificate fix for speedtest (best effort)
    CERT_CMD=$(ls /Applications/Python*/Install\ Certificates.command 2>/dev/null | head -n1 || true)
    [ -n "$CERT_CMD" ] && "$CERT_CMD" >/dev/null 2>&1 || true
    echo ""
    echo "Setup complete!"
    echo ""
fi

# --- 4. Launch the tool ---
echo "Starting the WiFi tool..."
echo "(You may be asked for your Mac password — this lets the tool read WiFi details.)"
echo ""

# wl_tool12.py needs sudo for full WiFi telemetry via wdutil.
# Use the venv's python so dependencies are available under sudo.
sudo "$VENV_PY" wl_tool12.py

echo ""
echo "=================================================="
echo "  Done. You can close this window."
echo "=================================================="
read -p "Press Enter to close..."
