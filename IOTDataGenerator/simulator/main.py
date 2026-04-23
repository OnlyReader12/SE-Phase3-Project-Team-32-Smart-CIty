"""
Smart City IoT Simulator — Entry Point

Reads node_schemas.json, instantiates all nodes, connects to transport
backends (HTTP, MQTT, CoAP, WebSocket) and runs 100 async node coroutines
concurrently via asyncio.gather().

Usage (from IOTDataGenerator/ directory):
    python simulator/main.py

The simulator gracefully logs errors per-node and never crashes due to
a single bad node or unreachable backend.
"""
import asyncio
import os
import sys

# ── Path bootstrap ─────────────────────────────────────────────────────────
# Add the simulator/ directory itself to sys.path so that sub-packages
# (generators, transport, engine) can be imported without the 'simulator.'
# prefix, keeping all internal imports clean and backend-agnostic.
_SIM_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SIM_DIR)
# ───────────────────────────────────────────────────────────────────────────

from node_factory import NodeFactory

# node_schemas.json lives one level above simulator/ (i.e. in IOTDataGenerator/)
_SCHEMA_PATH = os.path.join(_SIM_DIR, "..", "node_schemas.json")


async def main():
    print("=" * 60)
    print("  Smart City IoT Simulator  ─  Schema-Driven v2")
    print("  github.com/SE-Phase3-Project-Team-32")
    print("=" * 60 + "\n")

    # 1. Build all nodes from JSON schema
    factory = NodeFactory(_SCHEMA_PATH)
    nodes, senders = factory.build_all()

    # 2. Start transport backends (open sessions, connect to brokers)
    print("[Simulator] Starting transport senders …")
    for proto_name, sender in senders.items():
        await sender.start()
    print("[Simulator] All transport senders ready.\n")

    # 3. Launch all node coroutines concurrently
    print(f"[Simulator] Launching {len(nodes)} nodes …  (Ctrl+C to stop)\n")
    try:
        await asyncio.gather(*[node.run() for node in nodes])
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Simulator] Gracefully stopped by user.")
