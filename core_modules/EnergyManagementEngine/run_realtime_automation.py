"""
run_realtime_automation.py — Energy Management Engine Realtime Automation

Starts the Energy Management Engine and streams continuous energy node data
to its /evaluate endpoint, showing realtime predictions, suggestions, and
dashboard/presentation updates.

Usage:
  python run_realtime_automation.py --interval 1.2 --per-type-nodes 1
  python run_realtime_automation.py --no-browser
  python run_realtime_automation.py --per-type-nodes 2 --interval 2.0

Equivalent to the EHS run_realtime_automation.py but for Energy (port 8003).
"""

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Dict, List

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
IOT_GENERATOR_DIR = REPO_ROOT / "IOTDataGenerator"

if str(IOT_GENERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(IOT_GENERATOR_DIR))

from iot_generator import EnergyNode


class SilentAdapter:
    def send(self, payload):
        pass


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(base_url: str, timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def metric_preview(payload: Dict) -> str:
    node_type = payload.get("node_type", "unknown")
    data = payload.get("data", {})
    if node_type == "power_monitor":
        return f"solar={data.get('solar_generation_watts')}W ac={data.get('ac_consumption_watts')}W"
    return str(data)


def build_energy_nodes(per_type_nodes: int) -> List:
    """Build replicated energy power monitor nodes."""
    adapter = SilentAdapter()
    nodes = []
    for i in range(per_type_nodes):
        nodes.append(EnergyNode(f"PWR-NODE-{i:02d}", adapter))
    return nodes


def stream_node(node, base_url: str, interval_seconds: float, stop_event: threading.Event, print_lock: threading.Lock) -> None:
    """Stream a single node's payloads to the engine /evaluate endpoint."""
    while not stop_event.is_set():
        payload = node.generate_payload()
        try:
            r = requests.post(f"{base_url}/evaluate", json=payload, timeout=8)
            status = "OK" if r.status_code == 200 else f"HTTP {r.status_code}"
        except Exception as exc:
            status = f"ERR {exc}"

        with print_lock:
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] {node.node_id:18s} {node.node_type:14s} -> {status} | {metric_preview(payload)}")

        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Energy Management Engine realtime automation with continuous node streams.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between sends per node.")
    parser.add_argument("--per-type-nodes", type=int, default=2, help="Number of power monitor nodes.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically.")
    args = parser.parse_args()

    energy_engine_dir = REPO_ROOT / "core_modules" / "EnergyManagementEngine"
    port = int(os.environ.get("ENERGY_ENGINE_PORT", "0")) or find_free_port()
    env = {**os.environ, "ENERGY_ENGINE_PORT": str(port)}
    base_url = f"http://127.0.0.1:{port}"

    print("=" * 72)
    print("Energy Management Engine Realtime Automation")
    print(f"Engine URL: {base_url}")
    print(f"Per-type nodes: {args.per_type_nodes} | Interval: {args.interval:.1f}s")
    print("=" * 72)

    server = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(energy_engine_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    try:
        if not wait_for_health(base_url):
            print("Failed to start Energy engine in time.")
            return

        print("Server is healthy.")
        print(f"Presentation: {base_url}/presentation")
        print(f"Dashboard: {base_url}/dashboard")
        print("Press Ctrl+C to stop automation.")

        if not args.no_browser:
            webbrowser.open(f"{base_url}/presentation")

        nodes = build_energy_nodes(args.per_type_nodes)
        stop_event = threading.Event()
        print_lock = threading.Lock()

        threads = [
            threading.Thread(
                target=stream_node,
                args=(node, base_url, args.interval, stop_event, print_lock),
                daemon=True,
            )
            for node in nodes
        ]

        for t in threads:
            t.start()

        while True:
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping realtime automation...")
    finally:
        try:
            if 'stop_event' in locals():
                stop_event.set()
            if 'threads' in locals():
                for t in threads:
                    t.join(timeout=1.0)
        finally:
            if server and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except Exception:
                    pass
            print("Automation stopped.")


if __name__ == "__main__":
    main()
