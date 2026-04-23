"""
run_realtime_automation.py — Access Management Service: Live IoT Data Stream

Starts the Access Management gateway and streams continuous telemetry from
BOTH Energy (7 node types) and EHS (6 node types) IoT generators into
the /api/v1/telemetry endpoint, making the dashboard fully dynamic.

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
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ═══════════════════════════════════════════
# ENERGY NODE SIMULATORS (7 types)
# ═══════════════════════════════════════════

class NodeSim:
    def __init__(self, node_id, domain, node_type):
        self.node_id = node_id
        self.domain = domain
        self.node_type = node_type
        self.tick = 0

    def generate(self):
        self.tick += 1
        data = self._data()
        return {
            "node_id": self.node_id, "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": data,
        }

    def _data(self):
        return {}


class SolarSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "energy", "solar_panel")
        self.cap = random.uniform(600, 1000)
        self.cloudy = False

    def _data(self):
        h = datetime.datetime.now().hour + datetime.datetime.now().minute / 60
        sun = max(0, math.sin((h - 6) * math.pi / 13)) if 6 <= h <= 19 else 0
        if random.random() < 0.12: self.cloudy = not self.cloudy
        cf = random.uniform(0.1, 0.4) if self.cloudy else 1.0
        pw = max(0, round(self.cap * sun * cf + random.uniform(-20, 20), 1))
        return {"solar_power_w": pw, "voltage": round(36 + random.uniform(-3, 5) * sun, 1),
                "is_critical": pw < 50 and 8 <= h <= 17}


class MeterSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "energy", "smart_meter")
        self.base = random.uniform(1000, 4000)

    def _data(self):
        h = datetime.datetime.now().hour
        lf = 1.3 if 8 <= h <= 18 else 0.6
        pw = round(self.base * lf * random.uniform(0.8, 1.2), 1)
        pf = round(random.uniform(0.65, 0.78) if random.random() < 0.1 else random.uniform(0.88, 0.99), 3)
        return {"power_w": pw, "power_factor": pf, "is_critical": pf < 0.80}


class BatterySim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "energy", "battery_storage")
        self.soc = random.uniform(30, 90)
        self.charging = True

    def _data(self):
        if self.charging:
            self.soc += random.uniform(0.5, 3)
            if self.soc >= 95: self.charging = False
        else:
            self.soc -= random.uniform(0.3, 2.5)
            if self.soc <= 10: self.charging = True
        self.soc = max(0, min(100, self.soc))
        return {"battery_soc_pct": round(self.soc, 1),
                "charge_rate_w": round(random.uniform(200, 800) if self.charging else random.uniform(-900, -100), 1),
                "is_critical": self.soc < 20}


class GridSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "energy", "grid_transformer")
        self.load = random.uniform(40, 70)

    def _data(self):
        h = datetime.datetime.now().hour
        pf = 1.0 + 0.3 * max(0, math.sin((h - 6) * math.pi / 12))
        self.load += random.uniform(-4, 5) * pf
        self.load = max(15, min(100, self.load))
        return {"grid_load_pct": round(self.load, 1),
                "grid_temperature_c": round(35 + self.load / 100 * 60 + random.uniform(-3, 3), 1),
                "is_critical": self.load > 90}


class OccupancySim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "energy", "occupancy_sensor")
        self.base = random.randint(10, 50)

    def _data(self):
        h = datetime.datetime.now().hour
        f = {range(8, 13): 2.0, range(13, 18): 1.8, range(18, 22): 0.5}.get(
            next((r for r in [range(8, 13), range(13, 18), range(18, 22)] if h in r), None), 0.1)
        c = max(0, int(self.base * f + random.randint(-5, 10)))
        if random.random() < 0.06: c = random.randint(110, 200)
        return {"person_count": c, "is_critical": c > 100}


class WaterSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "energy", "water_meter")
        self.leak = False

    def _data(self):
        if random.random() < 0.04: self.leak = not self.leak
        flow = round(random.uniform(80, 180) if self.leak else random.uniform(3, 35), 1)
        return {"flow_rate_lpm": flow, "leak_detected": self.leak, "is_critical": self.leak}


class ACSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "energy", "ac_unit")

    def _data(self):
        h = datetime.datetime.now().hour
        pw = random.uniform(1500, 4000) if 11 <= h <= 16 else random.uniform(500, 1800)
        if random.random() < 0.08: pw = random.uniform(3600, 5500)
        return {"ac_power_w": round(pw, 1), "ac_mode": random.choice(["cool", "auto", "fan"]),
                "set_temp_c": round(random.uniform(22, 26), 1), "is_critical": pw > 3500}


# ═══════════════════════════════════════════
# EHS NODE SIMULATORS (6 types)
# ═══════════════════════════════════════════

class AirQualitySim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "ehs", "air_quality")

    def _data(self):
        spike = random.random() < 0.05
        aqi = random.randint(150, 400) if spike else random.randint(18, 65)
        return {"aqi": aqi, "pm25": round(aqi * 0.35 + random.uniform(-7, 7), 1),
                "temperature_c": round(random.uniform(17, 39), 1),
                "humidity_pct": round(random.uniform(28, 88), 1), "is_critical": spike}


class WaterQualitySim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "ehs", "water_quality")

    def _data(self):
        bad = random.random() < 0.04
        ph = round(random.uniform(3.5, 5.0) if bad else random.uniform(6.4, 8.6), 2)
        return {"water_ph": ph, "turbidity_ntu": round(random.uniform(50, 200) if bad else random.uniform(0.3, 6), 2),
                "is_critical": bad}


class NoiseSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "ehs", "noise_monitor")

    def _data(self):
        loud = random.random() < 0.08
        db = round(random.uniform(70, 100) if loud else random.uniform(32, 65), 1)
        return {"noise_db": db, "peak_db": round(db + random.uniform(3, 15), 1), "is_critical": db > 85}


class WeatherSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "ehs", "weather_station")

    def _data(self):
        h = datetime.datetime.now().hour
        t = round(25 + 8 * math.sin((h - 5) * math.pi / 12) + random.uniform(-2, 2), 1)
        uv = round(max(0, 8 * math.sin((h - 6) * math.pi / 12) + random.uniform(-1, 1)), 1) if 6 <= h <= 18 else 0
        return {"temperature_c": t, "humidity_pct": round(random.uniform(30, 80), 1),
                "wind_speed_ms": round(random.uniform(0, 15), 1), "uv_index": max(0, uv),
                "is_critical": uv > 8}


class SoilSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "ehs", "soil_sensor")

    def _data(self):
        return {"soil_moisture_pct": round(random.uniform(20, 75), 1),
                "soil_ph": round(random.uniform(5.4, 7.6), 2), "is_critical": False}


class RadGasSim(NodeSim):
    def __init__(self, nid):
        super().__init__(nid, "ehs", "radiation_gas")

    def _data(self):
        leak = random.random() < 0.03
        return {"voc_ppb": round(random.uniform(1500, 5000) if leak else random.uniform(50, 400)),
                "co_ppm": round(random.uniform(20, 80) if leak else random.uniform(0, 5), 1),
                "is_critical": leak}


# ═══════════════════════════════════════════
# NODE FLEET
# ═══════════════════════════════════════════

NODE_TYPES = [
    # Energy (7 types)
    ("Solar Panel",     "NRG-SOL", SolarSim,        "☀️"),
    ("Smart Meter",     "NRG-MTR", MeterSim,         "📊"),
    ("Battery",         "NRG-BAT", BatterySim,       "🔋"),
    ("Grid Transformer","NRG-GRD", GridSim,          "⚡"),
    ("Occupancy",       "NRG-OCC", OccupancySim,     "👥"),
    ("Water Meter",     "NRG-H2O", WaterSim,         "💧"),
    ("AC Unit",         "NRG-AC",  ACSim,            "❄️"),
    # EHS (6 types)
    ("Air Quality",     "EHS-AQI", AirQualitySim,    "🌫️"),
    ("Water Quality",   "EHS-WTR", WaterQualitySim,  "🧪"),
    ("Noise Monitor",   "EHS-NOS", NoiseSim,         "🔊"),
    ("Weather Station", "EHS-WEA", WeatherSim,       "🌤️"),
    ("Soil Sensor",     "EHS-SOL", SoilSim,          "🌱"),
    ("Radiation/Gas",   "EHS-RAD", RadGasSim,        "☢️"),
]


def build_fleet(per_type):
    fleet = []
    for label, prefix, Cls, icon in NODE_TYPES:
        for i in range(per_type):
            fleet.append((Cls(f"{prefix}-{i+1:03d}"), icon, label))
    return fleet


# ═══════════════════════════════════════════
# ANSI + STREAMING
# ═══════════════════════════════════════════

class C:
    G='\033[92m'; Y='\033[93m'; R='\033[91m'; B='\033[94m'
    CY='\033[96m'; DIM='\033[2m'; END='\033[0m'; BOLD='\033[1m'


def preview(payload):
    d = payload.get("data", {})
    parts = []
    for k, v in list(d.items())[:3]:
        if k == "is_critical": continue
        if isinstance(v, float): v = round(v, 1)
        parts.append(f"{k}={v}")
    return " ".join(parts)


def stream_node(node, icon, base_url, interval, stop, lock, stats):
    while not stop.is_set():
        payload = node.generate()
        try:
            r = requests.post(f"{base_url}/api/v1/telemetry", json=payload, timeout=10)
            ok = r.status_code == 200
            crit = payload["data"].get("is_critical", False)
            status = "CRITICAL" if crit else "OK"
            color = C.R if crit else C.G
            stats["sent"] += 1
            if crit: stats["critical"] += 1
        except Exception:
            status = "ERR"
            color = C.R
            stats["errors"] += 1

        with lock:
            ts = time.strftime("%H:%M:%S")
            dom = C.Y if node.domain == "energy" else C.CY
            print(f"  {C.DIM}{ts}{C.END}  {icon}  {dom}{node.domain:6s}{C.END}  "
                  f"{C.B}{node.node_id:14s}{C.END}  {color}{status:8s}{C.END}  "
                  f"{C.DIM}{preview(payload)}{C.END}")

        time.sleep(interval + random.uniform(-0.2, 0.2))


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description="Access Management Gateway — Live IoT Stream")
    parser.add_argument("--interval", type=float, default=1.5, help="Seconds between sends per node")
    parser.add_argument("--nodes-per-type", type=int, default=2, help="Nodes per type (total = 13×N)")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    port = int(os.environ.get("ACCESS_SERVICE_PORT", "0")) or find_free_port()
    env = {**os.environ, "ACCESS_SERVICE_PORT": str(port)}
    base = f"http://127.0.0.1:{port}"
    total = 13 * args.nodes_per_type

    print(f"\n{C.CY}{'═' * 72}{C.END}")
    print(f"  {C.BOLD}🏛️  Access Management Gateway — Live IoT Data Stream{C.END}")
    print(f"  {C.DIM}Smart City Living Lab | Team 32 | Energy + EHS Domains{C.END}")
    print(f"{C.CY}{'═' * 72}{C.END}\n")
    print(f"  Gateway URL:    {C.B}{base}{C.END}")
    print(f"  Domains:        {C.BOLD}2{C.END} (Energy: 7 types, EHS: 6 types)")
    print(f"  Nodes per type: {C.BOLD}{args.nodes_per_type}{C.END}")
    print(f"  Total nodes:    {C.BOLD}{total}{C.END}")
    print(f"  Interval:       {C.BOLD}{args.interval:.1f}s{C.END}")
    print(f"\n  Starting Access Management server...")

    server = subprocess.Popen(
        [sys.executable, "main.py"], cwd=SCRIPT_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    # Drain stdout
    threading.Thread(target=lambda: [None for _ in iter(server.stdout.readline, "")], daemon=True).start()

    # Wait for health
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if requests.get(f"{base}/health", timeout=2).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print(f"  {C.R}[FAIL] Server didn't start in time.{C.END}")
        server.terminate()
        return

    print(f"  {C.G}[OK] Server healthy!{C.END}\n")

    print(f"  {C.BOLD}Live Endpoints:{C.END}")
    print(f"    Dashboard: {C.CY}{base}/dashboard{C.END}  (login as admin/admin123)")
    print(f"    Swagger:   {C.CY}{base}/docs{C.END}")
    print()

    if not args.no_browser:
        webbrowser.open(f"{base}/dashboard")
        time.sleep(0.5)

    fleet = build_fleet(args.nodes_per_type)
    print(f"  {C.BOLD}Node Fleet ({total} nodes across 13 types):{C.END}")
    for label, prefix, _, icon in NODE_TYPES:
        ids = ", ".join(f"{prefix}-{i+1:03d}" for i in range(args.nodes_per_type))
        print(f"    {icon}  {label:20s} × {args.nodes_per_type}  ({ids})")
    print(f"\n  {C.Y}Streaming data... Press Ctrl+C to stop.{C.END}")
    print(f"  {'─' * 68}")

    stop = threading.Event()
    lock = threading.Lock()
    stats = {"sent": 0, "critical": 0, "errors": 0}

    threads = []
    for node, icon, label in fleet:
        t = threading.Thread(target=stream_node, args=(node, icon, base, args.interval, stop, lock, stats), daemon=True)
        threads.append(t)

    for t in threads:
        t.start()
        time.sleep(0.08)

    try:
        while True:
            time.sleep(10)
            with lock:
                s, cr, er = stats["sent"], stats["critical"], stats["errors"]
                safe = s - cr - er
                print(f"\n  {C.DIM}[STATS] Sent: {s} | "
                      f"{C.G}Safe: {safe}{C.END}{C.DIM} | "
                      f"{C.R}Crit: {cr}{C.END}{C.DIM} | "
                      f"Errors: {er}{C.END}\n")
    except KeyboardInterrupt:
        print(f"\n\n  {C.Y}Stopping...{C.END}")
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=1)
        if server.poll() is None:
            server.terminate()
            try: server.wait(timeout=5)
            except: pass
        print(f"  {C.G}Done. Total sent: {stats['sent']}{C.END}\n")


if __name__ == "__main__":
    main()
