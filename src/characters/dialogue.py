"""
characters/dialogue.py — Character dialogue generation.

When a visitor speaks to a robot, this generates an in-character response
using Nebius Token Factory (Llama-3.3-70B).

The character:
- Stays in role always
- Reveals clues naturally in conversation
- Never breaks immersion
- Has a consistent personality
"""
import os
from openai import OpenAI
from src.story.generator import Character, StoryWorld

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1"


def _client() -> OpenAI:
    return OpenAI(base_url=NEBIUS_BASE_URL, api_key=NEBIUS_API_KEY)


def respond(
    character: Character,
    story: StoryWorld,
    visitor_message: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Generate an in-character response to a visitor's message.

    Args:
        character:            The robot's character
        story:                Full story world context
        visitor_message:      What the visitor said
        conversation_history: Previous turns [{"role": "user/assistant", "content": "..."}]

    Returns:
        Character's spoken response (2-4 sentences)
    """
    history = conversation_history or []

    system = f"""You are {character.name}, a character in an immersive mystery experience.

STORY: {story.premise}
MYSTERY: {story.mystery}
YOUR ROLE: {character.role}
YOUR PERSONALITY: {character.personality}
YOUR SECRET (never reveal directly): {character.secret}
CLUES YOU CAN DROP: {', '.join(character.clues)}

RULES:
- Stay in character at ALL times. Never break immersion.
- Speak in 2-4 sentences maximum — this is real-time robot speech.
- You can hint at clues but never confess directly.
- Be evasive, dramatic, or helpful based on your personality.
- Reference specific objects/details from the space when relevant.
- End with something that makes the visitor want to talk to another robot.

Setting: {story.setting}"""

    messages = [{"role": "system", "content": system}]
    messages.extend(history[-6:])  # last 3 turns
    messages.append({"role": "user", "content": visitor_message})

    client = _client()
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=150,
        temperature=0.85,
    )
    return resp.choices[0].message.content.strip()


def generate_intro(character: Character, story: StoryWorld) -> str:
    """
    Generate the robot's opening line when a visitor approaches.
    """
    prompt = f"""You are {character.name} ({character.role}) in a mystery: {story.premise}
Your personality: {character.personality}

Generate ONE short opening line (1-2 sentences) to say when someone approaches you.
Be mysterious, in-character, and make them want to ask questions.
Return ONLY the spoken line, no quotes."""

    client = _client()
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80,
        temperature=0.9,
    )
    return resp.choices[0].message.content.strip()
