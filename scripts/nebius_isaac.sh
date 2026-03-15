#!/bin/bash
# nebius_isaac.sh — Spin up Isaac Sim on Nebius H100 + stream to browser
#
# Usage: ./scripts/nebius_isaac.sh YOUR_VM_IP
#
# Prerequisites:
#   1. Nebius VM already running (Ubuntu 24.04, H100)
#   2. SSH key set up
#   3. Your Nebius VM IP passed as argument
#
set -e

VM_IP="${1:-}"
if [ -z "$VM_IP" ]; then
  echo "Usage: ./scripts/nebius_isaac.sh YOUR_VM_IP"
  echo ""
  echo "Get your VM IP from: console.nebius.com → Compute → VM → Network → Public IPv4"
  exit 1
fi

echo "🚀 Setting up Isaac Sim on Nebius H100 at $VM_IP..."

# Create setup script to run on remote VM
cat > /tmp/isaac_setup.sh << 'REMOTE'
#!/bin/bash
set -e

echo "📦 Installing Isaac Sim dependencies..."

# Install Docker if not present
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker ubuntu
fi

# Pull Isaac Sim container (streaming mode)
echo "🐳 Pulling Isaac Sim container (this takes ~5 min)..."
sudo docker pull nvcr.io/nvidia/isaac-sim:4.2.0

# Create SPECTER robot scene script
mkdir -p ~/specter_isaac
cat > ~/specter_isaac/specter_scene.py << 'PYTHON'
import asyncio
import json
import websockets
import omni
from omni.isaac.kit import SimulationApp

# Start Isaac Sim in headless streaming mode
simulation_app = SimulationApp({
    "headless": False,
    "renderer": "RayTracedLighting",
    "streaming": True,
})

import omni.isaac.core.utils.stage as stage_utils
from omni.isaac.core import World
from omni.isaac.core.robots import Robot
import numpy as np

world = World()

# SHACK15 zone positions
ZONES = {
    "entrance":  (0.0, 0.0, 0.0),
    "main_hall": (3.0, 0.0, 2.0),
    "bay_view":  (6.0, 0.0, 5.0),
    "bar":       (8.0, 0.0, -1.0),
    "stage":     (5.0, 0.0, 1.0),
}

# Load Unitree G1 USD
G1_USD = "omniverse://localhost/NVIDIA/Assets/Isaac/4.2/Isaac/Robots/Unitree/G1/g1.usd"

robots = {}

def spawn_robot(robot_id, name, zone):
    pos = ZONES.get(zone, (3.0, 0.0, 2.0))
    robot = world.scene.add(Robot(
        prim_path=f"/World/Robots/{robot_id}",
        name=name,
        usd_path=G1_USD,
        position=np.array([pos[0], pos[2], pos[1]]),
    ))
    robots[robot_id] = robot
    return robot

# Spawn 3 robots at SHACK15 positions
spawn_robot("robot_0", "Holmes",  "bay_view")
spawn_robot("robot_1", "Suspect", "bar")
spawn_robot("robot_2", "Witness", "main_hall")

world.reset()

# Listen for position updates from SPECTER
async def listen_specter():
    async with websockets.connect("ws://localhost:8081/ws") as ws:
        await ws.send(json.dumps({"action": "ping"}))
        async for msg in ws:
            d = json.loads(msg)
            if d.get("type") == "robot_move":
                rid = d["robot_id"]
                zone = d.get("zone", "main_hall")
                pos = ZONES.get(zone, (3.0, 0.0, 2.0))
                if rid in robots:
                    robots[rid].set_world_pose(
                        position=np.array([pos[0], pos[2], pos[1]])
                    )
                    print(f"🤖 {rid} → {zone}")

# Run sim + SPECTER listener
async def main():
    asyncio.create_task(listen_specter())
    while simulation_app.is_running():
        world.step(render=True)
        await asyncio.sleep(0)

asyncio.run(main())
simulation_app.close()
PYTHON

echo "✅ Isaac Sim setup complete!"
echo ""
echo "To run Isaac Sim:"
echo "  sudo docker run --gpus all -it --network host \\"
echo "    -e ACCEPT_EULA=Y \\"
echo "    nvcr.io/nvidia/isaac-sim:4.2.0 \\"
echo "    python /root/specter_isaac/specter_scene.py"
echo ""
echo "Stream viewer: http://$HOSTNAME:8211/streaming/client/"
REMOTE

# Copy and run setup on VM
echo "📤 Copying setup script to VM..."
scp -o StrictHostKeyChecking=no /tmp/isaac_setup.sh ubuntu@$VM_IP:/tmp/
ssh -o StrictHostKeyChecking=no ubuntu@$VM_IP "bash /tmp/isaac_setup.sh"

echo ""
echo "✅ Done! To start Isaac Sim, SSH in and run:"
echo "   ssh ubuntu@$VM_IP"
echo "   sudo docker run --gpus all -it --network host -e ACCEPT_EULA=Y \\"
echo "     nvcr.io/nvidia/isaac-sim:4.2.0 python /root/specter_isaac/specter_scene.py"
echo ""
echo "📺 Stream URL: http://$VM_IP:8211/streaming/client/"
echo "   Open this in your browser — you'll see 3 G1 robots in SHACK15!"
echo "   They'll move when SPECTER assigns characters to zones."
