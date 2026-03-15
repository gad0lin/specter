"""
scan/vision.py — Space scanning via NVIDIA NIM vision.

Takes a camera frame, returns a structured description:
  - objects identified
  - text visible
  - room type / atmosphere
  - interesting items for story generation

Backend: NIM (Qwen2-VL-72B via Nebius GPU) | fallback: OpenRouter
"""
import os
import base64
import json
from openai import OpenAI

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
NIM_MODEL = os.environ.get("NIM_MODEL", "meta/llama-3.2-90b-vision-instruct")

SCAN_PROMPT = """You are scanning a physical space for a real-time story generation system.
Analyze this image and return a JSON object with:
{
  "room_type": "brief description of the space",
  "atmosphere": "mood/vibe in 5 words",
  "objects": ["list", "of", "notable", "objects"],
  "text_visible": ["any", "readable", "text", "signs", "whiteboards"],
  "people_count": 0,
  "interesting": ["top 3 most story-worthy elements"],
  "coordinates": {"x": 0.5, "y": 0.5}
}
Be specific. Focus on unique, story-worthy details. Return ONLY valid JSON."""


def _client_nim():
    # Prefer NVIDIA API (has Llama-3.2-90B Vision), fall back to Nebius
    if NVIDIA_API_KEY:
        return OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=NVIDIA_API_KEY,
        )
    return OpenAI(
        base_url="https://api.studio.nebius.com/v1",
        api_key=NEBIUS_API_KEY,
    )


def _client_openrouter():
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )


def scan_frame(image_bytes: bytes, location_hint: str = "") -> dict:
    """
    Scan a camera frame and return structured scene description.
    
    Args:
        image_bytes:   JPEG frame bytes
        location_hint: e.g. "north corner", "entrance"
    
    Returns:
        dict with objects, atmosphere, interesting items, etc.
    """
    b64 = base64.b64encode(image_bytes).decode()
    prompt = SCAN_PROMPT
    if location_hint:
        prompt += f"\n\nLocation hint: {location_hint}"

    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": prompt},
    ]

    # Try NIM first, fall back to OpenRouter
    clients = []
    if NEBIUS_API_KEY:
        clients.append((_client_nim(), NIM_MODEL, "NIM"))
    if OPENROUTER_API_KEY:
        clients.append((_client_openrouter(), "qwen/qwen2-vl-72b-instruct", "OpenRouter"))

    if not clients:
        raise RuntimeError("No API keys set — need NEBIUS_API_KEY or OPENROUTER_API_KEY")

    last_err = None
    for client, model, label in clients:
        try:
            print(f"👁 Scanning via {label} ({model})...")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                max_tokens=512,
                temperature=0.2,
            )
            raw = resp.choices[0].message.content.strip()
            # Extract JSON even if wrapped in markdown
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            return json.loads(raw)
        except Exception as e:
            print(f"⚠️  {label} failed: {e}")
            last_err = e

    raise RuntimeError(f"All vision backends failed: {last_err}")


def scan_text(image_bytes: bytes) -> str:
    """Quick OCR — just return readable text from image."""
    b64 = base64.b64encode(image_bytes).decode()
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": "Read all visible text in this image. Return only the text, nothing else."},
    ]
    client = _client_nim() if NEBIUS_API_KEY else _client_openrouter()
    model = NIM_MODEL if NEBIUS_API_KEY else "qwen/qwen2-vl-72b-instruct"
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=256,
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()
