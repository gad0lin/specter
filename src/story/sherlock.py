"""
story/sherlock.py — Sherlock Holmes themed story engine for LORE.

Generates a Holmesian mystery set in the ACTUAL scanned space.
The robot playing Holmes is the "guide" — deductive, theatrical, brilliant.
Other robots are suspects, witnesses, victims' associates.

The visitor IS Watson — they follow Holmes (the robot) collecting clues.
"""
import os
import json
from dataclasses import dataclass, field
from openai import OpenAI

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1"

SHERLOCK_SYSTEM = """You are the story director for an immersive Sherlock Holmes mystery experience.
The mystery is set in a REAL physical space — a modern hackathon venue.
Holmes speaks with Victorian wit but references modern technology naturally.
Every clue must connect to real objects found in the space scan.
The mystery should be solvable — players collect 4-5 clues to name the culprit."""

SHERLOCK_PROMPT = """Design a Sherlock Holmes mystery for this space:

SPACE DETAILS:
{space_details}

ROBOTS AVAILABLE: {num_robots}

Create a mystery where:
- ROBOT 0 = Sherlock Holmes (detective guide, brilliant, theatrical, deductive)
- ROBOT 1 = Primary Suspect (nervous, clearly hiding something)
- ROBOT 2 = Key Witness (oblivious to importance of what they saw)
- ROBOT 3 = Secondary Suspect / Red Herring (misleads Watson, seems guilty but isn't)
- ROBOT 4 = Holmes's Informant (street-smart contact, drops cryptic clues for a price)
- ROBOT 5+ = Additional characters if more robots available

The visitor plays WATSON — they walk between robots collecting clues.

Return this JSON exactly:
{{
  "title": "The Adventure of [something from the space]",
  "victim": "who/what was stolen or harmed",
  "culprit": "the name of the guilty robot character (secret)",
  "motive": "why they did it",
  "method": "how they did it (uses objects from the space)",
  "premise": "2 sentences Holmes would say to open the case",
  "mystery_question": "What Watson must discover (1 sentence)",
  "characters": [
    {{
      "name": "Sherlock Holmes",
      "role": "detective",
      "personality": "brilliant, theatrical, uses deduction, speaks in revelations",
      "secret": "already knows the culprit but needs Watson to confirm evidence",
      "voice_tone": "commanding authoritative British male",
      "clues": ["deductive observation they share", "cryptic hint toward culprit"],
      "intro": "opening line Holmes says when approached"
    }},
    {{
      "name": "[suspect name]",
      "role": "suspect",
      "personality": "describe their manner of guilt-concealment",
      "secret": "what they actually did or know",
      "voice_tone": "nervous evasive adult",
      "clues": ["suspicious detail they accidentally reveal", "alibi with a hole in it"],
      "intro": "their opening line when approached",
      "avatar_style": "nervous, shifty eyes, formal clothes"
    }},
    {{
      "name": "[witness name]",
      "role": "witness",
      "personality": "describe their obliviousness to importance of what they saw",
      "secret": "the key observation they don't know matters",
      "voice_tone": "casual friendly helpful adult",
      "clues": ["innocent-sounding observation that is actually critical", "timing detail"],
      "intro": "their opening line when approached",
      "avatar_style": "friendly, open face, casual attire"
    }},
    {{
      "name": "[red herring name]",
      "role": "red_herring",
      "personality": "suspicious-seeming but actually innocent, defensive",
      "secret": "they look guilty because of an unrelated secret (embarrassing, not criminal)",
      "voice_tone": "defensive indignant adult",
      "clues": ["misleading clue that points wrong direction", "real but irrelevant secret that explains their behavior"],
      "intro": "defensive opening — they know they look suspicious",
      "avatar_style": "anxious, overdressed, constantly checking phone"
    }},
    {{
      "name": "[informant name]",
      "role": "informant",
      "personality": "street-smart, mercenary, will share info for something in return",
      "secret": "saw the actual crime but won't say without being asked the right way",
      "voice_tone": "sly knowing adult",
      "clues": ["cryptic hint that requires follow-up", "direct clue if Watson asks cleverly"],
      "intro": "cryptic greeting suggesting they know more than they let on",
      "avatar_style": "sharp eyes, hood up, leaning against wall"
    }}
  ],
  "solution_reveal": "The full 3-sentence solution Holmes delivers at the end",
  "watson_intro": "The opening narration Watson hears when they enter the space"
}}"""


@dataclass
class SherlockCharacter:
    name: str
    role: str
    personality: str
    secret: str
    voice_tone: str
    clues: list[str]
    intro: str
    robot_id: str = ""


@dataclass
class SherlockMystery:
    title: str
    victim: str
    culprit: str          # hidden from players
    motive: str           # hidden from players
    method: str           # hidden from players
    premise: str
    mystery_question: str
    solution_reveal: str
    watson_intro: str
    characters: list[SherlockCharacter] = field(default_factory=list)
    clues_collected: list[str] = field(default_factory=list)


