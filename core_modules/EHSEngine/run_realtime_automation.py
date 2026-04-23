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

from iot_generator import (  # noqa: E402
    AirQualityNode,
    NoiseMonitorNode,
    RadiationGasNode,
    SoilSensorNode,
    WaterQualityNode,
    WeatherStationNode,
)


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
    if node_type == "air_quality":
        return f"aqi={data.get('aqi')} pm25={data.get('pm25')}"
    if node_type == "water_quality":
        return f"water_ph={data.get('water_ph')} turbidity={data.get('turbidity_ntu')}"
    if node_type == "noise_monitor":
        return f"noise_db={data.get('noise_db')} peak_db={data.get('peak_db')}"
    if node_type == "weather_station":
        return f"temp={data.get('temperature_c')} uv={data.get('uv_index')}"
    if node_type == "soil_sensor":
        return f"moisture={data.get('soil_moisture_pct')} soil_ph={data.get('soil_ph')}"
    if node_type == "radiation_gas":
        return f"voc={data.get('voc_ppb')} radiation={data.get('radiation_usv')}"
    return str(data)


def build_nodes(per_type_nodes: int) -> List:
    adapter = SilentAdapter()
    nodes = []
    for i in range(per_type_nodes):
        nodes.append(AirQualityNode(f"EHS-AQI-LIVE-{i:02d}", adapter))
        nodes.append(WaterQualityNode(f"EHS-WTR-LIVE-{i:02d}", adapter))
        nodes.append(NoiseMonitorNode(f"EHS-NOS-LIVE-{i:02d}", adapter))
        nodes.append(WeatherStationNode(f"EHS-WEA-LIVE-{i:02d}", adapter))
        nodes.append(SoilSensorNode(f"EHS-SOL-LIVE-{i:02d}", adapter))
        nodes.append(RadiationGasNode(f"EHS-RAD-LIVE-{i:02d}", adapter))
    return nodes


def stream_node(node, base_url: str, interval_seconds: float, stop_event: threading.Event, print_lock: threading.Lock) -> None:
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
    parser = argparse.ArgumentParser(description="Start EHS realtime automation with continuous node streams.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between sends per node.")
    parser.add_argument("--per-type-nodes", type=int, default=2, help="Number of nodes per EHS node type.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically.")
    args = parser.parse_args()

    port = int(os.environ.get("EHS_ENGINE_PORT", "0")) or find_free_port()
    env = {**os.environ, "EHS_ENGINE_PORT": str(port)}
    base_url = f"http://127.0.0.1:{port}"

    print("=" * 72)
    print("EHS Realtime Automation")
    print(f"Engine URL: {base_url}")
    print(f"Per-type nodes: {args.per_type_nodes} | Interval: {args.interval:.1f}s")
    print("=" * 72)

    server = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(SCRIPT_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    try:
        if not wait_for_health(base_url):
            print("Failed to start EHS server in time.")
            return

        print("Server is healthy.")
        print(f"Presentation: {base_url}/presentation")
        print(f"Dashboard: {base_url}/dashboard")
        print("Press Ctrl+C to stop automation.")

        if not args.no_browser:
            webbrowser.open(f"{base_url}/presentation")

        nodes = build_nodes(args.per_type_nodes)
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
