"""
scan/visitor.py — Visitor sensing and tracking.

When someone approaches a robot, NIM vision:
1. Describes their appearance (for cross-robot recognition)
2. Estimates their emotional state (nervous? confident? curious?)
3. Notes what they're carrying, wearing, doing
4. Shares this profile with ALL robots in the mesh

This lets robots "gossip" about Watson — each character knows
who they're dealing with and can react accordingly.

Holmes: "Ah, I see from your lanyard you work in AI — and that coffee
        stain suggests you've been here since the doors opened."
"""
import os
import json
import base64
from openai import OpenAI

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
NIM_MODEL = os.environ.get("NIM_MODEL", "Qwen/Qwen2-VL-72B-Instruct")

VISITOR_PROMPT = """Analyze this person approaching a robot for an immersive mystery experience.
Return a JSON profile for other robots to use in conversation:
{
  "appearance": "brief physical description (clothing, notable items)",
  "carries": ["items they have (badge, laptop, coffee, etc.)"],
  "mood": "calm|curious|excited|nervous|tired",
  "body_language": "brief observation (leaning in, arms crossed, etc.)",
  "deduction": "one Sherlock-style deduction about them (job, habits, mood)",
  "engagement": "high|medium|low"
}
Be observational, not invasive. Focus on what's useful for storytelling.
Return ONLY valid JSON."""


def sense_visitor(image_bytes: bytes) -> dict:
    """
    Analyze a visitor approaching the robot.
    Returns a profile dict shared across the robot mesh.
    """
    b64 = base64.b64encode(image_bytes).decode()
    client = OpenAI(base_url="https://api.studio.nebius.com/v1", api_key=NEBIUS_API_KEY)

    try:
        resp = client.chat.completions.create(
            model=NIM_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": VISITOR_PROMPT},
            ]}],
            max_tokens=300,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"⚠️  Visitor sensing failed: {e}")
        return {"mood": "curious", "deduction": "A keen investigator, no doubt.", "engagement": "high"}


def visitor_context_for_character(visitor_profile: dict, character_name: str) -> str:
    """
    Format visitor profile as context injection for character dialogue.
    """
    if not visitor_profile:
        return ""
    parts = []
    if visitor_profile.get("appearance"):
        parts.append(f"Visitor appearance: {visitor_profile['appearance']}")
    if visitor_profile.get("deduction"):
        parts.append(f"Holmes-style deduction: {visitor_profile['deduction']}")
    if visitor_profile.get("mood"):
        parts.append(f"Their mood: {visitor_profile['mood']}")
    if visitor_profile.get("carries"):
        parts.append(f"They carry: {', '.join(visitor_profile['carries'])}")
    return "\n".join(parts)
