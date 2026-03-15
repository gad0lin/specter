"""
robots/deployment.py — Stage-based robot deployment.

SPECTER runs the same story/character logic regardless of stage.
Only the robot backend changes:

  Stage 1 — virtual    Dashboard map + Rerun 3D (no hardware)
  Stage 2 — simulated  Isaac Sim on Nebius H100 (physics sim)
  Stage 3 — real       Unitree G1 physical robots (live hardware)

Switch with: ./specter.sh --stage virtual|simulated|real
Or in config.yaml: stage: virtual
"""
import os

STAGE = os.environ.get("SPECTER_STAGE", "virtual").lower()


def move_robot(robot_id: str, character_name: str, role: str, zone: str, position: dict):
    """Send robot to a zone — backend depends on deployment stage."""
    if STAGE == "real":
        _move_real(robot_id, zone, position)
    elif STAGE == "simulated":
        _move_sim(robot_id, zone, position)
    else:
        _move_virtual(robot_id, character_name, role, zone)


def speak(robot_id: str, audio_bytes: bytes, zone: str):
    """Play audio from robot — real plays on device, virtual plays locally."""
    if STAGE == "real":
        _speak_real(robot_id, audio_bytes)
    else:
        _speak_local(audio_bytes)


# ── Stage 1: Virtual ──────────────────────────────────────────────────────────

def _move_virtual(robot_id: str, character_name: str, role: str, zone: str):
    """Update position in Rerun 3D viewer."""
    try:
        from src.robots.visualizer import update_robot
        update_robot(robot_id, character_name, role, zone)
    except Exception:
        pass  # Rerun optional


def _speak_local(audio_bytes: bytes):
    """Play audio on local machine."""
    import tempfile, subprocess, os
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes); tmp = f.name
    try:
        subprocess.run(["afplay", tmp], check=False)
    finally:
        os.unlink(tmp)


# ── Stage 2: Simulated (Isaac Sim) ───────────────────────────────────────────

ISAAC_WS_URL = os.environ.get("ISAAC_WS_URL", "")  # e.g. ws://VM_IP:8765

def _move_sim(robot_id: str, zone: str, position: dict):
    """Send nav goal to Isaac Sim robot via WebSocket."""
    if not ISAAC_WS_URL:
        print(f"⚠️  ISAAC_WS_URL not set — set to ws://YOUR_VM_IP:8765")
        return
    try:
        import asyncio, websockets, json
        async def _send():
            async with websockets.connect(ISAAC_WS_URL) as ws:
                await ws.send(json.dumps({
                    "type": "move_robot",
                    "robot_id": robot_id,
                    "zone": zone,
                    "position": position,
                }))
        asyncio.run(_send())
        print(f"🤖 [SIM] {robot_id} → {zone}")
    except Exception as e:
        print(f"⚠️  Isaac Sim connection failed: {e}")


# ── Stage 3: Real (Unitree G1) ────────────────────────────────────────────────

UNITREE_API = os.environ.get("UNITREE_API_URL", "")  # e.g. http://192.168.1.x:8080

def _move_real(robot_id: str, zone: str, position: dict):
    """Send nav goal to physical Unitree G1 robot."""
    if not UNITREE_API:
        print(f"⚠️  UNITREE_API_URL not set — set to robot's IP")
        return
    try:
        import requests
        requests.post(f"{UNITREE_API}/navigate", json={
            "robot_id": robot_id,
            "x": position.get("x", 0),
            "y": position.get("y", 0),
            "zone": zone,
        }, timeout=3)
        print(f"🤖 [REAL] {robot_id} → {zone}")
    except Exception as e:
        print(f"⚠️  Unitree G1 connection failed: {e}")


def _speak_real(robot_id: str, audio_bytes: bytes):
    """Stream audio to robot's speaker."""
    if not UNITREE_API:
        _speak_local(audio_bytes)
        return
    try:
        import requests
        requests.post(f"{UNITREE_API}/speak",
                     data=audio_bytes,
                     headers={"Content-Type": "audio/mp3"},
                     timeout=5)
    except Exception:
        _speak_local(audio_bytes)


def stage_info() -> dict:
    return {
        "stage": STAGE,
        "isaac_url": ISAAC_WS_URL or None,
        "unitree_url": UNITREE_API or None,
        "description": {
            "virtual":   "Dashboard map + Rerun 3D (no hardware needed)",
            "simulated": "Isaac Sim on Nebius H100 (physics simulation)",
            "real":      "Unitree G1 physical robots (live hardware)",
        }.get(STAGE, "unknown"),
    }
