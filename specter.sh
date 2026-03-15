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

# Extract port from args for tunnel
PORT=8888
for i in "$@"; do
  case $i in --port=*) PORT="${i#*=}" ;; esac
done
for i in "$@"; do
  case $i in --port) shift; PORT="$1" ;; esac
done

# Start Cloudflare tunnel in background if cloudflared is available
if command -v cloudflared &>/dev/null; then
  echo "   🌐 Starting Cloudflare tunnel..."
  cloudflared tunnel --url "http://localhost:$PORT" --no-autoupdate 2>&1 | \
    grep -E "trycloudflare.com|https://" | head -1 | \
    awk '{print "   Public: " $NF}' &
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
