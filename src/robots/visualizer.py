"""
robots/visualizer.py — Rerun 3D visualization for SPECTER robot mesh.

Uses rerun-sdk to render robots moving through SHACK15 in a live 3D viewer.
Run: python src/robots/visualizer.py
Opens browser at http://localhost:9090

Robots are represented as capsules with character labels.
Position updates stream in real-time from the mesh.
"""
import os
import time
import threading
import numpy as np

try:
    import rerun as rr
    RERUN_AVAILABLE = True
except ImportError:
    RERUN_AVAILABLE = False
    print("⚠️  rerun-sdk not installed — run: pip install rerun-sdk")


# SHACK15 zone positions in 3D (x, z, y=0 floor)
ZONE_3D = {
    "entrance":  np.array([0.0,  0.0,  0.0]),
    "main_hall": np.array([3.0,  0.0,  2.0]),
    "bay_view":  np.array([6.0,  0.0,  5.0]),
    "bar":       np.array([8.0,  0.0, -1.0]),
    "robot_lab": np.array([2.0,  0.0, -2.0]),
    "stage":     np.array([5.0,  0.0,  1.0]),
}

ROLE_COLORS = {
    "detective": [99,  102, 241],   # indigo
    "suspect":   [201,  48,  48],   # red
    "witness":   [37,   99, 235],   # blue
    "guide":     [5,   150, 105],   # green
}


def init_rerun(app_name: str = "SPECTER"):
    """Initialize Rerun and open viewer."""
    if not RERUN_AVAILABLE:
        return False
    rr.init(app_name, spawn=True)
    _draw_shack15_space()
    return True


def _draw_shack15_space():
    """Draw SHACK15 floor plan as 3D boxes."""
    if not RERUN_AVAILABLE:
        return

    # Floor
    rr.log("space/floor", rr.Boxes3D(
        centers=[[4.0, -0.05, 2.0]],
        half_sizes=[[5.0, 0.05, 4.0]],
        colors=[[240, 237, 232]],
        labels=["SHACK15 — Ferry Building"],
    ))

    # Walls (simplified)
    rr.log("space/bay_windows", rr.Boxes3D(
        centers=[[4.0, 1.5, 5.5]],
        half_sizes=[[4.0, 1.5, 0.1]],
        colors=[[191, 219, 254, 80]],
        labels=["Bay View Windows"],
    ))

    # Zone markers
    for zone, pos in ZONE_3D.items():
        rr.log(f"zones/{zone}", rr.Points3D(
            positions=[pos + np.array([0, 0.01, 0])],
            colors=[[200, 200, 200]],
            labels=[zone.replace("_", " ").title()],
            radii=[0.3],
        ))


def update_robot(robot_id: str, character_name: str, role: str, zone: str):
    """Update a robot's position in the 3D view."""
    if not RERUN_AVAILABLE:
        return

    pos = ZONE_3D.get(zone, ZONE_3D["main_hall"]).copy()
    pos[1] = 0.9  # robot height center

    color = ROLE_COLORS.get(role, [100, 100, 100])

    # Robot body (capsule approximation with box)
    rr.log(f"robots/{robot_id}/body", rr.Boxes3D(
        centers=[pos],
        half_sizes=[[0.2, 0.6, 0.2]],
        colors=[color],
        labels=[f"{character_name}\n({role})"],
    ))

    # Robot head
    head_pos = pos.copy(); head_pos[1] = 1.7
    rr.log(f"robots/{robot_id}/head", rr.Points3D(
        positions=[head_pos],
        colors=[color],
        radii=[0.18],
    ))

    # Label
    rr.log(f"robots/{robot_id}/label", rr.TextLog(
        text=f"{character_name} → {zone.replace('_',' ')}",
        level=rr.TextLogLevel.INFO,
    ))


def show_dialogue(robot_id: str, text: str):
    """Flash a speech bubble when robot speaks."""
    if not RERUN_AVAILABLE:
        return
    rr.log(f"dialogue/{robot_id}", rr.TextLog(
        text=f"💬 {text[:80]}",
        level=rr.TextLogLevel.INFO,
    ))


def mark_clue(location: str, clue_text: str):
    """Mark a clue location in the 3D space."""
    if not RERUN_AVAILABLE:
        return
    pos = ZONE_3D.get(location, ZONE_3D["main_hall"]).copy()
    pos[1] = 0.5
    rr.log(f"clues/{location}", rr.Points3D(
        positions=[pos],
        colors=[[251, 191, 36]],
        radii=[0.15],
        labels=[f"🔍 {clue_text[:40]}"],
    ))


if __name__ == "__main__":
    print("🔮 SPECTER — Rerun 3D Visualizer")
    if not init_rerun():
        print("Install: uv pip install rerun-sdk")
        exit(1)

    # Demo: animate robots through SHACK15 zones
    demo_robots = [
        ("robot_0", "Sherlock Holmes", "detective", ["bay_view", "main_hall", "stage"]),
        ("robot_1", "The Suspect", "suspect", ["bar", "main_hall", "bar"]),
        ("robot_2", "The Witness", "witness", ["main_hall", "stage", "main_hall"]),
    ]

    print("Animating robots through SHACK15... (Ctrl+C to stop)")
    for i in range(3):
        for robot_id, name, role, zones in demo_robots:
            zone = zones[i % len(zones)]
            update_robot(robot_id, name, role, zone)
            print(f"  {name} → {zone}")
        time.sleep(3)
