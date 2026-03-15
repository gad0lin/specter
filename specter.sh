#!/bin/bash
# specter.sh — LORE main launcher
# Usage: ./specter.sh [--stack nvidia|hybrid|auto] [--port 8888] [--image-path FILE] [init|scan]
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec uv run --with fastapi --with uvicorn --with openai --with tavily-python --with minimax --with requests \
  python "$SCRIPT_DIR/src/web/app.py" "$@"
