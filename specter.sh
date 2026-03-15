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
