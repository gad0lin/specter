# 🔮 SPECTER — Space Perception Engine for Crime, Theater, and Exploration Research

> Robots scan a physical space, generate an immersive story from what they find, then each robot *becomes* a character. Visitors walk through and interact to unravel the mystery.

**Built at Nebius.Build SF 2026** · SHACK15 · March 15, 2026

---

## Concept

**Phase 1 — SCAN** *(autonomous, ~5 min)*
Robots sweep the space. NVIDIA NIM vision identifies objects, Tavily searches real context, Llama generates a story world grounded in what it actually found.

**Phase 2 — PLAY** *(interactive, ongoing)*
Each robot is assigned a character role (detective, suspect, witness). Visitors walk up and speak to them. Robots respond in character via ACE Riva TTS + Audio2Face avatar. Collecting clues across robots solves the mystery.

**Mirror World**
Omniverse renders a real-time digital twin — every robot's position, the space map, active clues, character avatars.

---

## Stack

| Layer | Tech | Provider |
|-------|------|---------|
| Vision / OCR | NIM · Qwen2-VL-72B | NVIDIA + Nebius |
| LLM / Story gen | Llama-3.3-70B | Nebius Token Factory |
| Character search | Tavily AI Search | Tavily |
| Voice synthesis | ACE Riva TTS | NVIDIA |
| Avatar animation | ACE Audio2Face | NVIDIA |
| Egocentric data | HomER dataset + preset | Toloka |
| Model routing | Token Factory + OpenRouter | Nebius |
| Robot platform | Unitree G1 Humanoid | — |
| Orchestration | OpenClaw | — |
| Mirror world | Omniverse (planned) | NVIDIA |

---

## Quick Start

```bash
# Setup
./specter.sh init

# Scan the space (builds story)
./specter.sh scan

# Deploy characters to robots
./specter.sh deploy

# Open mirror world dashboard
open http://localhost:8888
```

---

## Repo Layout

```
specter.sh             ← main entry point
src/
  scan/             ← space scanning + object recognition
  story/            ← story generation + character assignment
  characters/       ← character memory + dialogue
  voice/            ← Riva TTS + Audio2Face + MiniMax fallback
  web/              ← FastAPI dashboard + mirror world UI
  robots/           ← Unitree G1 + robot mesh coordination
config/
  stacks.py         ← backend presets (nvidia / hybrid / auto)
scripts/
  scan.sh           ← run scan phase
  deploy.sh         ← deploy characters
```

---

## Team

Built from scratch at Nebius.Build SF 2026.
