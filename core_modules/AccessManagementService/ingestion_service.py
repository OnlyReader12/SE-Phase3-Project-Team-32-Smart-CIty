"""
ingestion_service.py — Microservice 1: Data Ingestion (Store) v3

Port: 8006

Receives telemetry from ALL IoT generators and stores in normalized SQLite.
Auto-registers unknown nodes on first contact.

v3: Engine health, system metrics (CPU/memory/workers), dynamic node add/remove,
    data rate control, HLD architecture stats.
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

SERVER_PORT = int(os.getenv("INGESTION_SERVICE_PORT", "8006"))
WORKER_ID = os.getenv("WORKER_ID", "w0")

db = DatabaseManager(os.path.join(_BASE_DIR, "smartcity.db"))

app = FastAPI(
    title="Smart City Data Ingestion Service",
    description="Microservice 1: Stores IoT telemetry + Engine Health + System Metrics",
    version="3.0.0",
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
# Control State
# ═══════════════════════════════════════════
CONTROL = {
    "interval": 1.5,
}
PENDING_NODES = []
REMOVED_NODES = set()


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
    print(f"[ENGINE] Worker {WORKER_ID} started on port {SERVER_PORT}")


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

class RemoveNodePayload(BaseModel):
    node_id: str

class IntervalPayload(BaseModel):
    interval: float = Field(ge=0.3, le=10.0)

class AddBulkNodesPayload(BaseModel):
    count: int = Field(ge=1, le=50)
    domain: str = "energy"
    node_type: str = "solar_panel"
    prefix: str = "DYN"


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
# Routes: Info & Health
# ═══════════════════════════════════════════

@app.get("/", tags=["info"])
def root():
    return {
        "service": "Smart City Data Ingestion Service", "version": "3.0.0",
        "port": SERVER_PORT, "worker": WORKER_ID,
    }

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
        except:
            ENGINE["ingest_errors"] += 1
    return {"status": "batch_stored", "stored": stored, "critical": critical}


# ═══════════════════════════════════════════
# Routes: Engine Health & System Metrics
# ═══════════════════════════════════════════

def _get_system_metrics():
    """Collect real CPU/memory/system metrics."""
    cpu_count = os.cpu_count() or 1
    load_avg = list(os.getloadavg())  # 1min, 5min, 15min
    cpu_usage_pct = round(load_avg[0] / cpu_count * 100, 1)

    # Process memory
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        mem_mb = round(ru.ru_maxrss / (1024 * 1024), 1)  # macOS reports bytes
    except:
        mem_mb = 0

    # DB file size
    db_path = os.path.join(_BASE_DIR, "smartcity.db")
    db_size_mb = round(os.path.getsize(db_path) / (1024*1024), 2) if os.path.exists(db_path) else 0

    # Thread count
    thread_count = threading.active_count()

    # PID
    pid = os.getpid()

    return {
        "cpu_count": cpu_count,
        "cpu_usage_pct": min(100, cpu_usage_pct),
        "load_avg_1m": round(load_avg[0], 2),
        "load_avg_5m": round(load_avg[1], 2),
        "load_avg_15m": round(load_avg[2], 2),
        "memory_mb": mem_mb,
        "thread_count": thread_count,
        "db_size_mb": db_size_mb,
        "pid": pid,
    }


@app.get("/engine-health", tags=["engine"])
def engine_health():
    uptime = time.time() - (ENGINE["start_time"] or time.time())
    rps = ENGINE["ingest_count"] / max(1, uptime)
    lats = list(ENGINE["last_100_latencies_ms"])
    avg_lat = sum(lats) / len(lats) if lats else 0
    max_lat = max(lats) if lats else 0
    sys_metrics = _get_system_metrics()
    nodes = db.fetchone("SELECT COUNT(*) as c FROM nodes WHERE is_active = 1")

    return {
        "worker_id": WORKER_ID,
        "uptime_seconds": round(uptime, 1),
        "total_ingested": ENGINE["ingest_count"],
        "total_errors": ENGINE["ingest_errors"],
        "records_per_second": round(rps, 2),
        "avg_latency_ms": round(avg_lat, 2),
        "max_latency_ms": round(max_lat, 2),
        "active_nodes": nodes["c"],
        "system": sys_metrics,
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
    PENDING_NODES.append({
        "node_id": payload.node_id, "domain": payload.domain,
        "node_type": payload.node_type, "added_at": datetime.now().isoformat(),
    })
    return {"status": "added", "node_id": payload.node_id, "note": "Node will start streaming shortly"}

@app.post("/control/add-bulk-nodes", tags=["control"])
def add_bulk_nodes(payload: AddBulkNodesPayload):
    """Add multiple nodes at once for load testing."""
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
    print(f"  Data Ingestion Service v3 — Port {SERVER_PORT} — Worker {WORKER_ID}")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
