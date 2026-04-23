"""
run_realtime_automation.py — Energy Management Engine Realtime Automation

Starts the Energy Management Engine and streams continuous energy node data
across ALL 7 node types to its /evaluate endpoint, showing realtime
predictions, suggestions, and dashboard/presentation updates.

Node Types Simulated (matching engine schema):
  - Solar Panel       (NRG-SOL-xxx) — solar_power_w, voltage, current, energy_kwh
  - Smart Meter       (NRG-MTR-xxx) — voltage, current, power_w, energy_kwh, power_factor
  - Battery Storage   (NRG-BAT-xxx) — battery_soc_pct, voltage, charge_rate_w
  - Grid Transformer  (NRG-GRD-xxx) — grid_load_pct, grid_temperature_c, fault_status
  - Occupancy Sensor  (NRG-OCC-xxx) — occupancy_detected, person_count
  - Water Meter       (NRG-H2O-xxx) — flow_rate_lpm, total_consumption_l, leak_detected
  - AC Unit           (NRG-AC-xxx)  — ac_power_w, set_temp_c, ac_mode, ac_state

Usage:
  python3 run_realtime_automation.py
  python3 run_realtime_automation.py --no-browser
  python3 run_realtime_automation.py --interval 1.0 --nodes-per-type 3
"""

import argparse
import datetime
import math
import os
import random
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ═══════════════════════════════════════════
# SIMULATED ENERGY NODES — All 7 Types
# ═══════════════════════════════════════════

class EnergyNodeSimulator:
    """Base class for all energy node simulators."""
    def __init__(self, node_id, node_type):
        self.node_id = node_id
        self.node_type = node_type
        self.domain = "energy"
        self.tick = 0  # for gradual drift

    def generate_payload(self):
        raise NotImplementedError

    def _base_payload(self, data):
        self.tick += 1
        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": data,
        }


class SolarPanelSim(EnergyNodeSimulator):
    """Simulates solar panels with diurnal output curve and cloud events."""
    def __init__(self, node_id):
        super().__init__(node_id, "solar_panel")
        self.base_capacity = random.uniform(600, 1000)
        self.cloud_state = False

    def generate_payload(self):
        hour = datetime.datetime.now().hour + datetime.datetime.now().minute / 60
        # Solar follows sine curve: 0 at night, peak at noon
        if 6 <= hour <= 19:
            sun_factor = max(0, math.sin((hour - 6) * math.pi / 13))
        else:
            sun_factor = 0

        # Random cloud events (15% chance toggle)
        if random.random() < 0.15:
            self.cloud_state = not self.cloud_state
        cloud_factor = random.uniform(0.1, 0.4) if self.cloud_state else 1.0

        power = round(self.base_capacity * sun_factor * cloud_factor + random.uniform(-20, 20), 1)
        power = max(0, power)
        voltage = round(36 + random.uniform(-4, 6) * sun_factor, 1)
        current = round(power / max(voltage, 1), 2)
        energy = round(random.uniform(5, 300) + self.tick * 0.1, 2)

        is_critical = power < 50 and 8 <= hour <= 17
        return self._base_payload({
            "solar_power_w": power,
            "voltage": voltage,
            "current": current,
            "energy_kwh": energy,
            "solar_status": "active" if power > 0 else "inactive",
            "is_critical": is_critical,
        })


class SmartMeterSim(EnergyNodeSimulator):
    """Simulates smart energy meters with realistic power factor drift."""
    def __init__(self, node_id):
        super().__init__(node_id, "smart_meter")
        self.base_load = random.uniform(1000, 4000)

    def generate_payload(self):
        hour = datetime.datetime.now().hour
        # Load higher during business hours
        load_factor = 1.3 if 8 <= hour <= 18 else 0.6
        load_jitter = random.uniform(0.8, 1.2)

        power = round(self.base_load * load_factor * load_jitter, 1)
        voltage = round(random.uniform(225, 240), 1)
        current = round(power / voltage, 2)
        energy = round(random.uniform(100, 800) + self.tick * 0.5, 2)
        # Power factor drifts — occasionally drops low
        pf = round(random.uniform(0.65, 0.78) if random.random() < 0.12
                    else random.uniform(0.88, 0.99), 3)

        return self._base_payload({
            "voltage": voltage,
            "current": current,
            "power_w": power,
            "energy_kwh": energy,
            "power_factor": pf,
            "is_critical": pf < 0.80,
        })


