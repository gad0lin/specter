#!/bin/bash
# specter.sh — SPECTER main launcher
#
# Usage:
#   ./specter.sh                          # start dashboard (auto stack)
#   ./specter.sh --stack nvidia           # full NVIDIA stack
#   ./specter.sh --mode forensics         # forensics documentation mode
#   ./specter.sh --mode mystery           # Sherlock mystery game mode
#   ./specter.sh --image-path FILE        # scan a specific image
#   ./specter.sh init                     # first-time setup wizard
#   ./specter.sh scan FILE                # one-shot forensics scan
#
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR"

# Parse port from args
PORT=8081  # fixed port — matches cloudflare tunnel config

# Kill anything already on this port
if command -v lsof &>/dev/null; then
  OLD=$(lsof -ti:$PORT 2>/dev/null)
  [ -n "$OLD" ] && echo "   ⚠️  Killing process on :$PORT (pid $OLD)" && kill -9 $OLD 2>/dev/null
fi
args=("$@")
for i in "${!args[@]}"; do
  if [[ "${args[$i]}" == "--port" || "${args[$i]}" == "-p" ]]; then
    PORT="${args[$((i+1))]}"
  fi
done

# Start Cloudflare named tunnel if config exists
if command -v cloudflared &>/dev/null && [ -f "$HOME/.cloudflared/config.yml" ]; then
  echo "   🌐 Starting Cloudflare tunnel → specter.charlieverse.io"
  cloudflared tunnel run specter &>/tmp/specter-tunnel.log &
  sleep 2
fi

# uv run needs -- to separate its own flags from the app's flags
exec uv run \
  --with fastapi \
  --with "uvicorn[standard]" \
  --with openai \
  --with "tavily-python" \
  --with requests \
  --with httpx \
  --with python-dotenv \
  -- python "$SCRIPT_DIR/src/web/app.py" "$@"
