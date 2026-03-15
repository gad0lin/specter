"""
voice/ace_avatar.py — NVIDIA ACE Avatar integration.

Uses NVIDIA ACE Audio2Face-3D NIM to generate facial animation
from character audio. Falls back to CSS animation in dashboard.

NIM endpoint: https://ai.api.nvidia.com/v1/avatar/nvidia/audio2face-3d
"""
import os
import base64
import requests

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
A2F_URL = "https://ai.api.nvidia.com/v1/avatar/nvidia/audio2face-3d"

# Avatar styles per role → CSS + SVG face configuration
AVATAR_CONFIGS = {
    "detective": {
        "color": "#6366f1",
        "hat": True,
        "expression": "focused",
        "pipe": True,
    },
    "suspect": {
        "color": "#c93030",
        "hat": False,
        "expression": "nervous",
        "sweat": True,
    },
    "witness": {
        "color": "#2563eb",
        "hat": False,
        "expression": "surprised",
    },
    "red_herring": {
        "color": "#d97706",
        "hat": False,
        "expression": "defensive",
        "collar": True,
    },
    "informant": {
        "color": "#059669",
        "hat": True,
        "expression": "sly",
        "hood": True,
    },
}


def get_avatar_svg(role: str, name: str, speaking: bool = False) -> str:
    """
    Generate an SVG avatar face for a character role.
    Used in dashboard when ACE Audio2Face is not available.
    """
    cfg = AVATAR_CONFIGS.get(role, AVATAR_CONFIGS["witness"])
    color = cfg["color"]
    anim = 'animation:speak 0.15s ease-in-out infinite alternate;' if speaking else ''

    expressions = {
        "focused":   ("M35,55 Q48,50 61,55", "M42,42 L44,38 M52,38 L54,42"),  # neutral brow, focused
        "nervous":   ("M38,58 Q48,54 58,58", "M40,40 Q48,44 56,40"),           # slight frown, raised brows
        "surprised": ("M38,52 Q48,60 58,52", "M40,36 Q48,32 56,36"),           # open mouth, high brows
        "defensive": ("M36,56 Q48,52 60,56", "M42,42 Q48,46 54,42"),           # thin line, furrowed
        "sly":       ("M36,54 Q48,50 62,56", "M40,42 L45,40 M51,40 L56,42"),   # smirk, one raised brow
    }

    mouth, brow = expressions.get(cfg.get("expression","focused"), expressions["focused"])
    mouth_anim = f'style="{anim}"' if speaking else ""

    extras = ""
    if cfg.get("hat"):
        extras += f'<rect x="26" y="18" width="44" height="8" rx="3" fill="{color}" opacity="0.9"/><rect x="22" y="24" width="52" height="5" rx="2" fill="{color}"/>'
    if cfg.get("hood"):
        extras += f'<path d="M20,30 Q20,16 48,16 Q76,16 76,30 L72,34 Q68,22 48,22 Q28,22 24,34Z" fill="{color}" opacity="0.7"/>'
    if cfg.get("pipe"):
        extras += '<path d="M58,62 L68,60 L70,64 L60,66Z" fill="#8B6F47"/><line x1="70" y1="62" x2="76" y2="58" stroke="#8B6F47" stroke-width="2"/>'
    if cfg.get("sweat"):
        extras += '<ellipse cx="66" cy="44" rx="3" ry="5" fill="#93c5fd" opacity="0.7"/>'
    if cfg.get("collar"):
        extras += f'<path d="M32,75 L40,68 L48,72 L56,68 L64,75" stroke="{color}" stroke-width="2" fill="none"/>'

    return f'''<svg viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">
  <style>@keyframes speak {{0%{{transform:scaleY(1)}}100%{{transform:scaleY(0.7)}}}}</style>
  <!-- Head -->
  <ellipse cx="48" cy="52" rx="26" ry="30" fill="#fde8d8"/>
  <ellipse cx="48" cy="36" rx="26" ry="22" fill="#fde8d8"/>
  <!-- Extras (hat/hood/etc) -->
  {extras}
  <!-- Eyes -->
  <ellipse cx="38" cy="44" rx="5" ry="5.5" fill="white"/>
  <ellipse cx="58" cy="44" rx="5" ry="5.5" fill="white"/>
  <circle cx="39" cy="44" r="3" fill="{color}"/>
  <circle cx="59" cy="44" r="3" fill="{color}"/>
  <circle cx="40" cy="43" r="1" fill="white"/>
  <circle cx="60" cy="43" r="1" fill="white"/>
  <!-- Brows -->
  <g stroke="{color}" stroke-width="2.5" stroke-linecap="round" fill="none">
    <path d="{brow}"/>
  </g>
  <!-- Mouth -->
  <g {mouth_anim}>
    <path d="{mouth}" stroke="#c0715a" stroke-width="2" fill="none" stroke-linecap="round"/>
  </g>
  <!-- Nose -->
  <ellipse cx="48" cy="54" rx="2.5" ry="2" fill="#e8c4a0"/>
  <!-- Role badge -->
  <rect x="0" y="84" width="96" height="12" fill="{color}" rx="0"/>
  <text x="48" y="93" text-anchor="middle" fill="white" font-size="7" font-family="sans-serif" font-weight="bold">{name[:16].upper()}</text>
</svg>'''


def animate_with_ace(audio_bytes: bytes, text: str) -> dict | None:
    """
    Send audio to NVIDIA ACE Audio2Face-3D NIM.
    Returns blendshape animation data for face rendering.
    Falls back to None if not available.
    """
    if not NVIDIA_API_KEY:
        return None

    try:
        audio_b64 = base64.b64encode(audio_bytes).decode()
        resp = requests.post(
            A2F_URL,
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "audio": audio_b64,
                "text": text,
                "face_params": {
                    "emotion_strength": 0.8,
                    "blink_rate": 0.3,
                },
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"⚠️  ACE Audio2Face failed: {e}")

    return None
