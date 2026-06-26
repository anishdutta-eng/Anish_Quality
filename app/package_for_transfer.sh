#!/bin/bash

# Packages the Wireless Diagnostic Suite into a single .zip for transfer
# to another Mac. Excludes generated test output, caches, and the venv so
# the archive stays small and clean.

set -e

# This script lives in <project_root>/app/. We package the WHOLE project folder
# (the parent of app/), not just app/, so the launcher, floorplans and docs are
# included.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GRANDPARENT_DIR="$(dirname "$PROJECT_ROOT")"
FOLDER_NAME="$(basename "$PROJECT_ROOT")"
STAMP="$(date +%Y%m%d)"
ARCHIVE="$GRANDPARENT_DIR/WiFi_Quality_transfer_${STAMP}.zip"

echo "Packaging '$FOLDER_NAME' -> $ARCHIVE"

cd "$GRANDPARENT_DIR"

# Build a zip of the project folder while excluding only regenerable/huge
# artifacts. Patterns use a leading */ so they match at any nesting depth
# (handles nested virtualenvs and git repos inside subfolders).
# Generated output (Results/, RUN_*/SURVEY_*/COMPARATIVE_*) is excluded so the
# archive stays small; the new machine regenerates output by running the tool.
zip -r "$ARCHIVE" "$FOLDER_NAME" \
    -x "*/.venv/*" -x "$FOLDER_NAME/.venv/*" \
    -x "*/__pycache__/*" -x "$FOLDER_NAME/__pycache__/*" \
    -x "*.pyc" \
    -x "*/.git/*" -x "$FOLDER_NAME/.git/*" \
    -x "$FOLDER_NAME/Results/*" \
    -x "$FOLDER_NAME/RUN_*" -x "$FOLDER_NAME/SURVEY_*" -x "$FOLDER_NAME/COMPARATIVE_*" \
    -x "*.DS_Store"

echo ""
echo "Done. Archive created:"
echo "    $ARCHIVE"
echo ""
echo "Transfer that .zip to the new Mac (AirDrop / USB / cloud), then:"
echo "    unzip WiFi_Quality_transfer_${STAMP}.zip"
echo "    cd $FOLDER_NAME"
echo "    double-click 'Start WiFi Tool.command'  (or: bash app/setup.sh)"
