#!/usr/bin/env bash
set -e

echo "🏛️ Installing Agent Live Browser..."

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[-] Python3 not found. Please install Python 3.9+."
    exit 1
fi

# Install dependencies
echo "[*] Installing Python dependencies..."
pip install -r "$(dirname "$0")/requirements.txt"

# Install Playwright Chromium if missing
echo "[*] Ensuring Playwright Chromium is installed..."
python3 -m playwright install chromium

# Register as agent skill if directories exist
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.gemini/config/skills" "$HOME/.agents/skills"

echo "[*] Linking skill to agent directories..."
ln -sfn "$SKILL_DIR" "$HOME/.gemini/config/skills/agent-live-browser"
ln -sfn "$SKILL_DIR" "$HOME/.agents/skills/agent-live-browser"

echo ""
echo "✅ Installation complete!"
echo "👉 Start browser: python3 $SKILL_DIR/scripts/agent_browser.py start"
echo "👉 Web UI stream: http://localhost:7654"
