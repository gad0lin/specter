"""
web/app.py — LORE dashboard + WebSocket hub.

Routes:
  GET  /           → dashboard UI
  GET  /status     → current story world + robot states
  GET  /story      → full story JSON
  WS   /ws         → real-time updates + visitor interaction
  POST /scan       → trigger space scan
  POST /interact   → visitor talks to a robot
"""
import os
import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(_mesh.run_water_cooler_loop(broadcast))
    yield

app = FastAPI(title="SPECTER — Space Perception Engine", lifespan=lifespan)

# ── State ──────────────────────────────────────────────────────────────────────
from src.robots.mesh import mesh as _mesh
from config.settings import apply_to_env as _apply_config
_apply_config()

_story_world = None          # StoryWorld or SherlockMystery once generated
_story_mode = "sherlock"     # "sherlock" | "generic"
_scan_results = []           # List of scan dicts
_robot_states = {}           # robot_id → {character, status, position}
_clues_found = []            # list of clues collected by visitors
_conversation_histories = {} # robot_id → list of {role, content}
_cases: dict = {}           # case_id → ForensicsReport
_clients: list[WebSocket] = []


async def broadcast(msg: dict):
    for ws in list(_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            _clients.remove(ws)


# ── HTTP routes ────────────────────────────────────────────────────────────────

TEMPLATE = Path(__file__).parent / "templates" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return TEMPLATE.read_text()


@app.get("/status")
async def status():
    return {
        "story": _story_world.__dict__ if _story_world else None,
        "robots": _robot_states,
        "clues_found": _clues_found,
        "scan_count": len(_scan_results),
    }


@app.get("/forensics/{case_id}")
async def get_case(case_id: str):
    if case_id not in _cases:
        return JSONResponse({"error": "Case not found"}, status_code=404)
    from src.scan.forensics import report_to_json
    return report_to_json(_cases[case_id])


@app.post("/forensics/scan")
async def forensics_scan(data: dict):
    """Trigger a forensics scan on an image."""
    image_path = data.get("image_path") or os.environ.get("IMAGE_PATH")
    location = data.get("location", "scene")
    case_id = data.get("case_id", "CASE-001")

    if not image_path:
        return JSONResponse({"error": "No image_path provided"}, status_code=400)

    from src.scan.forensics import scan_scene, generate_report, report_to_json
    loop = asyncio.get_event_loop()

    image_bytes = Path(image_path).read_bytes()
    scan = await loop.run_in_executor(None, scan_scene, image_bytes, location)
    _scan_results.append(scan)

    report = await loop.run_in_executor(None, generate_report, _scan_results, case_id)
    _cases[case_id] = report

    await broadcast({"type": "forensics_report", "case_id": case_id,
                     "summary": report.llm_summary, "anomalies": report.anomalies[:3]})

    return report_to_json(report)


@app.get("/mesh")
async def mesh_status():
    return {"robots": _mesh.all_states(), "visitor": _mesh.visitor_profile}


@app.get("/story")
async def story():
    if not _story_world:
        return JSONResponse({"error": "No story generated yet"}, status_code=404)
    sw = _story_world
    return {
        "title": sw.title,
        "premise": sw.premise,
        "mystery": sw.mystery,
        "atmosphere": sw.atmosphere,
        "characters": [c.__dict__ for c in sw.characters],
        "clues": sw.clues,
    }


@app.post("/interact")
async def interact(data: dict):
    """Visitor talks to a robot — returns character response + audio."""
    robot_id = data.get("robot_id", "robot_0")
    message = data.get("message", "Hello")

    if not _story_world:
        return {"error": "No story yet — scan the space first"}

    char = next((c for c in _story_world.characters if c.robot_id == robot_id), None)
    if not char:
        char = _story_world.characters[0] if _story_world.characters else None
    if not char:
        return {"error": "No character found"}

    # Visitor sensing — if image provided, profile them and share with mesh
    visitor_image = data.get("visitor_image_path")
    if visitor_image:
        from src.scan.visitor import sense_visitor
        try:
            img_bytes = Path(visitor_image).read_bytes()
            visitor_profile = await asyncio.get_event_loop().run_in_executor(None, sense_visitor, img_bytes)
            _mesh.update_visitor(visitor_profile)
            await broadcast({"type": "visitor_profile", "profile": visitor_profile})
        except Exception as e:
            print(f"⚠️  Visitor sensing failed: {e}")

    # Record interaction in mesh
    _mesh.record_interaction(robot_id)

    # Generate water cooler whisper between robots
    other_robots = [rid for rid in _mesh.robots if rid != robot_id]
    if other_robots:
        import random
        target = random.choice(other_robots)
        whisper = _mesh.generate_whisper(robot_id, target)
        await broadcast({"type": "mesh_whisper", "from": char.name,
                        "to": _mesh.robots[target].character_name, "text": whisper})

    # Maintain per-robot conversation history
    history = _conversation_histories.setdefault(robot_id, [])

    loop = asyncio.get_event_loop()

    # Check for solution attempt
    if any(kw in message.lower() for kw in ["the culprit is", "i think it was", "i accuse", "solution:"]):
        from src.story.sherlock import check_solution
        correct, response_text = check_solution(_story_world, message)
        kind = "solution_correct" if correct else "solution_wrong"
        await broadcast({"type": kind, "response": response_text})
    elif _story_mode == "sherlock":
        from src.story.sherlock import sherlock_respond
        response_text = await loop.run_in_executor(
            None, sherlock_respond, char, _story_world, message, history, _clues_found
        )
    else:
        from src.characters.dialogue import respond
        response_text = await loop.run_in_executor(
            None, respond, char, _story_world, message, history
        )

    # Update history
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response_text})

    # TTS
    from src.voice.tts import synthesize
    import base64
    try:
        audio_bytes = await loop.run_in_executor(
            None, synthesize, response_text, char.voice_tone
        )
        audio_b64 = base64.b64encode(audio_bytes).decode()
    except Exception as e:
        audio_b64 = None
        print(f"TTS error: {e}")

    # Broadcast to all dashboard clients
    await broadcast({
        "type": "dialogue",
        "robot_id": robot_id,
        "character": char.name,
        "visitor_said": message,
        "character_said": response_text,
    })

    return {
        "character": char.name,
        "response": response_text,
        "audio_b64": audio_b64,
    }


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "scan":
                await _handle_scan(websocket, data)

            elif action == "generate_story":
                mode = data.get("mode", "sherlock")
                await _handle_generate_story(websocket, data, mode)

            elif action == "interact":
                result = await interact(data)
                await websocket.send_json({"type": "interact_result", **result})

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        _clients.remove(websocket)