def generate_sherlock_mystery(scan_results: list[dict], num_robots: int = 3) -> SherlockMystery:
    """Generate a Sherlock Holmes mystery grounded in the scanned space."""

    # Build space description from scans
    all_objects = []
    all_interesting = []
    atmosphere = ""
    room_type = ""
    text_visible = []

    for s in scan_results:
        all_objects.extend(s.get("objects", []))
        all_interesting.extend(s.get("interesting", []))
        text_visible.extend(s.get("text_visible", []))
        atmosphere = atmosphere or s.get("atmosphere", "")
        room_type = room_type or s.get("room_type", "")

    # Use fallback if no real scan
    if not scan_results:
        room_type = "modern hackathon space at SHACK15, San Francisco Ferry Building"
        atmosphere = "electric, caffeinated, competitive"
        all_objects = ["laptop computers", "robot arms", "whiteboards", "ethernet cables",
                       "coffee machines", "NVIDIA GPUs", "sticky notes", "server racks"]
        all_interesting = ["a disabled robot arm in the corner",
                           "an encrypted whiteboard formula",
                           "a suspiciously empty server rack"]
        text_visible = ["SHACK15", "NVIDIA GTC 2026", "Nebius.Build"]

    space_details = f"""
Room: {room_type}
Atmosphere: {atmosphere}
Objects found: {', '.join(list(set(all_objects))[:15])}
Text visible: {', '.join(list(set(text_visible))[:8])}
Most interesting: {', '.join(list(set(all_interesting))[:5])}
Number of robots: {num_robots}"""

    prompt = SHERLOCK_PROMPT.format(
        space_details=space_details,
        num_robots=num_robots
    )

    print(f"🔍 Generating Sherlock mystery via Nebius ({LLM_MODEL})...")
    client = OpenAI(base_url=NEBIUS_BASE_URL, api_key=NEBIUS_API_KEY)

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SHERLOCK_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2000,
        temperature=0.9,
    )

    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json").strip()

    data = json.loads(raw)
    characters = [SherlockCharacter(**c) for c in data.get("characters", [])]

    return SherlockMystery(
        title=data["title"],
        victim=data["victim"],
        culprit=data["culprit"],
        motive=data["motive"],
        method=data["method"],
        premise=data["premise"],
        mystery_question=data["mystery_question"],
        solution_reveal=data["solution_reveal"],
        watson_intro=data["watson_intro"],
        characters=characters,
    )


def sherlock_respond(
    character: SherlockCharacter,
    mystery: SherlockMystery,
    watson_message: str,
    conversation_history: list[dict] | None = None,
    clues_collected: list[str] | None = None,
) -> str:
    """
    Generate an in-character Holmesian response.
    Holmes can be more forthcoming as more clues are collected.
    """
    history = conversation_history or []
    clues = clues_collected or []
    progress = len(clues)

    is_holmes = character.role == "detective"

    system = f"""You are {character.name} in an immersive Sherlock Holmes mystery.

THE CASE: {mystery.title}
VICTIM: {mystery.victim}
YOUR ROLE: {character.role}
YOUR PERSONALITY: {character.personality}
YOUR SECRET (never state directly): {character.secret}
CLUES YOU CAN DROP: {chr(10).join(f'- {c}' for c in character.clues)}

{"HOLMES SPECIAL RULES:" if is_holmes else "CHARACTER RULES:"}
{"- You ARE Sherlock Holmes. Speak with Victorian wit and modern intelligence." if is_holmes else ""}
{"- Use deductive observations about the visitor (Watson) and the space." if is_holmes else ""}
{"- The visitor is YOUR Watson. Guide them without giving everything away." if is_holmes else ""}
{"- Reference real objects in the space as evidence." if is_holmes else ""}
{"- Watson has collected " + str(progress) + " clues so far." if is_holmes else ""}
{"- Stay in character. Be evasive, nervous, or helpful based on your personality." if not is_holmes else ""}
{"- Never confess directly. Drop clues accidentally." if not is_holmes else ""}

CASE SETTING: {mystery.premise}
WATSON MUST SOLVE: {mystery.mystery_question}

Respond in 2-3 sentences maximum. Make every word count.
{"End with something that redirects Watson toward another character or a specific object." if is_holmes else "End with something ambiguous that raises more questions."}"""

    messages = [{"role": "system", "content": system}]
    messages.extend(history[-6:])
    messages.append({"role": "user", "content": watson_message})

    client = OpenAI(base_url=NEBIUS_BASE_URL, api_key=NEBIUS_API_KEY)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=120,
        temperature=0.85,
    )
    return resp.choices[0].message.content.strip()


def check_solution(mystery: SherlockMystery, watson_answer: str) -> tuple[bool, str]:
    """
    Check if Watson's solution is correct. Returns (correct, response).
    """
    culprit_lower = mystery.culprit.lower()
    answer_lower = watson_answer.lower()

    # Check if culprit name mentioned
    correct = any(word in answer_lower for word in culprit_lower.split())

    if correct:
        return True, f"*Elementary, my dear Watson.* {mystery.solution_reveal}"
    else:
        hints_remaining = len(mystery.characters[0].clues)
        return False, (
            f"Hmm. An interesting theory, but the evidence does not support it. "
            f"Return to the suspects — you are missing something crucial. "
            f"{hints_remaining} threads remain unexplored."
        )
