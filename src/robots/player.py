"""
robots/player.py — Player recognition and identity system.

Players register before the experience starts. Each gets:
- A unique visual token (colored badge, hat, lanyard pattern)
- A character role in the story (Watson, Inspector, Dr. Watson's associate...)
- Their progress tracked across all robots

When a robot's camera sees someone approaching:
- NIM vision checks: "Is this a registered player or a bystander?"
- If player: engage in character, remember their clue history
- If bystander: ignore, or give a generic "nothing to see here" deflection

This lets the experience run in a crowd (hackathon) without breaking
immersion — robots only "activate" for players wearing the token.

Player tokens: simple visual markers
  - Colored stickers on badge lanyards
  - Glow bracelets
  - Specific hat/item given at registration
  - QR code badge (robot can read it)
"""
import os
import json
import base64
from dataclasses import dataclass, field
from openai import OpenAI

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
NIM_MODEL = os.environ.get("NIM_MODEL", "Qwen/Qwen2-VL-72B-Instruct")


@dataclass
class Player:
    player_id: str
    name: str                        # "Watson", "Inspector Chen", etc.
    role: str                        # their story role
    token_description: str           # "red sticker on badge", "glow bracelet"
    clues_found: list[str] = field(default_factory=list)
    robots_visited: list[str] = field(default_factory=list)
    profile: dict = field(default_factory=dict)  # NIM-sensed profile
    active: bool = True


# Global player registry
_players: dict[str, Player] = {}


def register_player(name: str, role: str, token: str = "red badge sticker") -> Player:
    """Register a player before the experience starts."""
    import uuid
    player = Player(
        player_id=str(uuid.uuid4())[:8],
        name=name,
        role=role,
        token_description=token,
    )
    _players[player.player_id] = player
    print(f"🎭 Player registered: {name} ({role}) — token: {token}")
    return player


def get_all_players() -> list[Player]:
    return list(_players.values())


TOKEN_DETECT_PROMPT = """Look at this person approaching a robot in an interactive experience.

Registered player tokens to look for: {tokens}

Answer in JSON:
{{
  "is_player": true/false,
  "confidence": "high|medium|low",
  "token_seen": "description of what you see or null",
  "player_description": "brief appearance note for cross-robot recognition"
}}

If no player token visible → is_player: false. Bystanders should be ignored.
Return ONLY valid JSON."""


def identify_approaching_person(image_bytes: bytes) -> dict:
    """
    NIM vision checks if approaching person is a registered player.
    Returns identification result.
    """
    if not _players:
        return {"is_player": True, "confidence": "high", "token_seen": "demo mode"}

    tokens = [f"{p.name}: {p.token_description}" for p in _players.values()]
    prompt = TOKEN_DETECT_PROMPT.format(tokens="\n".join(tokens))

    b64 = base64.b64encode(image_bytes).decode()
    client = OpenAI(base_url="https://api.studio.nebius.com/v1", api_key=NEBIUS_API_KEY)

    try:
        resp = client.chat.completions.create(
            model=NIM_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            max_tokens=200,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"⚠️  Player ID failed: {e}")
        return {"is_player": True, "confidence": "low", "token_seen": None}


BYSTANDER_DEFLECTIONS = [
    "I'm afraid I'm rather occupied at the moment. Do carry on.",
    "Nothing to see here. Move along, please.",
    "I'm... waiting for someone. Excuse me.",
    "*looks away and pretends to examine something interesting*",
]


def bystander_deflection() -> str:
    import random
    return random.choice(BYSTANDER_DEFLECTIONS)