class BatteryStorageSim(EnergyNodeSimulator):
    """Simulates battery storage with charge/discharge cycles."""
    def __init__(self, node_id):
        super().__init__(node_id, "battery_storage")
        self.soc = random.uniform(30, 90)
        self.charging = random.choice([True, False])

    def generate_payload(self):
        # Drift SoC based on charge state
        if self.charging:
            self.soc += random.uniform(0.5, 3.0)
            if self.soc >= 95:
                self.charging = False
        else:
            self.soc -= random.uniform(0.3, 2.5)
            if self.soc <= 10:
                self.charging = True

        self.soc = max(0, min(100, self.soc))

        charge_rate = round(random.uniform(200, 800), 1) if self.charging \
                      else round(random.uniform(-900, -100), 1)
        voltage = round(48 + (self.soc / 100) * 8 + random.uniform(-1, 1), 1)
        status = "charging" if self.charging else "discharging"

        return self._base_payload({
            "battery_soc_pct": round(self.soc, 1),
            "voltage": voltage,
            "charge_rate_w": charge_rate,
            "battery_status": status,
            "is_critical": self.soc < 20,
        })


class GridTransformerSim(EnergyNodeSimulator):
    """Simulates grid transformers with load and temperature drift."""
    def __init__(self, node_id):
        super().__init__(node_id, "grid_transformer")
        self.load = random.uniform(40, 70)
        self.temp = random.uniform(45, 60)

    def generate_payload(self):
        hour = datetime.datetime.now().hour
        # Load peaks during afternoon
        peak_factor = 1.0 + 0.3 * max(0, math.sin((hour - 6) * math.pi / 12))
        self.load += random.uniform(-4, 5) * peak_factor
        self.load = max(15, min(100, self.load))

        # Temperature correlates with load
        self.temp = 35 + (self.load / 100) * 60 + random.uniform(-3, 3)
        self.temp = max(30, min(105, self.temp))

        fault = "warning" if self.load > 85 else "normal"
        if self.load > 95:
            fault = "fault"

        return self._base_payload({
            "grid_load_pct": round(self.load, 1),
            "grid_temperature_c": round(self.temp, 1),
            "fault_status": fault,
            "is_critical": self.load > 90,
        })


class OccupancySensorSim(EnergyNodeSimulator):
    """Simulates occupancy sensors with time-of-day patterns."""
    def __init__(self, node_id):
        super().__init__(node_id, "occupancy_sensor")
        self.base_count = random.randint(10, 50)

    def generate_payload(self):
        hour = datetime.datetime.now().hour
        # Occupancy follows campus schedule
        if 8 <= hour <= 12:
            factor = random.uniform(1.5, 3.0)
        elif 13 <= hour <= 17:
            factor = random.uniform(1.2, 2.5)
        elif 18 <= hour <= 21:
            factor = random.uniform(0.3, 0.8)
        else:
            factor = random.uniform(0.05, 0.2)

        count = max(0, int(self.base_count * factor + random.randint(-5, 10)))
        # Occasional overcrowding event
        if random.random() < 0.08:
            count = random.randint(110, 200)

        return self._base_payload({
            "occupancy_detected": count > 0,
            "person_count": count,
            "is_critical": count > 100,
        })


class WaterMeterSim(EnergyNodeSimulator):
    """Simulates smart water meters with rare leak events."""
    def __init__(self, node_id):
        super().__init__(node_id, "water_meter")
        self.total = random.uniform(500, 5000)
        self.leak_active = False

    def generate_payload(self):
        # Normal flow
        flow = round(random.uniform(3, 35), 1)

        # 5% chance to toggle leak state
        if random.random() < 0.05:
            self.leak_active = not self.leak_active

        if self.leak_active:
            flow = round(random.uniform(80, 180), 1)

        self.total += flow * 0.017  # accumulate
        self.total = round(self.total, 1)

        return self._base_payload({
            "flow_rate_lpm": flow,
            "total_consumption_l": self.total,
            "leak_detected": self.leak_active,
            "is_critical": self.leak_active,
        })


class ACUnitSim(EnergyNodeSimulator):
    """Simulates AC units with temperature and mode changes."""
    def __init__(self, node_id):
        super().__init__(node_id, "ac_unit")
        self.set_temp = random.uniform(22, 26)
        self.mode = random.choice(["cool", "auto", "fan"])
        self.state = "on"

    def generate_payload(self):
        hour = datetime.datetime.now().hour
        # AC load higher during hot afternoon
        if 11 <= hour <= 16:
            base_power = random.uniform(1500, 4000)
        elif 8 <= hour <= 20:
            base_power = random.uniform(800, 2200)
        else:
            base_power = random.uniform(200, 800)

        # Occasional overload spike (10%)
        if random.random() < 0.10:
            base_power = random.uniform(3600, 5500)

        # Occasionally toggle mode
        if random.random() < 0.05:
            self.mode = random.choice(["cool", "heat", "fan", "auto"])
        if random.random() < 0.03:
            self.state = "off" if self.state == "on" else "on"
            if self.state == "off":
                base_power = 0

        self.set_temp += random.uniform(-0.5, 0.5)
        self.set_temp = round(max(16, min(30, self.set_temp)), 1)

        return self._base_payload({
            "ac_power_w": round(base_power, 1),
            "set_temp_c": self.set_temp,
            "ac_mode": self.mode,
            "ac_state": self.state,
            "is_critical": base_power > 3500,
        })


