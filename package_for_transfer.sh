#!/bin/bash

# Packages the Wireless Diagnostic Suite into a single .zip for transfer
# to another Mac. Excludes generated test output, caches, and the venv so
# the archive stays small and clean.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
FOLDER_NAME="$(basename "$SCRIPT_DIR")"
STAMP="$(date +%Y%m%d)"
ARCHIVE="$PARENT_DIR/WiFi_Quality_transfer_${STAMP}.zip"

echo "Packaging '$FOLDER_NAME' -> $ARCHIVE"

cd "$PARENT_DIR"

# Build a zip of the project folder while excluding only regenerable/huge
# artifacts. Patterns use a leading */ so they match at any nesting depth
# (handles nested virtualenvs and git repos inside subfolders).
# NOTE: your test-output folders (RUN_*/SURVEY_*/COMPARATIVE_*) are KEPT,
# since they are small and you may want the collected data on the new Mac.
zip -r "$ARCHIVE" "$FOLDER_NAME" \
    -x "*/.venv/*" -x "$FOLDER_NAME/.venv/*" \
    -x "*/__pycache__/*" -x "$FOLDER_NAME/__pycache__/*" \
    -x "*.pyc" \
    -x "*/.git/*" -x "$FOLDER_NAME/.git/*" \
    -x "*.DS_Store"

echo ""
echo "Done. Archive created:"
echo "    $ARCHIVE"
echo ""
echo "Transfer that .zip to the new Mac (AirDrop / USB / cloud), then:"
echo "    unzip WiFi_Quality_transfer_${STAMP}.zip"
echo "    cd $FOLDER_NAME"
echo "    bash setup.sh"
