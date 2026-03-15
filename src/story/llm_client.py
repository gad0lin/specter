"""
story/llm_client.py — Unified LLM client factory.

Returns an OpenAI-compatible client pointed at the right backend:
  LLM_BACKEND=nvidia  → integrate.api.nvidia.com (NVIDIA NIM)
  LLM_BACKEND=nebius  → api.studio.nebius.com (Nebius Token Factory)
  LLM_BACKEND=openrouter → openrouter.ai (fallback)
"""
import os
from openai import OpenAI


def get_client() -> tuple[OpenAI, str]:
    """Returns (client, model_id)."""
    backend = os.environ.get("LLM_BACKEND", "nebius").lower()
    model = os.environ.get("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

    if backend == "nvidia":
        api_key = os.environ.get("NVIDIA_API_KEY", "")
        base_url = os.environ.get("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        return OpenAI(base_url=base_url, api_key=api_key), model

    if backend == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key), model

    # Default: Nebius
    api_key = os.environ.get("NEBIUS_API_KEY", "")
    return OpenAI(base_url="https://api.studio.nebius.com/v1", api_key=api_key), model