async def _handle_scan(ws: WebSocket, data: dict):
    global _scan_results
    await ws.send_json({"type": "log", "msg": "📸 Starting space scan..."})

    # For demo: use a provided image_path or camera
    image_path = data.get("image_path") or os.environ.get("IMAGE_PATH")
    location = data.get("location", "main area")

    if not image_path:
        await ws.send_json({"type": "log", "msg": "⚠️  No image path — use --image-path or camera"})
        return

    from src.scan.vision import scan_frame
    loop = asyncio.get_event_loop()

    try:
        image_bytes = Path(image_path).read_bytes()
        result = await loop.run_in_executor(None, scan_frame, image_bytes, location)
        _scan_results.append(result)
        await ws.send_json({"type": "scan_result", "result": result, "count": len(_scan_results)})
        await ws.send_json({"type": "log", "msg": f"✅ Scan complete — found {len(result.get('objects',[]))} objects"})
    except Exception as e:
        await ws.send_json({"type": "log", "msg": f"❌ Scan failed: {e}"})


async def _handle_generate_story(ws: WebSocket, data: dict, mode: str = "sherlock"):
    global _story_world, _story_mode
    _story_mode = mode
    await ws.send_json({"type": "log", "msg": "✨ Generating story from scan data..."})

    num_robots = data.get("num_robots", 3)
    robot_ids = data.get("robot_ids", [f"robot_{i}" for i in range(num_robots)])

    if not _scan_results:
        # Demo mode: use a minimal fake scan
        _scan_results.append({
            "room_type": "modern hackathon space",
            "atmosphere": "electric, creative, caffeinated",
            "objects": ["laptops", "robot arms", "whiteboards", "coffee machines", "ethernet cables"],
            "text_visible": ["SHACK15", "NVIDIA", "Nebius"],
            "interesting": ["a mysterious disabled robot arm", "an encrypted whiteboard", "a locked server rack"],
        })

    loop = asyncio.get_event_loop()

    try:
        if mode == "sherlock":
            from src.story.sherlock import generate_sherlock_mystery
            story = await loop.run_in_executor(None, generate_sherlock_mystery, _scan_results, num_robots)
            # Assign robot IDs to characters
            for i, char in enumerate(story.characters):
                if i < len(robot_ids):
                    char.robot_id = robot_ids[i]
            await ws.send_json({"type": "watson_intro", "text": story.watson_intro})
        else:
            from src.story.generator import generate_story, assign_robots
            story = await loop.run_in_executor(None, generate_story, _scan_results, num_robots)
            story = assign_robots(story, robot_ids)
        _story_world = story

        # Update robot states + register in mesh
        for char in story.characters:
            _robot_states[char.robot_id] = {
                "character": char.name,
                "role": char.role,
                "status": "ready",
            }
            _mesh.register(char.robot_id, char.name, char.role)

        await broadcast({
            "type": "story_ready",
            "title": story.title,
            "premise": story.premise,
            "mystery": story.mystery,
            "characters": [{"name": c.name, "role": c.role, "robot_id": c.robot_id} for c in story.characters],
        })
        await ws.send_json({"type": "log", "msg": f"🎭 Story ready: '{story.title}'"})
    except Exception as e:
        await ws.send_json({"type": "log", "msg": f"❌ Story generation failed: {e}"})


if __name__ == "__main__":
    import sys
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8888))
    uvicorn.run(app, host="0.0.0.0", port=port)
