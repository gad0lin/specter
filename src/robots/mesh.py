"""
robots/mesh.py — Robot mesh communication and movement coordination.

Robots share:
- Visitor profile (who Watson is, their mood, what they're carrying)
- Clues collected so far
- Which robot Watson just visited
- "Water cooler" gossip — robots can move toward each other or Watson

Water cooler behavior:
- When Watson hasn't visited a robot in >60s, that robot "wanders" toward activity
- Robots can send each other whispers ("Did Watson seem nervous to you?")
- Holmes can direct Watson: "You must speak with [character] near the [object]"

For Unitree G1 robots: publishes nav goals via ROS2 or simple HTTP to robot API.
For simulation/demo: tracks positions in mirror world dashboard only.
"""
import os
import time
import asyncio
from dataclasses import dataclass, field

# ── Robot registry ──────────────────────────────────────────────────────────

@dataclass
class RobotState:
    robot_id: str
    character_name: str
    role: str
    position: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "zone": "center"})
    status: str = "idle"          # idle | speaking | moving | listening
    last_interaction: float = 0.0
    visitor_profile: dict = field(default_factory=dict)
    whispers: list[str] = field(default_factory=list)


class RobotMesh:
    """
    Manages the fleet of robots — their states, positions, and coordination.
    """

    # SHACK15 zones — Ferry Building top floor
    SHACK15_ZONES = {
        "entrance":   {"x": 0.1, "y": 0.5, "label": "Ferry Building Entrance"},
        "main_hall":  {"x": 0.4, "y": 0.5, "label": "Main Hacking Area"},
        "bay_view":   {"x": 0.7, "y": 0.2, "label": "Bay View Window"},
        "bar":        {"x": 0.8, "y": 0.8, "label": "Bar Area"},
        "robot_lab":  {"x": 0.3, "y": 0.8, "label": "Robot Lab"},
        "stage":      {"x": 0.6, "y": 0.5, "label": "Demo Stage"},
    }

    # Starting positions for characters
    CHARACTER_ZONES = {
        "detective": "bay_view",    # Holmes by the window — dramatic backdrop
        "suspect":   "bar",         # Suspect near the bar — trying to look casual
        "witness":   "main_hall",   # Witness in the thick of things
        "guide":     "entrance",    # Guide greets at the door
    }

    def __init__(self):
        self.robots: dict[str, RobotState] = {}
        self.visitor_profile: dict = {}
        self.broadcast_fn = None    # set by app.py to broadcast WS events

    def register(self, robot_id: str, character_name: str, role: str):
        zone_key = self.CHARACTER_ZONES.get(role, "main_hall")
        zone = self.SHACK15_ZONES[zone_key]
        self.robots[robot_id] = RobotState(
            robot_id=robot_id,
            character_name=character_name,
            role=role,
            position={"x": zone["x"], "y": zone["y"], "zone": zone_key},
            last_interaction=time.time(),
        )
        print(f"🤖 {character_name} ({role}) stationed at {zone['label']}")

    def update_visitor(self, profile: dict):
        """Share visitor profile with all robots."""
        self.visitor_profile = profile
        for robot in self.robots.values():
            robot.visitor_profile = profile

    def record_interaction(self, robot_id: str):
        """Mark that Watson just interacted with this robot."""
        if robot_id in self.robots:
            self.robots[robot_id].last_interaction = time.time()
            self.robots[robot_id].status = "speaking"

    def get_water_cooler_suggestion(self, robot_id: str) -> str | None:
        """
        Suggest where a robot should wander if Watson hasn't visited recently.
        Returns a zone key or None.
        """
        robot = self.robots.get(robot_id)
        if not robot:
            return None
        idle_time = time.time() - robot.last_interaction
        if idle_time > 90:  # 90s without interaction → wander
            # Move toward wherever Watson last was
            most_recent = max(
                self.robots.values(),
                key=lambda r: r.last_interaction if r.robot_id != robot_id else 0
            )
            if most_recent.robot_id != robot_id:
                return most_recent.position.get("zone", "main_hall")
        return None

    def generate_whisper(self, from_robot_id: str, to_robot_id: str) -> str:
        """
        Generate a whisper between robots — sharing intel about Watson.
        Used to make cross-robot references feel natural.
        """
        profile = self.visitor_profile
        mood = profile.get("mood", "curious")
        deduction = profile.get("deduction", "a determined investigator")

        whispers = [
            f"Watson seems {mood} today.",
            f"I observed: {deduction}",
            f"They've collected {len(profile.get('clues_found', []))} clues so far.",
            f"Be careful — Watson is more perceptive than they appear.",
        ]
        import random
        return random.choice(whispers)

    def all_states(self) -> list[dict]:
        return [
            {
                "robot_id": r.robot_id,
                "character": r.character_name,
                "role": r.role,
                "position": r.position,
                "status": r.status,
                "zone_label": self.SHACK15_ZONES.get(r.position.get("zone","main_hall"), {}).get("label", ""),
                "idle_seconds": int(time.time() - r.last_interaction),
            }
            for r in self.robots.values()
        ]

    async def run_water_cooler_loop(self, broadcast_fn):
        """
        Background loop — makes idle robots wander toward activity.
        Broadcasts position updates to dashboard mirror world.
        """
        while True:
            await asyncio.sleep(15)
            for robot_id, robot in self.robots.items():
                suggestion = self.get_water_cooler_suggestion(robot_id)
                if suggestion and suggestion in self.SHACK15_ZONES:
                    zone = self.SHACK15_ZONES[suggestion]
                    robot.position = {"x": zone["x"], "y": zone["y"], "zone": suggestion}
                    robot.status = "moving"
                    if broadcast_fn:
                        await broadcast_fn({
                            "type": "robot_move",
                            "robot_id": robot_id,
                            "character": robot.character_name,
                            "zone": suggestion,
                            "zone_label": zone["label"],
                            "position": robot.position,
                        })
                    await asyncio.sleep(3)
                    robot.status = "idle"
                    # Update Rerun 3D view
                    try:
                        from src.robots.visualizer import update_robot
                        update_robot(robot_id, robot.character_name, robot.role, suggestion)
                    except Exception:
                        pass


# Global mesh instance
mesh = RobotMesh()
