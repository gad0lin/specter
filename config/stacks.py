"""
LORE backend stack presets.

./specter.sh --stack nvidia    → full NVIDIA stack (GTC demo)
./specter.sh --stack hybrid    → CLI vision + Tavily + MiniMax
./specter.sh --stack auto      → smart defaults
"""
import os

STACKS = {
    "nvidia": {
        "VISION_BACKEND":   "nim",           # NVIDIA NIM / Qwen2-VL-72B
        "LLM_BACKEND":      "nebius",        # Nebius Token Factory / Llama-3.3-70B
        "SEARCH_BACKEND":   "tavily",        # Tavily AI search
        "TTS_BACKEND":      "riva",          # NVIDIA ACE Riva
        "AVATAR_BACKEND":   "audio2face",    # NVIDIA ACE Audio2Face
        "NIM_MODEL":        "Qwen/Qwen2-VL-72B-Instruct",
        "LLM_MODEL":        "meta-llama/Llama-3.3-70B-Instruct",
    },
    "hybrid": {
        "VISION_BACKEND":   "nim",
        "LLM_BACKEND":      "nebius",
        "SEARCH_BACKEND":   "tavily",
        "TTS_BACKEND":      "minimax",       # MiniMax speech-2.8-hd
        "AVATAR_BACKEND":   "css",           # CSS animated avatar
    },
    "auto": {
        "VISION_BACKEND":   "auto",
        "LLM_BACKEND":      "auto",
        "SEARCH_BACKEND":   "tavily",
        "TTS_BACKEND":      "minimax",
        "AVATAR_BACKEND":   "css",
    },
}

DEFAULT_STACK = "hybrid"


def apply(stack_name: str) -> None:
    preset = STACKS.get(stack_name.lower())
    if not preset:
        raise ValueError(f"Unknown stack '{stack_name}'. Choose: {', '.join(STACKS)}")
    applied = []
    for k, v in preset.items():
        if k not in os.environ:
            os.environ[k] = v
            applied.append(f"{k}={v}")
    print(f"🔧 Stack [{stack_name}]: {' · '.join(applied) or 'all overridden'}")


def summary(stack_name: str) -> str:
    p = STACKS.get(stack_name, {})
    return (f"vision={p.get('VISION_BACKEND','?')} · "
            f"llm={p.get('LLM_BACKEND','?')} · "
            f"tts={p.get('TTS_BACKEND','?')} · "
            f"avatar={p.get('AVATAR_BACKEND','?')}")
