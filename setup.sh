#!/usr/bin/env bash
#
# One-shot setup for the Zip Campaign Intelligence Agent demo.
# Run from anywhere:  bash /Users/jeffduffie/braze-agent/setup.sh
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Zip · Campaign Intelligence Agent — Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Verify dependencies are installed
echo "▸ Checking Python dependencies..."
python3 -m pip install --quiet --upgrade -r requirements.txt
echo "  ✓ Dependencies OK"
echo ""

# 2. Bootstrap .env from .env.example if missing
if [ ! -f .env ]; then
  cp .env.example .env
  echo "▸ Created fresh .env from template"
fi

# 3. Ensure ANTHROPIC_API_KEY line exists in .env
if ! grep -q "^ANTHROPIC_API_KEY=" .env; then
  echo "ANTHROPIC_API_KEY=" >> .env
  echo "▸ Added ANTHROPIC_API_KEY line to .env"
fi

# 4. Prompt for key if it's blank or still the placeholder
CURRENT_KEY=$(grep "^ANTHROPIC_API_KEY=" .env | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | xargs)
NEEDS_KEY=false
# Placeholder patterns we should reject
if [ -z "$CURRENT_KEY" ] \
   || [[ "$CURRENT_KEY" == *"..."* ]] \
   || [[ "$CURRENT_KEY" == *"YOUR_KEY"* ]] \
   || [[ "$CURRENT_KEY" == *"your-key"* ]] \
   || [[ "$CURRENT_KEY" == *"placeholder"* ]] \
   || [[ "$CURRENT_KEY" == *"YOUR-KEY"* ]] \
   || [ ${#CURRENT_KEY} -lt 50 ]; then
  NEEDS_KEY=true
fi

if [ "$NEEDS_KEY" = true ]; then
  echo "▸ Anthropic API key not yet set in .env"
  echo "  Get one at: https://console.anthropic.com/settings/keys"
  echo ""
  read -r -s -p "  Paste your sk-ant-... key (hidden input, press Enter when done): " USER_KEY
  echo ""

  if [ -z "$USER_KEY" ]; then
    echo "  ✗ No key entered. You can add it manually later:"
    echo "      Edit $PROJECT_DIR/.env and set ANTHROPIC_API_KEY=sk-ant-..."
    exit 1
  fi

  # Replace the existing line (BSD sed / macOS compatible)
  sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${USER_KEY}|" .env
  rm -f .env.bak
  chmod 600 .env
  echo "  ✓ Key saved to .env (file permissions locked to 600)"
else
  echo "▸ ANTHROPIC_API_KEY already set in .env ✓"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete. Launching app..."
echo "  → http://localhost:8501"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 5. Kill any old Streamlit on 8501, then launch fresh
pkill -f "streamlit run app.py" 2>/dev/null || true
sleep 1
exec python3 -m streamlit run app.py --server.port 8501
