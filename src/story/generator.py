"""
story/generator.py — Story world generation from scanned space.

Takes the scan results (objects, atmosphere, interesting items) and:
1. Searches for real context via Tavily
2. Uses Nebius Token Factory (Llama-3.3-70B) to generate the story
3. Assigns characters to robots

Output: StoryWorld with characters, clues, dialogue starters
"""
import os
import json
from dataclasses import dataclass, field
from openai import OpenAI

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1"


@dataclass
class Character:
    name: str
    role: str               # detective | suspect | witness | guide
    personality: str        # e.g. "nervous, evasive, speaks in riddles"
    secret: str             # what they know but won't say directly
    voice_tone: str         # for TTS: "anxious male adult"
    clues: list[str] = field(default_factory=list)
    robot_id: str = ""      # assigned robot


@dataclass
class StoryWorld:
    title: str
    genre: str              # mystery | thriller | adventure | comedy
    setting: str            # description of the space as story backdrop
    premise: str            # 2-sentence setup
    mystery: str            # what needs to be solved
    solution: str           # the answer (hidden from players)
    characters: list[Character] = field(default_factory=list)
    clues: list[str] = field(default_factory=list)
    atmosphere: str = ""


def _llm_client() -> OpenAI:
    return OpenAI(base_url=NEBIUS_BASE_URL, api_key=NEBIUS_API_KEY)


def _search_context(interesting_items: list[str]) -> str:
    """Use Tavily to find real-world context for interesting items."""
    if not TAVILY_API_KEY or not interesting_items:
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        query = f"interesting facts about: {', '.join(interesting_items[:3])}"
        result = client.search(query=query, search_depth="basic", max_results=3, include_answer=True)
        return result.get("answer", "") or ""
    except Exception as e:
        print(f"⚠️  Tavily search failed: {e}")
        return ""


def generate_story(scan_results: list[dict], num_robots: int = 3) -> StoryWorld:
    """
    Generate a complete story world from space scan results.
    
    Args:
        scan_results:  List of scan dicts from vision.scan_frame()
        num_robots:    Number of robots available = number of characters
    
    Returns:
        StoryWorld with characters, clues, mystery
    """
    # Aggregate scan results
    all_objects = []
    all_interesting = []
    atmosphere = ""
    room_type = ""
    for s in scan_results:
        all_objects.extend(s.get("objects", []))
        all_interesting.extend(s.get("interesting", []))
        atmosphere = atmosphere or s.get("atmosphere", "")
        room_type = room_type or s.get("room_type", "")

    # Get real context via Tavily
    print("🔍 Searching real context via Tavily...")
    context = _search_context(all_interesting[:4])

    # Build story generation prompt
    prompt = f"""You are a creative director generating an immersive, interactive mystery experience.

SPACE SCANNED:
- Room type: {room_type}
- Atmosphere: {atmosphere}  
- Notable objects: {', '.join(list(set(all_objects))[:15])}
- Most interesting: {', '.join(list(set(all_interesting))[:6])}
- Real context found: {context[:400] if context else 'none'}

REQUIREMENTS:
- {num_robots} robots are available, each becomes ONE character
- Genre: mystery (murder, theft, or secret)
- Story must be grounded in the ACTUAL objects/space found
- Each character has a secret related to the mystery
- Players collect clues by talking to each robot character

Return ONLY this JSON:
{{
  "title": "short evocative title",
  "genre": "mystery",
  "setting": "2-sentence description of this space as story backdrop",
  "premise": "2-sentence story setup",
  "mystery": "what needs to be solved (1 sentence)",
  "solution": "the answer — who did what and why (kept secret from players)",
  "atmosphere": "3 adjectives",
  "characters": [
    {{
      "name": "character name",
      "role": "detective|suspect|witness",
      "personality": "3 personality traits",
      "secret": "what they know but hide",
      "voice_tone": "description for TTS casting",
      "clues": ["clue they'll reveal", "another clue"]
    }}
  ],
  "clues": ["overall clue list for tracking progress"]
}}

Generate exactly {num_robots} characters. Make it compelling and specific to THIS space."""

    print(f"✨ Generating story via Nebius ({LLM_MODEL})...")
    client = _llm_client()
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.8,
    )

    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json").strip()

    data = json.loads(raw)
    characters = [Character(**c) for c in data.get("characters", [])]

    return StoryWorld(
        title=data["title"],
        genre=data["genre"],
        setting=data["setting"],
        premise=data["premise"],
        mystery=data["mystery"],
        solution=data["solution"],
        atmosphere=data.get("atmosphere", ""),
        characters=characters,
        clues=data.get("clues", []),
    )


def assign_robots(story: StoryWorld, robot_ids: list[str]) -> StoryWorld:
    """Assign robot IDs to characters."""
    for i, char in enumerate(story.characters):
        if i < len(robot_ids):
            char.robot_id = robot_ids[i]
    return story
