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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile
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


@app.post("/scan/video")
async def scan_video_upload(request: Request):
    """Upload a video → extract frames → NIM scans each → rich scene map."""
    from fastapi import UploadFile
    import tempfile
    form = await request.form()
    video_file = form.get("video")
    if not video_file:
        return JSONResponse({"error": "No video file"}, status_code=400)

    suffix = Path(video_file.filename).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        content = await video_file.read()
        f.write(content)
        tmp_path = f.name

    await broadcast({"type": "log", "msg": f"📽️ Video received ({len(content)//1024}KB) — extracting frames..."})

    from src.scan.video import scan_video, merge_scan_results
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(None, scan_video, tmp_path, 0.5, 6)
        merged = merge_scan_results(results)
        _scan_results.extend(results)
        await broadcast({"type": "scan_result", "result": merged, "count": len(_scan_results), "source": "video"})
        await broadcast({"type": "log", "msg": f"✅ Video scanned — {len(results)} frames, {len(merged.get('objects',[]))} objects found"})
        return {"frames_scanned": len(results), "merged": merged}
    except Exception as e:
        await broadcast({"type": "log", "msg": f"❌ Video scan failed: {e}"})
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        os.unlink(tmp_path)


@app.get("/avatar/{role}/{name}")
async def get_avatar(role: str, name: str, speaking: bool = False):
    from src.voice.ace_avatar import get_avatar_svg
    from fastapi.responses import Response
    svg = get_avatar_svg(role, name, speaking)
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/favicon.ico")
async def favicon():
    # SVG eye icon as favicon
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
      <rect width="96" height="96" fill="#1a1814" rx="16"/>
      <path d="M12 48 C24 24 72 24 84 48 C72 72 24 72 12 48Z" stroke="white" stroke-width="2.5" fill="none"/>
      <circle cx="48" cy="48" r="14" stroke="white" stroke-width="2.5" fill="none"/>
      <circle cx="48" cy="48" r="5" fill="white"/>
    </svg>'''
    from fastapi.responses import Response
    return Response(content=svg, media_type="image/svg+xml")


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
        "keys": await _check_keys(),
        "deployment": _get_stage_info(),
    }


def _get_stage_info() -> dict:
    try:
        from src.robots.deployment import stage_info
        return stage_info()
    except Exception:
        return {"stage": "virtual"}


async def _check_keys() -> dict:
    from config.settings import get
    import httpx
    results = {}
    nebius_key = get("nebius_api_key")
    tavily_key = get("tavily_api_key")
    nvidia_key = get("nvidia_api_key")
    if nvidia_key:
        results["nvidia_ace"] = "configured"
    else:
        results["nvidia_ace"] = "missing (optional)"

    # Nebius
    if nebius_key:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.post(
                    "https://api.studio.nebius.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {nebius_key}"},
                    json={"model":"meta-llama/Llama-3.3-70B-Instruct","messages":[{"role":"user","content":"ping"}],"max_tokens":3},
                )
            results["nebius"] = "ok" if r.status_code == 200 else f"error {r.status_code}"
        except Exception as e:
            results["nebius"] = f"error: {e}"
    else:
        results["nebius"] = "missing"

    # Tavily
    if tavily_key:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {tavily_key}"},
                    json={"query":"test","max_results":1},
                )
            results["tavily"] = "ok" if r.status_code == 200 else f"error {r.status_code}"
        except Exception as e:
            results["tavily"] = f"error: {e}"
    else:
        results["tavily"] = "missing"

    return results


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


from src.web.mystery_store import create as create_mystery, get as get_mystery, all_sessions, add_clue, mark_solved


@app.get("/mystery/{mystery_id}", response_class=HTMLResponse)
async def mystery_player(mystery_id: str):
    """Player view — interact with characters, collect clues."""
    s = get_mystery(mystery_id)
    if not s:
        return HTMLResponse("<h1>Mystery not found</h1>", status_code=404)
    return _render_mystery_page(s, admin=False)


@app.get("/mystery/{mystery_id}/admin", response_class=HTMLResponse)
async def mystery_admin(mystery_id: str):
    """Operator view — see all character prompts, robot assignments, solution."""
    s = get_mystery(mystery_id)
    if not s:
        return HTMLResponse("<h1>Mystery not found</h1>", status_code=404)
    return _render_mystery_page(s, admin=True)


@app.get("/mysteries")
async def list_mysteries():
    return [{"id": s.id, "title": s.title, "solved": s.solved,
             "url": f"/mystery/{s.id}"} for s in all_sessions()]


def _render_mystery_page(s, admin: bool = False) -> str:
    chars_html = ""
    for c in s.characters:
        color = {"detective":"#6366f1","suspect":"#c93030","witness":"#2563eb",
                 "red_herring":"#d97706","informant":"#059669"}.get(c.get("role",""), "#888")
        secret_block = f"""<div style="margin-top:8px;padding:8px;background:#fef3c7;border-radius:6px;font-size:12px">
            <strong>🔒 Secret:</strong> {c.get('secret','')}
            <br><strong>📍 Zone:</strong> {c.get('robot_id','?')} → {c.get('zone','?')}
            <br><strong>🎭 Voice:</strong> {c.get('voice_tone','')}
            <br><strong>💡 Clues to drop:</strong> {', '.join(c.get('clues',[]))}
        </div>""" if admin else ""

        chars_html += f"""<div style="background:#fff;border:1px solid #e5e2dc;border-radius:12px;padding:20px;margin-bottom:12px">
            <div style="display:flex;gap:12px;align-items:center;margin-bottom:8px">
                <img src="/avatar/{c.get('role','witness')}/{c.get('name','?')}" width="48" height="48" style="border-radius:50%;border:2px solid {color}"/>
                <div>
                    <div style="font-weight:700;font-size:16px">{c.get('name','?')}</div>
                    <div style="font-size:11px;color:{color};font-weight:700;text-transform:uppercase">{c.get('role','').replace('_',' ')}</div>
                </div>
            </div>
            <div style="font-size:13px;color:#6b6560">{c.get('personality','')}</div>
            <div style="font-size:13px;margin-top:6px;font-style:italic">"{c.get('intro','')}"</div>
            {secret_block}
        </div>"""

    solution_block = f"""<div style="background:#fef3c7;border:1px solid #fde68a;border-radius:12px;padding:20px;margin-bottom:24px">
        <div style="font-size:11px;font-weight:700;letter-spacing:2px;color:#b45309;margin-bottom:8px">🔑 SOLUTION (OPERATOR ONLY)</div>
        <div style="font-size:14px">{s.solution}</div>
    </div>""" if admin else ""

    admin_badge = '<span style="background:#c93030;color:#fff;font-size:10px;font-weight:700;padding:3px 10px;border-radius:999px;margin-left:8px">OPERATOR VIEW</span>' if admin else ''

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SPECTER — {s.title}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>
* {{margin:0;padding:0;box-sizing:border-box}}
body {{background:#f8f7f4;font-family:'DM Sans',sans-serif;color:#1a1814;padding:0 0 60px}}
.header {{background:#1a1814;color:#faf8f5;padding:16px 24px;display:flex;align-items:center;gap:12px}}
.header svg {{opacity:0.8}}
.container {{max-width:720px;margin:32px auto;padding:0 24px}}
.mystery-title {{font-family:'DM Serif Display',serif;font-size:2.2rem;margin:24px 0 8px}}
.premise {{color:#6b6560;font-size:15px;line-height:1.7;margin-bottom:16px}}
.mystery-q {{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px 18px;font-size:14px;color:#92400e;margin-bottom:24px}}
.section {{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#aaa49e;margin:24px 0 12px}}
.share-url {{background:#fff;border:1px solid #e5e2dc;border-radius:8px;padding:10px 14px;font-family:monospace;font-size:13px;display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}}
.copy-btn {{background:#1a1814;color:#fff;border:none;padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer}}
</style>
</head><body>
<div class="header">
  <svg width="24" height="24" viewBox="0 0 96 96" fill="none"><path d="M12 48 C24 24 72 24 84 48 C72 72 24 72 12 48Z" stroke="white" stroke-width="3" fill="none"/><circle cx="48" cy="48" r="14" stroke="white" stroke-width="3" fill="none"/><circle cx="48" cy="48" r="5" fill="white"/></svg>
  <span style="font-family:'DM Serif Display',serif;font-size:1.1rem">SPECTER</span>
  <span style="color:#555;font-size:13px">#{s.id}</span>
  {admin_badge}
  <a href="/mystery/{s.id}{'admin' if not admin else ''}" style="margin-left:auto;color:#888;font-size:12px;text-decoration:none">{'→ Operator view' if not admin else '→ Player view'}</a>
</div>
<div class="container">
  <div class="mystery-title">{s.title}</div>
  <div class="premise">{s.premise}</div>
  <div class="mystery-q"><strong>🔍 Your mission:</strong> {s.mystery_question}</div>

  {solution_block}

  <div class="section">Share this mystery</div>
  <div class="share-url">
    <span>{s.id and f'specter.charlieverse.io/mystery/{s.id}'}</span>
    <button class="copy-btn" onclick="navigator.clipboard.writeText(location.origin+'/mystery/{s.id}');this.textContent='Copied!'">Copy link</button>
  </div>

  <div class="section">Characters ({len(s.characters)})</div>
  {chars_html}

  <div class="section">Clues collected ({len(s.clues_found)})</div>
  <div style="color:#aaa49e;font-size:13px">{'<br>'.join(s.clues_found) if s.clues_found else 'No clues yet — interact with characters.'}</div>
</div>
</body></html>"""


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

        # Save to mystery store → shareable URL
        scan_summary = _scan_results[-1] if _scan_results else {}
        mystery_data = {
            "title": story.title, "premise": story.premise,
            "mystery_question": getattr(story, 'mystery_question', story.mystery),
            "solution": getattr(story, 'solution_reveal', getattr(story, 'solution', '')),
            "watson_intro": getattr(story, 'watson_intro', ''),
            "characters": [c.__dict__ for c in story.characters],
        }
        session = create_mystery(mystery_data, scan_summary)

        await broadcast({
            "type": "story_ready",
            "title": story.title,
            "premise": story.premise,
            "mystery": getattr(story, 'mystery_question', story.mystery),
            "mystery_id": session.id,
            "player_url": f"/mystery/{session.id}",
            "admin_url": f"/mystery/{session.id}/admin",
            "characters": [{"name": c.name, "role": c.role, "robot_id": c.robot_id} for c in story.characters],
        })
        await ws.send_json({"type": "log", "msg": f"🎭 '{story.title}' → /mystery/{session.id}"})
    except Exception as e:
        await ws.send_json({"type": "log", "msg": f"❌ Story generation failed: {e}"})


if __name__ == "__main__":
    import sys
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="specter",
        description="SPECTER — Space Perception Engine for Crime, Theater & Exploration Research",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  ./specter.sh                          start dashboard (auto stack)
  ./specter.sh --stack nvidia           full NVIDIA NIM + Nebius stack
  ./specter.sh --mode mystery           Sherlock mystery game
  ./specter.sh --mode forensics         crime scene documentation
  ./specter.sh --image-path scan.jpg    scan a specific image
  ./specter.sh --port 9000              custom port
  ./specter.sh init                     first-time setup wizard

config:
  ~/.config/specter/config.yaml         API keys + defaults
        """,
    )
    parser.add_argument("command", nargs="?", help="init | scan")
    parser.add_argument("--port", "-p", type=int, default=int(os.environ.get("PORT", 8081)), help="Port (default: 8081)")
    parser.add_argument("--stack", choices=["nvidia", "hybrid", "auto"], default=None, help="Backend stack preset")
    parser.add_argument("--mode", choices=["mystery", "forensics", "auto"], default="auto", help="Operating mode")
    parser.add_argument("--image-path", metavar="FILE", help="Scan a specific image file")
    parser.add_argument("--no-banner", action="store_true", help="Skip startup banner")
    parser.add_argument("--stage", choices=["virtual","simulated","real"], default=None,
                        help="Deployment stage: virtual (default) | simulated (Isaac Sim) | real (Unitree G1)")

    args = parser.parse_args()

    if args.command == "init":
        print("🔮 SPECTER init — coming soon. Edit ~/.config/specter/config.yaml manually for now.")
        sys.exit(0)

    # Apply stack
    if args.stack:
        from config.stacks import apply
        apply(args.stack)

    if args.image_path:
        os.environ["IMAGE_PATH"] = args.image_path
    if args.stage:
        os.environ["SPECTER_STAGE"] = args.stage

    os.environ["SPECTER_MODE"] = args.mode

    if not args.no_banner:
        from config.settings import get
        stack = args.stack or get("stack", "auto")
        mode = args.mode
        stage = args.stage or os.environ.get("SPECTER_STAGE", "virtual")
        stage_labels = {"virtual":"🖥  Virtual (dashboard + Rerun)", "simulated":"🔬 Simulated (Isaac Sim on Nebius H100)", "real":"🤖 Real (Unitree G1 hardware)"}
        print(f"""
🔮 SPECTER
   Stage:   {stage_labels.get(stage, stage)}
   Mode:    {mode}
   Stack:   {stack}
   Port:    {args.port}
   Local:   http://localhost:{args.port}
""")

    uvicorn.run(app, host="0.0.0.0", port=args.port,
                ws_ping_interval=20, ws_ping_timeout=20,
                proxy_headers=True, forwarded_allow_ips="*")