# ═══════════════════════════════════════════
# NODE FACTORY
# ═══════════════════════════════════════════

NODE_TYPE_CONFIG = [
    ("Solar Panel",       "NRG-SOL", SolarPanelSim,      "☀️"),
    ("Smart Meter",       "NRG-MTR", SmartMeterSim,       "📊"),
    ("Battery Storage",   "NRG-BAT", BatteryStorageSim,   "🔋"),
    ("Grid Transformer",  "NRG-GRD", GridTransformerSim,  "⚡"),
    ("Occupancy Sensor",  "NRG-OCC", OccupancySensorSim,  "👥"),
    ("Water Meter",       "NRG-H2O", WaterMeterSim,       "💧"),
    ("AC Unit",           "NRG-AC",  ACUnitSim,           "❄️"),
]


def build_all_nodes(nodes_per_type: int):
    """Build multiple instances of each of the 7 energy node types."""
    nodes = []
    for label, prefix, NodeClass, icon in NODE_TYPE_CONFIG:
        for i in range(nodes_per_type):
            node_id = f"{prefix}-{i+1:03d}"
            nodes.append((NodeClass(node_id), icon, label))
    return nodes


# ═══════════════════════════════════════════
# SERVER MANAGEMENT
# ═══════════════════════════════════════════

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(base_url: str, timeout_seconds: int = 25) -> bool:
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


# ═══════════════════════════════════════════
# STREAMING LOGIC
# ═══════════════════════════════════════════

def format_metric_preview(payload):
    """Format a compact metric preview for console output."""
    data = payload.get("data", {})
    nt = payload.get("node_type", "")
    previews = {
        "solar_panel":      lambda d: f"solar={d.get('solar_power_w',0)}W v={d.get('voltage',0)}V",
        "smart_meter":      lambda d: f"power={d.get('power_w',0)}W pf={d.get('power_factor',0)}",
        "battery_storage":  lambda d: f"soc={d.get('battery_soc_pct',0)}% rate={d.get('charge_rate_w',0)}W",
        "grid_transformer": lambda d: f"load={d.get('grid_load_pct',0)}% temp={d.get('grid_temperature_c',0)}°C",
        "occupancy_sensor": lambda d: f"persons={d.get('person_count',0)}",
        "water_meter":      lambda d: f"flow={d.get('flow_rate_lpm',0)}LPM leak={'YES' if d.get('leak_detected') else 'no'}",
        "ac_unit":          lambda d: f"power={d.get('ac_power_w',0)}W mode={d.get('ac_mode','?')} set={d.get('set_temp_c',0)}°C",
    }
    fn = previews.get(nt, lambda d: str(d)[:60])
    return fn(data)


# ANSI colors
class C:
    G = '\033[92m'; Y = '\033[93m'; R = '\033[91m'; B = '\033[94m'
    CY = '\033[96m'; DIM = '\033[2m'; END = '\033[0m'; BOLD = '\033[1m'


