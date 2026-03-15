"""
config/settings.py — SPECTER config loader.

Priority (highest wins):
  1. Environment variables
  2. ~/.config/specter/config.yaml
  3. Defaults

Example ~/.config/specter/config.yaml:
  nebius_api_key: eyJhb...
  tavily_api_key: tvly-...
  minimax_api_key: ...
  openrouter_api_key: ...
  stack: nvidia
  port: 8888
"""
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "specter" / "config.yaml"

_cfg: dict = {}


def load() -> dict:
    global _cfg
    if _cfg:
        return _cfg
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml
        with open(CONFIG_PATH) as f:
            _cfg = yaml.safe_load(f) or {}
    except ImportError:
        # fallback: simple key: value parser
        _cfg = {}
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                _cfg[k.strip()] = v.strip()
    except Exception as e:
        print(f"⚠️  Could not load {CONFIG_PATH}: {e}")
    return _cfg


def get(key: str, default=None):
    """Get value — env var takes priority over config file."""
    env_map = {
        "nebius_api_key":    "NEBIUS_API_KEY",
        "tavily_api_key":    "TAVILY_API_KEY",
        "minimax_api_key":   "MINIMAX_API_KEY",
        "openrouter_api_key":"OPENROUTER_API_KEY",
        "stack":             "SPECTER_STACK",
        "port":              "PORT",
        "image_path":        "IMAGE_PATH",
    }
    env_key = env_map.get(key)
    if env_key and os.environ.get(env_key):
        return os.environ[env_key]
    return load().get(key, default)


def apply_to_env():
    """Push all config values into os.environ so submodules pick them up."""
    mapping = {
        "nebius_api_key":    "NEBIUS_API_KEY",
        "tavily_api_key":    "TAVILY_API_KEY",
        "minimax_api_key":   "MINIMAX_API_KEY",
        "openrouter_api_key":"OPENROUTER_API_KEY",
        "stack":             "SPECTER_STACK",
    }
    cfg = load()
    for cfg_key, env_key in mapping.items():
        if cfg_key in cfg and not os.environ.get(env_key):
            os.environ[env_key] = str(cfg[cfg_key])
            print(f"   {env_key} ← config.yaml")
