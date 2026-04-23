"""
ingestion_service.py — Microservice 1: Data Ingestion (Store) v4

Port: 8006

Receives telemetry from IoT generators & stores in SQLite.
v4: Emergency alert detection, HLD CPU simulation, user-level node management.
"""

import json, os, sys, time, resource, threading
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE_DIR)

from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import deque

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database.connection import DatabaseManager
from database.seed import seed_database

# Load .env
def _load_env():
    env_path = os.path.join(_BASE_DIR, "..", "AlertManagement", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
_load_env()

SERVER_PORT = int(os.getenv("INGESTION_SERVICE_PORT", "8006"))
WORKER_ID = os.getenv("WORKER_ID", "w0")
ALERT_MGR_URL = os.getenv("ALERT_MANAGER_URL", "http://127.0.0.1:8008")

db = DatabaseManager(os.path.join(_BASE_DIR, "smartcity.db"))

app = FastAPI(
    title="Smart City Data Ingestion Service",
    description="Microservice 1: IoT data → SQLite + Emergency Detection + HLD Sim",
    version="4.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ═══════════════════════════════════════════
# Engine Metrics
# ═══════════════════════════════════════════
ENGINE = {
    "start_time": None,
    "ingest_count": 0,
    "ingest_errors": 0,
    "last_100_latencies_ms": deque(maxlen=100),
    "last_report_at": None,
    "worker_id": WORKER_ID,
}

# ═══════════════════════════════════════════
# HLD CPU Simulation
# ═══════════════════════════════════════════
HLD = {
    "cpu_count": int(os.getenv("HLD_INITIAL_CPU_COUNT", "4")),
    "cpu_warning_pct": int(os.getenv("HLD_CPU_WARNING_PCT", "70")),
    "cpu_critical_pct": int(os.getenv("HLD_CPU_CRITICAL_PCT", "85")),
    "scale_history": [],
    "cpu_alert_sent": False,
}

# ═══════════════════════════════════════════
# Control State
# ═══════════════════════════════════════════
CONTROL = {"interval": 1.5}
PENDING_NODES = []
REMOVED_NODES = set()

# ═══════════════════════════════════════════
# Alert Dedup (don't spam same alert)
# ═══════════════════════════════════════════
_ALERT_COOLDOWN = {}  # node_id:alert_type → last_sent_time
ALERT_COOLDOWN_SECS = 60  # same alert refire cooldown


@app.on_event("startup")
async def startup():
    db.initialize()
    counts = seed_database(db)
    if counts["roles"] > 0:
        print(f"[SEED] Created: {counts}")
    ENGINE["start_time"] = time.time()
    total = db.fetchone("SELECT COUNT(*) as c FROM telemetry_readings")
    nodes = db.fetchone("SELECT COUNT(*) as c FROM nodes")
    ENGINE["ingest_count"] = total["c"]
    print(f"[DB] Telemetry: {total['c']} records | Nodes: {nodes['c']} registered")
    print(f"[ENGINE] Worker {WORKER_ID} on port {SERVER_PORT} | Alert Manager: {ALERT_MGR_URL}")


# ═══════════════════════════════════════════
# Models
# ═══════════════════════════════════════════

class TelemetryPayload(BaseModel):
    node_id: str
    domain: str
    node_type: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    data: Dict[str, Any]

class BatchPayload(BaseModel):
    readings: List[TelemetryPayload]

class AddNodePayload(BaseModel):
    node_id: str
    domain: str
    node_type: str
    location: str = "Dynamic"
    user_id: Optional[int] = None

class RemoveNodePayload(BaseModel):
    node_id: str

class IntervalPayload(BaseModel):
    interval: float = Field(ge=0.3, le=10.0)

class AddBulkNodesPayload(BaseModel):
    count: int = Field(ge=1, le=50)
    domain: str = "energy"
    node_type: str = "solar_panel"
    prefix: str = "DYN"

class ScaleCPUPayload(BaseModel):
    new_count: int = Field(ge=1, le=32)


# ═══════════════════════════════════════════
# Node Auto-Registration
# ═══════════════════════════════════════════

def _ensure_node_registered(node_id_str, domain_name, type_name):
    existing = db.fetchone("SELECT id FROM nodes WHERE node_id = ?", (node_id_str,))
    if existing:
        db.execute("UPDATE nodes SET last_seen = ? WHERE id = ?",
                   (datetime.now().isoformat(), existing["id"]))
        return existing["id"]
    domain = db.fetchone("SELECT id FROM domains WHERE name = ?", (domain_name,))
    if not domain:
        db.execute("INSERT INTO domains (name, label, description) VALUES (?, ?, ?)",
                   (domain_name, domain_name.title(), f"Auto-registered: {domain_name}"))
        domain = db.fetchone("SELECT id FROM domains WHERE name = ?", (domain_name,))
    node_type = db.fetchone("SELECT id FROM node_types WHERE domain_id = ? AND type_name = ?",
                            (domain["id"], type_name))
    if not node_type:
        db.execute("INSERT INTO node_types (domain_id, type_name, label, protocol) VALUES (?, ?, ?, 'HTTP')",
                   (domain["id"], type_name, type_name.replace("_", " ").title()))
        node_type = db.fetchone("SELECT id FROM node_types WHERE domain_id = ? AND type_name = ?",
                                (domain["id"], type_name))
    now = datetime.now().isoformat()
    db.execute("INSERT INTO nodes (node_id, node_type_id, is_active, first_seen, last_seen) VALUES (?, ?, 1, ?, ?)",
               (node_id_str, node_type["id"], now, now))
    node = db.fetchone("SELECT id FROM nodes WHERE node_id = ?", (node_id_str,))
    return node["id"]


# ═══════════════════════════════════════════
# Emergency Detection
# ═══════════════════════════════════════════

def _check_emergency(node_id, domain, node_type, data):
    """Check telemetry for emergency conditions and fire alerts."""
    alerts = []

    # EHS alerts
    if node_type == "air_quality":
        aqi = data.get("aqi", 0)
        if aqi > 200:
            alerts.append(("EMERGENCY", "aqi_critical", f"AQI={aqi} (>200) — hazardous air quality"))
        elif aqi > 100:
            alerts.append(("WARNING", "aqi_high", f"AQI={aqi} (>100) — unhealthy air quality"))

    if node_type == "water_quality":
        ph = data.get("water_ph", 7.0)
        if ph < 5.0 or ph > 9.0:
            alerts.append(("WARNING", "ph_abnormal", f"Water pH={ph} — outside safe range (5-9)"))

    if node_type == "noise_monitor":
        db_level = data.get("noise_db", 0)
        if db_level > 65:
            alerts.append(("WARNING", "noise_high", f"Noise={db_level}dB (>65) — exceeds safe level"))

    if node_type == "radiation_gas":
        co = data.get("co_ppm", 0)
        if co > 8:
            alerts.append(("EMERGENCY", "co_hazard", f"CO={co}ppm (>8) — carbon monoxide hazard"))

    # Energy alerts
    if node_type == "battery_storage":
        soc = data.get("battery_soc_pct", 100)
        if soc < 10:
            alerts.append(("EMERGENCY", "battery_critical", f"Battery SOC={soc}% (<10%) — critically low"))

    if node_type == "grid_transformer":
        load = data.get("grid_load_pct", 0)
        temp = data.get("grid_temperature_c", 0)
        if load > 95:
            alerts.append(("EMERGENCY", "grid_overload", f"Grid load={load}% (>95%) — overload risk"))
        if temp > 90:
            alerts.append(("EMERGENCY", "grid_overheat", f"Grid temp={temp}°C (>90°C) — overheating"))

    if node_type == "water_meter":
        if data.get("leak_detected", False):
            alerts.append(("EMERGENCY", "water_leak", "Water leak detected!"))

    # Fire alerts
    for severity, alert_type, message in alerts:
        _fire_alert(node_id, domain, severity, alert_type, message, data)


def _fire_alert(node_id, domain, severity, alert_type, message, data):
    """Send alert to Alert Manager (with dedup cooldown)."""
    key = f"{node_id}:{alert_type}"
    now = time.time()
    if key in _ALERT_COOLDOWN and (now - _ALERT_COOLDOWN[key]) < ALERT_COOLDOWN_SECS:
        return  # cooldown active
    _ALERT_COOLDOWN[key] = now

    # Store in alerts table
    try:
        db.execute(
            "INSERT INTO alerts (node_id, severity, alert_type, message, domain, data_json, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
            (node_id, severity, alert_type, message, domain, json.dumps(data), datetime.now().isoformat())
        )
    except:
        pass  # alerts table might not have all columns yet

    # POST to Alert Manager
    try:
        import requests
        requests.post(f"{ALERT_MGR_URL}/alert", json={
            "node_id": node_id, "domain": domain, "severity": severity,
            "alert_type": alert_type, "message": message, "data": data,
        }, timeout=3)
    except:
        pass  # Alert Manager might not be running


# ═══════════════════════════════════════════
# Routes: Info & Health
# ═══════════════════════════════════════════

@app.get("/", tags=["info"])
def root():
    return {"service": "Smart City Data Ingestion Service", "version": "4.0.0", "port": SERVER_PORT, "worker": WORKER_ID}

@app.get("/health", tags=["info"])
def health():
    total = db.fetchone("SELECT COUNT(*) as c FROM telemetry_readings")
    nodes = db.fetchone("SELECT COUNT(*) as c FROM nodes")
    domains = db.fetchall("SELECT name FROM domains")
    return {
        "status": "healthy", "service": "DataIngestionService",
        "port": SERVER_PORT, "worker": WORKER_ID, "database": "SQLite (WAL mode)",
        "total_readings": total["c"], "registered_nodes": nodes["c"],
        "domains": [d["name"] for d in domains],
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════
# Routes: Telemetry Ingestion
# ═══════════════════════════════════════════

@app.post("/ingest", tags=["telemetry"])
def ingest(payload: TelemetryPayload):
    t0 = time.time()
    try:
        node_pk = _ensure_node_registered(payload.node_id, payload.domain, payload.node_type)
        is_critical = 1 if payload.data.get("is_critical", False) else 0
        now = datetime.now().isoformat()
        db.execute(
            """INSERT INTO telemetry_readings
               (node_pk, domain_name, node_type_name, node_id_str, timestamp, data_json, is_critical, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_pk, payload.domain, payload.node_type, payload.node_id,
             payload.timestamp, json.dumps(payload.data), is_critical, now)
        )
        ENGINE["ingest_count"] += 1
        ENGINE["last_100_latencies_ms"].append((time.time() - t0) * 1000)

        # Emergency detection
        _check_emergency(payload.node_id, payload.domain, payload.node_type, payload.data)

        return {"status": "stored", "node_id": payload.node_id, "domain": payload.domain, "is_critical": bool(is_critical)}
    except Exception as e:
        ENGINE["ingest_errors"] += 1
        raise HTTPException(500, str(e))

@app.post("/ingest/batch", tags=["telemetry"])
def ingest_batch(batch: BatchPayload):
    stored = critical = 0
    for payload in batch.readings:
        t0 = time.time()
        try:
            node_pk = _ensure_node_registered(payload.node_id, payload.domain, payload.node_type)
            is_crit = 1 if payload.data.get("is_critical", False) else 0
            now = datetime.now().isoformat()
            db.execute(
                """INSERT INTO telemetry_readings
                   (node_pk, domain_name, node_type_name, node_id_str, timestamp, data_json, is_critical, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (node_pk, payload.domain, payload.node_type, payload.node_id,
                 payload.timestamp, json.dumps(payload.data), is_crit, now)
            )
            stored += 1
            if is_crit: critical += 1
            ENGINE["ingest_count"] += 1
            ENGINE["last_100_latencies_ms"].append((time.time() - t0) * 1000)
            _check_emergency(payload.node_id, payload.domain, payload.node_type, payload.data)
        except:
            ENGINE["ingest_errors"] += 1
    return {"status": "batch_stored", "stored": stored, "critical": critical}


# ═══════════════════════════════════════════
# Routes: Engine Health & System Metrics (HLD)
# ═══════════════════════════════════════════

def _get_system_metrics():
    """Collect simulated HLD CPU + real memory metrics."""
    # Simulated CPU based on node count and HLD config
    active_nodes_row = db.fetchone("SELECT COUNT(*) as c FROM nodes WHERE is_active = 1")
    active_nodes = active_nodes_row["c"] if active_nodes_row else 0
    uptime = time.time() - (ENGINE["start_time"] or time.time())
    rps = ENGINE["ingest_count"] / max(1, uptime)

    # Simulated CPU usage: more nodes + higher RPS → higher CPU
    cpu_count = HLD["cpu_count"]
    raw_load = (active_nodes * 1.5) + (rps * 0.3)
    cpu_usage_pct = round(min(100, raw_load / (cpu_count / 4) ), 1)

    # Real memory
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        mem_mb = round(ru.ru_maxrss / (1024 * 1024), 1)
    except:
        mem_mb = 0

    db_path = os.path.join(_BASE_DIR, "smartcity.db")
    db_size_mb = round(os.path.getsize(db_path) / (1024*1024), 2) if os.path.exists(db_path) else 0
    thread_count = threading.active_count()

    # CPU auto-alert
    status = "NORMAL"
    if cpu_usage_pct >= HLD["cpu_critical_pct"]:
        status = "CRITICAL"
        if not HLD["cpu_alert_sent"]:
            HLD["cpu_alert_sent"] = True
            _fire_alert("SYSTEM", "system", "EMERGENCY", "cpu_overload",
                        f"CPU usage {cpu_usage_pct}% (>{HLD['cpu_critical_pct']}%) — scale up needed!", {})
    elif cpu_usage_pct >= HLD["cpu_warning_pct"]:
        status = "WARNING"
        HLD["cpu_alert_sent"] = False
    else:
        HLD["cpu_alert_sent"] = False

    return {
        "cpu_count": cpu_count,
        "cpu_usage_pct": cpu_usage_pct,
        "cpu_status": status,
        "memory_mb": mem_mb,
        "thread_count": thread_count,
        "db_size_mb": db_size_mb,
        "pid": os.getpid(),
        "active_nodes": active_nodes,
    }


@app.get("/engine-health", tags=["engine"])
def engine_health():
    uptime = time.time() - (ENGINE["start_time"] or time.time())
    rps = ENGINE["ingest_count"] / max(1, uptime)
    lats = list(ENGINE["last_100_latencies_ms"])
    avg_lat = sum(lats) / len(lats) if lats else 0
    max_lat = max(lats) if lats else 0
    sys_metrics = _get_system_metrics()

    return {
        "worker_id": WORKER_ID,
        "uptime_seconds": round(uptime, 1),
        "total_ingested": ENGINE["ingest_count"],
        "total_errors": ENGINE["ingest_errors"],
        "records_per_second": round(rps, 2),
        "avg_latency_ms": round(avg_lat, 2),
        "max_latency_ms": round(max_lat, 2),
        "active_nodes": sys_metrics["active_nodes"],
        "system": sys_metrics,
        "hld": {
            "cpu_count": HLD["cpu_count"],
            "cpu_warning_pct": HLD["cpu_warning_pct"],
            "cpu_critical_pct": HLD["cpu_critical_pct"],
            "scale_history": HLD["scale_history"][-10:],
        },
        "interval": CONTROL["interval"],
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/engine-report", tags=["engine"])
def engine_report():
    uptime = time.time() - (ENGINE["start_time"] or time.time())
    domain_stats = db.fetchall("""
        SELECT domain_name, COUNT(*) as total, SUM(is_critical) as critical,
               MIN(timestamp) as first_ts, MAX(timestamp) as last_ts
        FROM telemetry_readings GROUP BY domain_name
    """)
    type_stats = db.fetchall("""
        SELECT node_type_name, domain_name, COUNT(*) as total, SUM(is_critical) as critical
        FROM telemetry_readings GROUP BY node_type_name, domain_name ORDER BY total DESC
    """)
    faulty = db.fetchall("""
        SELECT node_id_str, node_type_name, domain_name, COUNT(*) as fault_readings
        FROM telemetry_readings WHERE json_extract(data_json, '$.fault_code') > 0
        GROUP BY node_id_str ORDER BY fault_readings DESC LIMIT 10
    """)
    low_battery = db.fetchall("""
        SELECT node_id_str, json_extract(data_json, '$.battery_level_pct') as battery
        FROM telemetry_readings
        WHERE id IN (SELECT MAX(id) FROM telemetry_readings GROUP BY node_id_str)
        AND json_extract(data_json, '$.battery_level_pct') < 30
        ORDER BY battery ASC LIMIT 10
    """)
    ENGINE["last_report_at"] = datetime.now().isoformat()
    return {
        "report_type": "engine_health",
        "generated_at": ENGINE["last_report_at"],
        "uptime_seconds": round(uptime, 1),
        "total_records": ENGINE["ingest_count"],
        "records_per_second": round(ENGINE["ingest_count"] / max(1, uptime), 2),
        "domain_breakdown": domain_stats,
        "node_type_breakdown": type_stats,
        "top_faulty_nodes": faulty,
        "low_battery_nodes": low_battery,
    }


# ═══════════════════════════════════════════
# Routes: HLD Scaling
# ═══════════════════════════════════════════

@app.post("/hld/scale-cpu", tags=["hld"])
def scale_cpu(payload: ScaleCPUPayload):
    old = HLD["cpu_count"]
    HLD["cpu_count"] = payload.new_count
    HLD["cpu_alert_sent"] = False
    decision = {
        "action": "SCALE_CPU",
        "old": old, "new": payload.new_count,
        "time": datetime.now().isoformat(),
    }
    HLD["scale_history"].append(decision)
    return {"status": "scaled", "old_cpu": old, "new_cpu": payload.new_count}


# ═══════════════════════════════════════════
# Routes: Node & Data Rate Control
# ═══════════════════════════════════════════

@app.get("/control/actuators", tags=["control"])
def get_control_state():
    return CONTROL

@app.post("/control/set-interval", tags=["control"])
def set_interval(payload: IntervalPayload):
    old = CONTROL["interval"]
    CONTROL["interval"] = payload.interval
    return {"status": "updated", "old_interval": old, "new_interval": payload.interval}

@app.post("/control/add-node", tags=["control"])
def add_node(payload: AddNodePayload):
    _ensure_node_registered(payload.node_id, payload.domain, payload.node_type)
    # Map to user if provided
    if payload.user_id:
        try:
            db.execute("INSERT OR IGNORE INTO user_nodes (user_id, node_id_str) VALUES (?, ?)",
                       (payload.user_id, payload.node_id))
        except:
            pass
    PENDING_NODES.append({
        "node_id": payload.node_id, "domain": payload.domain,
        "node_type": payload.node_type, "added_at": datetime.now().isoformat(),
    })
    return {"status": "added", "node_id": payload.node_id}

@app.post("/control/add-bulk-nodes", tags=["control"])
def add_bulk_nodes(payload: AddBulkNodesPayload):
    import random
    added = []
    for i in range(payload.count):
        nid = f"{payload.prefix}-{payload.node_type[:3].upper()}-{random.randint(100,999)}"
        _ensure_node_registered(nid, payload.domain, payload.node_type)
        PENDING_NODES.append({
            "node_id": nid, "domain": payload.domain,
            "node_type": payload.node_type, "added_at": datetime.now().isoformat(),
        })
        added.append(nid)
    return {"status": "added", "count": len(added), "node_ids": added}

@app.post("/control/remove-node", tags=["control"])
def remove_node(payload: RemoveNodePayload):
    db.execute("UPDATE nodes SET is_active = 0 WHERE node_id = ?", (payload.node_id,))
    REMOVED_NODES.add(payload.node_id)
    return {"status": "deactivated", "node_id": payload.node_id}

@app.get("/control/pending-nodes", tags=["control"])
def pending_nodes():
    return {"nodes": PENDING_NODES}

@app.post("/control/ack-node", tags=["control"])
def ack_node(payload: RemoveNodePayload):
    PENDING_NODES[:] = [n for n in PENDING_NODES if n["node_id"] != payload.node_id]
    return {"status": "acknowledged", "node_id": payload.node_id}

@app.get("/control/fleet-status", tags=["control"])
def fleet_status():
    nodes = db.fetchall("""
        SELECT n.node_id, nt.type_name, nt.label AS type_label,
               d.name AS domain, n.is_active, n.first_seen, n.last_seen
        FROM nodes n JOIN node_types nt ON n.node_type_id = nt.id
        JOIN domains d ON nt.domain_id = d.id ORDER BY n.last_seen DESC
    """)
    result = []
    for node in nodes:
        latest = db.fetchone(
            "SELECT data_json, is_critical, timestamp FROM telemetry_readings WHERE node_id_str = ? ORDER BY timestamp DESC LIMIT 1",
            (node["node_id"],)
        )
        health = {}
        if latest:
            data = json.loads(latest["data_json"])
            health = {
                "battery_level_pct": data.get("battery_level_pct"),
                "signal_strength_dbm": data.get("signal_strength_dbm"),
                "cpu_temp_c": data.get("cpu_temp_c"),
                "fault_code": data.get("fault_code", 0),
                "firmware_version": data.get("firmware_version"),
                "uptime_hours": data.get("uptime_hours"),
                "is_critical": bool(latest["is_critical"]),
                "last_reading_at": latest["timestamp"],
            }
        result.append({**dict(node), "health": health})
    return {
        "count": len(result),
        "active": sum(1 for n in result if n["is_active"]),
        "inactive": sum(1 for n in result if not n["is_active"]),
        "nodes": result,
    }


# ═══════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Data Ingestion Service v4 — Port {SERVER_PORT} — Worker {WORKER_ID}")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