def stream_node(node, icon, base_url, interval, stop_event, print_lock, stats):
    """Stream a single node's payloads to the engine /evaluate endpoint."""
    while not stop_event.is_set():
        payload = node.generate_payload()
        try:
            r = requests.post(f"{base_url}/evaluate", json=payload, timeout=10)
            if r.status_code == 200:
                resp = r.json()
                status = resp.get("overall_status", "?")
                color = {
                    "SAFE": C.G, "WARNING": C.Y, "CRITICAL": C.R
                }.get(status, C.DIM)
                stats["sent"] += 1
                if status == "CRITICAL":
                    stats["critical"] += 1
                elif status == "WARNING":
                    stats["warning"] += 1
            else:
                status = f"HTTP {r.status_code}"
                color = C.R
                stats["errors"] += 1
        except Exception as exc:
            status = "ERR"
            color = C.R
            stats["errors"] += 1

        preview = format_metric_preview(payload)
        with print_lock:
            ts = time.strftime("%H:%M:%S")
            print(f"  {C.DIM}{ts}{C.END}  {icon}  {C.B}{node.node_id:14s}{C.END}  "
                  f"{color}{status:8s}{C.END}  {C.DIM}{preview}{C.END}")

        # Jitter the interval slightly for realistic async behavior
        time.sleep(interval + random.uniform(-0.3, 0.3))


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Energy Engine Realtime Automation — streams all 7 energy node types."
    )
    parser.add_argument("--interval", type=float, default=1.5,
                        help="Seconds between sends per node (default: 1.5)")
    parser.add_argument("--nodes-per-type", type=int, default=2,
                        help="Number of nodes per type (default: 2, total = 7×N)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open browser automatically.")
    args = parser.parse_args()

    port = int(os.environ.get("ENERGY_ENGINE_PORT", "0")) or find_free_port()
    env = {**os.environ, "ENERGY_ENGINE_PORT": str(port)}
    base_url = f"http://127.0.0.1:{port}"
    total_nodes = 7 * args.nodes_per_type

    print(f"\n{C.CY}{'═' * 72}{C.END}")
    print(f"  {C.BOLD}⚡ Energy Management Engine — Realtime Automation{C.END}")
    print(f"  {C.DIM}Smart City Living Lab | Team Member 3: Raghuram{C.END}")
    print(f"{C.CY}{'═' * 72}{C.END}\n")
    print(f"  Engine URL:     {C.B}{base_url}{C.END}")
    print(f"  Node types:     {C.BOLD}7{C.END} (Solar, Meter, Battery, Grid, Occupancy, Water, AC)")
    print(f"  Nodes per type: {C.BOLD}{args.nodes_per_type}{C.END}")
    print(f"  Total nodes:    {C.BOLD}{total_nodes}{C.END}")
    print(f"  Send interval:  {C.BOLD}{args.interval:.1f}s{C.END}")
    print(f"\n  Starting Energy Engine server...")

    # ── Start the server ──
    server = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=SCRIPT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    # Drain server stdout in background
    def drain(proc):
        if proc.stdout:
            for _ in iter(proc.stdout.readline, ""):
                pass
    threading.Thread(target=drain, args=(server,), daemon=True).start()

    try:
        if not wait_for_health(base_url):
            print(f"\n  {C.R}[FAIL] Server failed to start within timeout.{C.END}")
            server.terminate()
            return

        print(f"  {C.G}[OK] Server is healthy!{C.END}\n")

        # Show endpoint links
        print(f"  {C.BOLD}Live Endpoints:{C.END}")
        print(f"    Dashboard:    {C.CY}{base_url}/dashboard{C.END}")
        print(f"    Presentation: {C.CY}{base_url}/presentation{C.END}")
        print(f"    Swagger:      {C.CY}{base_url}/docs{C.END}")
        print(f"    Health:       {C.CY}{base_url}/health{C.END}")
        print()

        # Open browser
        if not args.no_browser:
            webbrowser.open(f"{base_url}/dashboard")
            time.sleep(0.5)

        # ── Build nodes ──
        nodes = build_all_nodes(args.nodes_per_type)
        print(f"  {C.BOLD}Node Fleet ({total_nodes} nodes):{C.END}")
        for label, prefix, _, icon in NODE_TYPE_CONFIG:
            count = args.nodes_per_type
            ids = ", ".join(f"{prefix}-{i+1:03d}" for i in range(count))
            print(f"    {icon}  {label:20s} × {count}  ({ids})")
        print()

        print(f"  {C.Y}Streaming telemetry... Press Ctrl+C to stop.{C.END}\n")
        print(f"  {'─' * 68}")

        # ── Start streaming threads ──
        stop_event = threading.Event()
        print_lock = threading.Lock()
        stats = {"sent": 0, "critical": 0, "warning": 0, "errors": 0}

        threads = []
        for node, icon, label in nodes:
            t = threading.Thread(
                target=stream_node,
                args=(node, icon, base_url, args.interval, stop_event, print_lock, stats),
                daemon=True,
            )
            threads.append(t)

        # Stagger starts slightly
        for t in threads:
            t.start()
            time.sleep(0.1)

        # ── Run until Ctrl+C ──
        while True:
            time.sleep(10)
            with print_lock:
                total_sent = stats["sent"]
                crit = stats["critical"]
                warn = stats["warning"]
                errs = stats["errors"]
                print(f"\n  {C.DIM}[STATS] Sent: {total_sent} | "
                      f"{C.G}Safe: {total_sent - crit - warn - errs}{C.END}{C.DIM} | "
                      f"{C.Y}Warn: {warn}{C.END}{C.DIM} | "
                      f"{C.R}Crit: {crit}{C.END}{C.DIM} | "
                      f"Errors: {errs}{C.END}\n")

    except KeyboardInterrupt:
        print(f"\n\n  {C.Y}Stopping realtime automation...{C.END}")
    finally:
        stop_event.set() if 'stop_event' in locals() else None
        if 'threads' in locals():
            for t in threads:
                t.join(timeout=1.0)
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                pass
        total_sent = stats.get("sent", 0) if 'stats' in locals() else 0
        print(f"  {C.G}Automation stopped. Total telemetry sent: {total_sent}{C.END}\n")


if __name__ == "__main__":
    main()
