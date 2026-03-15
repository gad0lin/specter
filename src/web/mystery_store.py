"""
mystery_store.py — Persistent mystery sessions.

Each mystery gets a unique ID and shareable URL:
  /mystery/1        → player view (interact with characters)
  /mystery/1/admin  → operator view (see all prompts, robot assignments)
  /mystery/1/solve  → submit solution

Mysteries persist in memory (resets on restart).
Can be extended to write to disk for persistence.
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class MysterySession:
    id: str
    created_at: float
    title: str
    premise: str
    mystery_question: str
    solution: str          # hidden from players
    watson_intro: str
    characters: list[dict]  # name, role, personality, secret, clues, robot_id, zone
    scan_summary: dict      # what was found in the space
    clues_found: list[str] = field(default_factory=list)
    solved: bool = False
    solver: str = ""

# In-memory store: id → MysterySession
_mysteries: dict[str, MysterySession] = {}
_counter = 0


def create(mystery_data: dict, scan_summary: dict) -> MysterySession:
    global _counter
    _counter += 1
    session_id = str(_counter)

    session = MysterySession(
        id=session_id,
        created_at=time.time(),
        title=mystery_data.get("title", "Untitled Mystery"),
        premise=mystery_data.get("premise", ""),
        mystery_question=mystery_data.get("mystery_question", ""),
        solution=mystery_data.get("solution", ""),
        watson_intro=mystery_data.get("watson_intro", ""),
        characters=[c.__dict__ if hasattr(c, '__dict__') else c
                    for c in mystery_data.get("characters", [])],
        scan_summary=scan_summary,
    )
    _mysteries[session_id] = session
    return session


def get(session_id: str) -> Optional[MysterySession]:
    return _mysteries.get(session_id)


def all_sessions() -> list[MysterySession]:
    return list(_mysteries.values())


def add_clue(session_id: str, clue: str):
    s = _mysteries.get(session_id)
    if s and clue not in s.clues_found:
        s.clues_found.append(clue)


def mark_solved(session_id: str, solver: str = "Watson"):
    s = _mysteries.get(session_id)
    if s:
        s.solved = True
        s.solver = solver
