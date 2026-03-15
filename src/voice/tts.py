"""
voice/tts.py — Multi-backend TTS for character voices.

Backends:
  riva      — NVIDIA ACE Riva (GPU-accelerated, highest quality)
  minimax   — MiniMax speech-2.8-hd (expressive system voices)
  elevenlabs — ElevenLabs (fallback)
  
Selected via TTS_BACKEND env var (set by stack preset).
"""
import os
import subprocess
import tempfile

TTS_BACKEND = os.environ.get("TTS_BACKEND", "minimax").lower()

# MiniMax voice mapping by personality keywords
MINIMAX_VOICES = {
    "detective": "English_authoritative_man",
    "male":      "English_authoritative_man",
    "female":    "English_cheerful_woman",
    "child":     "English_male_child",
    "young":     "English_male_child",
    "narrator":  "English_expressive_narrator",
    "nervous":   "English_expressive_narrator",
    "villain":   "English_deep_man",
    "guide":     "English_expressive_narrator",
}


def _pick_minimax_voice(voice_tone: str) -> str:
    tone_lower = voice_tone.lower()
    for keyword, voice_id in MINIMAX_VOICES.items():
        if keyword in tone_lower:
            return voice_id
    return "English_expressive_narrator"


def synthesize(text: str, voice_tone: str = "expressive narrator") -> bytes:
    """
    Synthesize speech for a character.

    Args:
        text:       Text to speak
        voice_tone: Character's voice description (from StoryWorld character)

    Returns:
        MP3 audio bytes
    """
    backend = TTS_BACKEND

    if backend == "riva":
        return _synthesize_riva(text, voice_tone)
    if backend == "minimax":
        return _synthesize_minimax(text, voice_tone)
    if backend == "elevenlabs":
        return _synthesize_elevenlabs(text, voice_tone)

    # auto: try in order
    for fn in [_synthesize_minimax, _synthesize_elevenlabs]:
        try:
            return fn(text, voice_tone)
        except Exception as e:
            print(f"⚠️  TTS {fn.__name__} failed: {e}")
    raise RuntimeError("All TTS backends failed")


def play(audio_bytes: bytes) -> None:
    """Play audio bytes via afplay (macOS) or aplay (Linux)."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        if os.path.exists("/usr/bin/afplay"):
            subprocess.run(["afplay", tmp], check=True)
        else:
            subprocess.run(["aplay", tmp], check=True)
    finally:
        os.unlink(tmp)


def speak(text: str, voice_tone: str = "expressive narrator") -> bytes:
    """Synthesize and play. Returns audio bytes."""
    audio = synthesize(text, voice_tone)
    play(audio)
    return audio


# ── MiniMax ───────────────────────────────────────────────────────────────────

def _synthesize_minimax(text: str, voice_tone: str) -> bytes:
    import requests
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not set")

    voice_id = _pick_minimax_voice(voice_tone)
    resp = requests.post(
        "https://api.minimax.io/v1/t2a_v2",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "speech-2.8-hd",
            "text": text,
            "stream": False,
            "language_boost": "auto",
            "output_format": "mp3",
            "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "format": "mp3"},
        },
        timeout=20,
    )
    resp.raise_for_status()
    audio_hex = resp.json().get("data", {}).get("audio", "")
    if not audio_hex:
        raise RuntimeError(f"MiniMax returned no audio: {resp.json()}")
    return bytes.fromhex(audio_hex)


# ── NVIDIA Riva ───────────────────────────────────────────────────────────────

def _synthesize_riva(text: str, voice_tone: str) -> bytes:
    """
    NVIDIA ACE Riva TTS via NIM container.
    Requires RIVA_SERVER or falls back to MiniMax.
    """
    riva_server = os.environ.get("RIVA_SERVER", "")
    if not riva_server:
        print("⚠️  RIVA_SERVER not set — falling back to MiniMax")
        return _synthesize_minimax(text, voice_tone)

    try:
        import riva.client
        auth = riva.client.Auth(uri=riva_server)
        tts_client = riva.client.SpeechSynthesisServiceStub(auth.channel)
        req = riva.client.AudioEncoding.LINEAR_PCM
        # TODO: pick voice by tone
        resp = tts_client.Synthesize(riva.client.SynthesizeSpeechRequest(
            text=text,
            language_code="en-US",
            encoding=req,
            sample_rate_hz=22050,
            voice_name="English-US.Male-1",
        ))
        return resp.audio
    except Exception as e:
        print(f"⚠️  Riva failed: {e} — falling back to MiniMax")
        return _synthesize_minimax(text, voice_tone)


# ── ElevenLabs fallback ───────────────────────────────────────────────────────

def _synthesize_elevenlabs(text: str, voice_tone: str) -> bytes:
    import requests
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")
    voice_id = "JBFqnCBsd6RMkjVDRZzb"  # George — narrator
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_turbo_v2_5",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.content
