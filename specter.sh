#!/bin/bash
# specter.sh — SPECTER one-command launcher
#
# First time:  ./specter.sh init
# Demo:        ./specter.sh
# NVIDIA mode: ./specter.sh --stack nvidia
#
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR"

# ── Config check ───────────────────────────────────────────────────────────────
CONFIG="$HOME/.config/specter/config.yaml"
if [ ! -f "$CONFIG" ] && [ "$1" != "init" ]; then
  echo ""
  echo "  ⚠️  No config found. Run: ./specter.sh init"
  echo ""
  exit 1
fi

# ── Init wizard ────────────────────────────────────────────────────────────────
if [ "$1" = "init" ]; then
  mkdir -p "$HOME/.config/specter"
  echo ""
  echo "🔮 SPECTER Setup"
  echo ""
  read -p "  Nebius API key: " NEBIUS
  read -p "  Tavily API key: " TAVILY
  read -p "  MiniMax API key (optional, press enter to skip): " MINIMAX
  cat > "$CONFIG" << YAML
nebius_api_key: $NEBIUS
tavily_api_key: $TAVILY
minimax_api_key: $MINIMAX
stack: nvidia
port: 8081
YAML
  echo ""
  echo "  ✅ Config saved to $CONFIG"
  echo "  Run: ./specter.sh"
  echo ""
  exit 0
fi

# ── Port ───────────────────────────────────────────────────────────────────────
PORT=8081
for i in "$@"; do [[ "$i" == "--port" ]] && shift && PORT="$1"; done

# Kill old process on port (macOS-compatible)
lsof -ti:$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# ── Cloudflare tunnel ─────────────────────────────────────────────────────────
if command -v cloudflared &>/dev/null && [ -f "$HOME/.cloudflared/config.yml" ]; then
  cloudflared tunnel run specter &>/tmp/specter-tunnel.log &
  sleep 1
  echo "   🌐 https://specter.charlieverse.io"
fi

# ── Launch ─────────────────────────────────────────────────────────────────────
exec uv run \
  --with fastapi \
  --with "uvicorn[standard]" \
  --with openai \
  --with "tavily-python" \
  --with requests \
  --with httpx \
  --with python-dotenv \
  -- python "$SCRIPT_DIR/src/web/app.py" "$@"
