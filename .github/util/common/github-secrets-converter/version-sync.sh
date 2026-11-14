#!/bin/bash
# version-sync.sh - sync the version from version.json into the HTML file

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/version.json"
HTML_FILE="$SCRIPT_DIR/secrets-converter.html"

# Extract the version from version.json
VERSION=$(grep -o '"version": *"[^"]*"' "$VERSION_FILE" | cut -d'"' -f4)

if [ -z "$VERSION" ]; then
    echo "Error: Could not extract version from version.json"
    exit 1
fi

echo "Syncing version $VERSION to HTML file..."

# Update the version in the HTML file (meta tag and footer)
if [ -f "$HTML_FILE" ]; then
    # sed command compatible with macOS and Linux
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/content=\"[0-9]*\.[0-9]*\.[0-9]*\"/content=\"$VERSION\"/g" "$HTML_FILE"
        sed -i '' "s/v[0-9]*\.[0-9]*\.[0-9]*/v$VERSION/g" "$HTML_FILE"
    else
        sed -i "s/content=\"[0-9]*\.[0-9]*\.[0-9]*\"/content=\"$VERSION\"/g" "$HTML_FILE"
        sed -i "s/v[0-9]*\.[0-9]*\.[0-9]*/v$VERSION/g" "$HTML_FILE"
    fi
    echo "Successfully updated $HTML_FILE to version $VERSION"
else
    echo "Warning: HTML file not found at $HTML_FILE"
fi
