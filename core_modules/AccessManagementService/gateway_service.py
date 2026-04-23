"""
gateway_service.py — Microservice 2: Access Management Gateway (Retrieve) v2

Port: 8005

Authenticates users, enforces RBAC, and serves role-filtered data views.
Reads from the same SQLite database that the Ingestion Service writes to.

New in v2:
  GET  /api/v1/my-data             → Resident personal node data
  GET  /api/v1/analytics           → Analyst: aggregated stats, trend data
  Operator role: critical-only + health/fault view
  Resident role: sees only their personal nodes
"""

import json
import os
import sys

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE_DIR)

from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from database.connection import DatabaseManager
from database.seed import seed_database
from auth.rbac import (
    hash_password, verify_password, create_token, decode_token,
    get_role_info, has_permission, get_allowed_domains, get_user_with_role,
)

SERVER_PORT = int(os.getenv("GATEWAY_SERVICE_PORT", "8005"))
db = DatabaseManager(os.path.join(_BASE_DIR, "smartcity.db"))

app = FastAPI(
    title="Smart City Access Management Gateway",
    description="Microservice 2: Auth + RBAC + Role-filtered data views",
    version="2.0.0",
)


@app.on_event("startup")
async def startup():
    db.initialize()
    counts = seed_database(db)
    if counts["users"] > 0:
        print(f"[SEED] Created: {counts}")
    users = db.fetchone("SELECT COUNT(*) as c FROM users")
    print(f"[DB] {users['c']} users registered")


# ═══════════════════════════════════════════
# Auth Helpers
# ═══════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str
    full_name: str = None
    email: str = None


def _extract_user(authorization: Optional[str] = None):
    if not authorization:
        raise HTTPException(401, "Authorization header missing")
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    user = get_user_with_role(db, payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    if not user["is_active"]:
        raise HTTPException(403, "Account deactivated")
    return user


def _require(user, permission):
    if not has_permission(db, user["role_name"], permission):
        raise HTTPException(403, f"Role '{user['role_name']}' lacks '{permission}'")


def _get_user_nodes(user_id: int):
    """Get list of node_id strings mapped to a user."""
    rows = db.fetchall("SELECT node_id_str FROM user_nodes WHERE user_id = ?", (user_id,))
    return [r["node_id_str"] for r in rows]


# ═══════════════════════════════════════════
# Routes: Info & Health
# ═══════════════════════════════════════════

@app.get("/", tags=["info"])
def root():
    return {
        "service": "Smart City Access Management Gateway",
        "version": "2.0.0", "port": SERVER_PORT,
        "note": "v2 — Resident personal data, Analyst analytics, Operator critical-only",
    }


@app.get("/health", tags=["info"])
def health():
    readings = db.fetchone("SELECT COUNT(*) as c FROM telemetry_readings")
    nodes = db.fetchone("SELECT COUNT(*) as c FROM nodes")
    users = db.fetchone("SELECT COUNT(*) as c FROM users")
    domains = db.fetchall("SELECT name FROM domains")
    return {
        "status": "healthy", "service": "AccessManagementGateway", "port": SERVER_PORT,
        "database": "SQLite (WAL mode)",
        "total_readings": readings["c"], "registered_nodes": nodes["c"],
        "registered_users": users["c"],
        "active_domains": [d["name"] for d in domains],
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════
# Routes: Authentication
# ═══════════════════════════════════════════

@app.post("/auth/login", tags=["auth"])
def login(req: LoginRequest):
    user = get_user_with_role(db, req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    if not user["is_active"]:
        raise HTTPException(403, "Account deactivated")
    token = create_token(user["username"], user["role_name"])
    return {
        "access_token": token, "token_type": "bearer",
        "username": user["username"], "role": user["role_name"],
        "role_label": user["role_label"], "icon": user["role_icon"],
        "full_name": user["full_name"],
    }


@app.post("/auth/register", tags=["auth"])
def register(req: RegisterRequest, authorization: Optional[str] = Header(None)):
    admin = _extract_user(authorization)
    _require(admin, "users.write")
    existing = db.fetchone("SELECT id FROM users WHERE username = ?", (req.username,))
    if existing:
        raise HTTPException(409, "Username already exists")
    role = db.fetchone("SELECT id FROM roles WHERE role_name = ?", (req.role,))
    if not role:
        raise HTTPException(400, f"Unknown role: {req.role}")
    db.execute(
        "INSERT INTO users (username, password_hash, role_id, full_name, email, is_active, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (req.username, hash_password(req.password), role["id"],
         req.full_name, req.email, datetime.now().isoformat())
    )
    return {"status": "created", "username": req.username, "role": req.role}


@app.get("/api/v1/me", tags=["auth"])
def my_profile(authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    role_info = get_role_info(db, user["role_name"])
    my_nodes = _get_user_nodes(user["id"]) if user["role_name"] == "resident" else []
    return {
        "username": user["username"],
        "role": user["role_name"],
        "role_label": user["role_label"],
        "icon": user["role_icon"],
        "full_name": user["full_name"],
        "email": user["email"] if user["can_see_pii"] else None,
        "permissions": role_info["permissions"] if role_info else [],
        "domains": role_info["domains"] if role_info else [],
        "can_see_pii": bool(user["can_see_pii"]),
        "can_manage_users": bool(user["can_manage_users"]),
        "my_nodes": my_nodes,
    }


# ═══════════════════════════════════════════
# Routes: Telemetry Queries (role-filtered)
# ═══════════════════════════════════════════

@app.get("/api/v1/telemetry/query", tags=["telemetry"])
def query_telemetry(
    authorization: Optional[str] = Header(None),
    domain: Optional[str] = Query(None),
    node_type: Optional[str] = Query(None),
    node_id: Optional[str] = Query(None),
    critical_only: bool = Query(False),
    limit: int = Query(100, le=1000),
):
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    role = user["role_name"]
    allowed = get_allowed_domains(db, role)

    conditions = []
    params = []

    # Resident: restrict to their own nodes
    if role == "resident":
        my_nodes = _get_user_nodes(user["id"])
        if my_nodes:
            ph = ",".join("?" * len(my_nodes))
            conditions.append(f"node_id_str IN ({ph})")
            params.extend(my_nodes)
        else:
            return {"count": 0, "role": role, "records": []}
    else:
        # Domain filtering
        if domain:
            if allowed and domain not in allowed:
                raise HTTPException(403, f"No access to domain '{domain}'")
            conditions.append("domain_name = ?")
            params.append(domain)
        elif allowed:
            ph = ",".join("?" * len(allowed))
            conditions.append(f"domain_name IN ({ph})")
            params.extend(allowed)

    if node_type:
        conditions.append("node_type_name = ?")
        params.append(node_type)
    if node_id:
        conditions.append("node_id_str = ?")
        params.append(node_id)

    # Operator + Emergency responder: critical only
    if role in ("emergency_responder", "operator") or critical_only:
        conditions.append("is_critical = 1")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = db.fetchall(
        f"SELECT * FROM telemetry_readings {where} ORDER BY timestamp DESC LIMIT ?",
        tuple(params)
    )

    results = []
    for r in rows:
        rec = dict(r)
        rec["data"] = json.loads(rec.pop("data_json", "{}"))
        # Maintenance: show only health fields
        if role == "maintenance":
            health_keys = {"battery_soc_pct", "voltage", "current", "fault_status",
                           "grid_temperature_c", "grid_load_pct", "ac_power_w", "ac_mode",
                           "leak_detected", "is_critical", "solar_status", "battery_status",
                           "flow_rate_lpm", "solar_power_w"}
            rec["data"] = {k: v for k, v in rec["data"].items() if k in health_keys or k.startswith("is_")}
        results.append(rec)

    return {"count": len(results), "role": role, "records": results}


@app.get("/api/v1/telemetry/stats", tags=["telemetry"])
def telemetry_stats(authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    allowed = get_allowed_domains(db, user["role_name"])
    stats = db.fetchall("SELECT * FROM v_domain_stats")
    if allowed:
        stats = [s for s in stats if s["domain"] in allowed]
    return {"role": user["role_name"], "domains": stats}


# ═══════════════════════════════════════════
# Routes: Resident Personal Data
# ═══════════════════════════════════════════

@app.get("/api/v1/my-data", tags=["resident"])
def my_data(authorization: Optional[str] = Header(None)):
    """Get personal node data for a resident — energy consumption, generation, air quality."""
    user = _extract_user(authorization)
    my_nodes = _get_user_nodes(user["id"])
    if not my_nodes:
        return {"nodes": [], "summary": {}, "message": "No nodes mapped to your account"}

    # Get latest reading for each of the user's nodes
    node_data = []
    total_consumption = 0
    total_generation = 0
    aqi_values = []

    for nid in my_nodes:
        latest = db.fetchone(
            "SELECT * FROM telemetry_readings WHERE node_id_str = ? ORDER BY timestamp DESC LIMIT 1",
            (nid,)
        )
        if latest:
            data = json.loads(latest["data_json"])
            entry = {
                "node_id": nid,
                "domain": latest["domain_name"],
                "node_type": latest["node_type_name"],
                "timestamp": latest["timestamp"],
                "is_critical": bool(latest["is_critical"]),
                "data": data,
            }
            node_data.append(entry)

            # Aggregate
            if "solar_power_w" in data:
                total_generation += data["solar_power_w"]
            if "power_w" in data:
                total_consumption += data["power_w"]
            if "ac_power_w" in data:
                total_consumption += data["ac_power_w"]
            if "aqi" in data:
                aqi_values.append(data["aqi"])

        # Get recent 30 readings for trend
        recent = db.fetchall(
            "SELECT timestamp, data_json FROM telemetry_readings WHERE node_id_str = ? ORDER BY timestamp DESC LIMIT 30",
            (nid,)
        )
        if recent:
            trend = []
            for r in recent:
                d = json.loads(r["data_json"])
                trend.append({"timestamp": r["timestamp"], **d})
            entry["trend"] = trend

    avg_aqi = sum(aqi_values) / len(aqi_values) if aqi_values else None

    return {
        "username": user["username"],
        "full_name": user["full_name"],
        "nodes": node_data,
        "summary": {
            "total_consumption_w": round(total_consumption, 1),
            "total_generation_w": round(total_generation, 1),
            "net_energy_w": round(total_generation - total_consumption, 1),
            "aqi": round(avg_aqi) if avg_aqi else None,
            "node_count": len(my_nodes),
        },
    }


# ═══════════════════════════════════════════
# Routes: Analyst Analytics
# ═══════════════════════════════════════════

@app.get("/api/v1/analytics", tags=["analytics"])
def analytics(authorization: Optional[str] = Header(None)):
    """Aggregated analytics for analysts — per-domain breakdown, node-type stats, critical trends."""
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    allowed = get_allowed_domains(db, user["role_name"])

    # Per-domain stats
    domain_stats = db.fetchall("SELECT * FROM v_domain_stats")
    if allowed:
        domain_stats = [s for s in domain_stats if s["domain"] in allowed]

    # Per-node-type aggregation
    cond = ""
    params = []
    if allowed:
        ph = ",".join("?" * len(allowed))
        cond = f"WHERE domain_name IN ({ph})"
        params = list(allowed)

    node_type_stats = db.fetchall(
        f"""SELECT node_type_name, domain_name, 
                   COUNT(*) as readings, 
                   SUM(is_critical) as critical,
                   MAX(timestamp) as latest
            FROM telemetry_readings {cond}
            GROUP BY node_type_name, domain_name
            ORDER BY readings DESC""",
        tuple(params)
    )

    # Critical rate over recent readings
    recent_crit = db.fetchall(
        f"""SELECT
                substr(timestamp, 1, 16) as minute,
                COUNT(*) as total,
                SUM(is_critical) as critical
            FROM telemetry_readings {cond}
            GROUP BY minute
            ORDER BY minute DESC
            LIMIT 30""",
        tuple(params)
    )

    # Top critical nodes
    top_critical = db.fetchall(
        f"""SELECT node_id_str, node_type_name, domain_name,
                   COUNT(*) as critical_count
            FROM telemetry_readings
            WHERE is_critical = 1 {('AND domain_name IN (' + ph + ')') if allowed else ''}
            GROUP BY node_id_str
            ORDER BY critical_count DESC
            LIMIT 10""",
        tuple(params) if allowed else ()
    )

    return {
        "role": user["role_name"],
        "domain_stats": domain_stats,
        "node_type_stats": node_type_stats,
        "critical_trend": recent_crit,
        "top_critical_nodes": top_critical,
    }


# ═══════════════════════════════════════════
# Routes: Operator — Node Health & Faults
# ═══════════════════════════════════════════

@app.get("/api/v1/node-health", tags=["operator"])
def node_health(authorization: Optional[str] = Header(None)):
    """Operator/Maintenance view: last reading + health for each node."""
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    allowed = get_allowed_domains(db, user["role_name"])

    cond = ""
    params = []
    if allowed:
        ph = ",".join("?" * len(allowed))
        cond = f"WHERE d.name IN ({ph})"
        params = list(allowed)

    nodes = db.fetchall(
        f"""SELECT n.node_id, nt.type_name, nt.label AS type_label,
                   d.name AS domain, n.is_active, n.last_seen
            FROM nodes n
            JOIN node_types nt ON n.node_type_id = nt.id
            JOIN domains d ON nt.domain_id = d.id {cond}
            ORDER BY n.last_seen DESC""",
        tuple(params)
    )

    # Enrich with latest reading
    result = []
    for node in nodes:
        latest = db.fetchone(
            "SELECT data_json, is_critical, timestamp FROM telemetry_readings WHERE node_id_str = ? ORDER BY timestamp DESC LIMIT 1",
            (node["node_id"],)
        )
        status = "UNKNOWN"
        data = {}
        if latest:
            data = json.loads(latest["data_json"])
            if latest["is_critical"]:
                status = "CRITICAL"
            elif data.get("leak_detected") or data.get("fault_status"):
                status = "FAULT"
            else:
                status = "HEALTHY"

        # Count critical readings in last 50
        crit_count = db.fetchone(
            "SELECT COUNT(*) as c FROM (SELECT is_critical FROM telemetry_readings WHERE node_id_str = ? ORDER BY timestamp DESC LIMIT 50) WHERE is_critical = 1",
            (node["node_id"],)
        )

        result.append({
            **dict(node),
            "status": status,
            "is_critical": latest["is_critical"] if latest else 0,
            "last_reading_at": latest["timestamp"] if latest else None,
            "critical_in_last_50": crit_count["c"] if crit_count else 0,
            "key_data": {k: v for k, v in data.items() if k != "is_critical"},
        })

    # Sort: CRITICAL first, then FAULT, then HEALTHY
    order = {"CRITICAL": 0, "FAULT": 1, "HEALTHY": 2, "UNKNOWN": 3}
    result.sort(key=lambda x: order.get(x["status"], 9))

    return {"count": len(result), "nodes": result}


# ═══════════════════════════════════════════
# Routes: Nodes, Users, Roles, Alerts
# ═══════════════════════════════════════════

@app.get("/api/v1/nodes", tags=["nodes"])
def list_nodes(authorization: Optional[str] = Header(None), domain: Optional[str] = Query(None)):
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    allowed = get_allowed_domains(db, user["role_name"])
    sql = """SELECT n.node_id, nt.type_name, nt.label AS type_label,
                    d.name AS domain, d.label AS domain_label,
                    n.is_active, n.first_seen, n.last_seen
             FROM nodes n JOIN node_types nt ON n.node_type_id = nt.id JOIN domains d ON nt.domain_id = d.id"""
    conditions, params = [], []
    if domain:
        conditions.append("d.name = ?"); params.append(domain)
    elif allowed:
        conditions.append(f"d.name IN ({','.join('?' * len(allowed))})")
        params.extend(allowed)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY d.name, nt.type_name, n.node_id"
    nodes = db.fetchall(sql, tuple(params))
    return {"count": len(nodes), "nodes": nodes}


@app.get("/api/v1/users", tags=["users"])
def list_users(authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "users.read")
    users = db.fetchall("SELECT * FROM v_user_profiles")
    if not user["can_see_pii"]:
        for u in users: u.pop("email", None)
    return {"count": len(users), "users": users}


@app.get("/api/v1/roles", tags=["info"])
def list_roles():
    roles = db.fetchall("SELECT * FROM roles")
    result = []
    for r in roles:
        perms = db.fetchall("SELECT permission FROM role_permissions WHERE role_id = ?", (r["id"],))
        domains = db.fetchall("SELECT domain_name FROM role_domain_access WHERE role_id = ?", (r["id"],))
        result.append({
            "role": r["role_name"], "label": r["label"], "icon": r["icon"],
            "can_see_pii": bool(r["can_see_pii"]),
            "can_manage_users": bool(r["can_manage_users"]),
            "permissions": [p["permission"] for p in perms],
            "domains": [d["domain_name"] for d in domains],
        })
    return {"count": len(result), "roles": result}


@app.get("/api/v1/alerts", tags=["alerts"])
def get_alerts(authorization: Optional[str] = Header(None), severity: Optional[str] = Query(None), limit: int = Query(50)):
    user = _extract_user(authorization)
    _require(user, "alerts.read")
    conditions, params = [], []
    allowed = get_allowed_domains(db, user["role_name"])
    if allowed:
        conditions.append(f"domain_name IN ({','.join('?' * len(allowed))})")
        params.extend(allowed)
    if severity:
        conditions.append("severity = ?"); params.append(severity)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    alerts = db.fetchall(f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ?", tuple(params))
    return {"count": len(alerts), "alerts": alerts, "note": "Alerts integration pending — Member 4"}


# ═══════════════════════════════════════════
# Routes: Dashboard Data (v2 — role-specific)
# ═══════════════════════════════════════════

@app.get("/api/v1/dashboard-data", tags=["dashboard"])
def dashboard_data(authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    role = user["role_name"]
    role_info = get_role_info(db, role)
    allowed = role_info["domains"] if role_info else []

    # Domain stats
    domain_stats = db.fetchall("SELECT * FROM v_domain_stats")
    if allowed:
        domain_stats = [s for s in domain_stats if s["domain"] in allowed]

    total_readings = sum(s["total_readings"] or 0 for s in domain_stats)
    total_nodes = sum(s["unique_nodes"] or 0 for s in domain_stats)
    total_critical = sum(s["critical_readings"] or 0 for s in domain_stats)

    # Recent telemetry (role-filtered)
    conditions, params = [], []
    if role == "resident":
        my_nodes = _get_user_nodes(user["id"])
        if my_nodes:
            ph = ",".join("?" * len(my_nodes))
            conditions.append(f"node_id_str IN ({ph})")
            params.extend(my_nodes)
        else:
            conditions.append("1=0")  # no results
    elif allowed:
        ph = ",".join("?" * len(allowed))
        conditions.append(f"domain_name IN ({ph})")
        params.extend(allowed)
    if role in ("emergency_responder", "operator"):
        conditions.append("is_critical = 1")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    recent = db.fetchall(
        f"SELECT * FROM telemetry_readings {where} ORDER BY timestamp DESC LIMIT 30",
        tuple(params)
    )
    for r in recent:
        r["data"] = json.loads(r.pop("data_json", "{}"))

    # User count
    total_users = None
    if user["can_manage_users"]:
        total_users = db.fetchone("SELECT COUNT(*) as c FROM users")["c"]

    # Resident personal summary
    personal = None
    if role == "resident":
        my_nodes = _get_user_nodes(user["id"])
        consumption = 0
        generation = 0
        aqi = None
        for nid in my_nodes:
            latest = db.fetchone(
                "SELECT data_json FROM telemetry_readings WHERE node_id_str = ? ORDER BY timestamp DESC LIMIT 1",
                (nid,)
            )
            if latest:
                d = json.loads(latest["data_json"])
                consumption += d.get("power_w", 0) + d.get("ac_power_w", 0)
                generation += d.get("solar_power_w", 0)
                if "aqi" in d:
                    aqi = d["aqi"]
        personal = {
            "consumption_w": round(consumption, 1),
            "generation_w": round(generation, 1),
            "net_w": round(generation - consumption, 1),
            "aqi": aqi,
            "node_count": len(my_nodes),
            "my_nodes": my_nodes,
        }

    return {
        "role": role,
        "username": user["username"],
        "full_name": user["full_name"],
        "role_label": user["role_label"],
        "icon": user["role_icon"],
        "permissions": role_info["permissions"] if role_info else [],
        "domains_visible": allowed,
        "stats": {
            "total_readings": total_readings,
            "total_nodes": total_nodes,
            "total_critical": total_critical,
            "total_domains": len(domain_stats),
            "domain_breakdown": domain_stats,
            "total_users": total_users,
        },
        "recent_telemetry": recent,
        "personal": personal,
        "alerts": [],
        "alerts_note": "Alerts integration pending",
        "generated_at": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════
# HTML Pages
# ═══════════════════════════════════════════

@app.get("/dashboard", response_class=HTMLResponse, tags=["dashboard"])
def serve_dashboard():
    html_path = os.path.join(_BASE_DIR, "static", "dashboard.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

@app.get("/control-panel", response_class=HTMLResponse, tags=["control"])
def serve_control_panel():
    html_path = os.path.join(_BASE_DIR, "static", "control_panel.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Control Panel not found</h1>", status_code=404)

@app.get("/hld-architecture", response_class=HTMLResponse, tags=["hld"])
def serve_hld():
    html_path = os.path.join(_BASE_DIR, "static", "hld_architecture.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>HLD Architecture view not found</h1>", status_code=404)


# ═══════════════════════════════════════════
# Engine Health & Report Proxies
# ═══════════════════════════════════════════

INGESTION_URL = os.getenv("INGESTION_URL", "http://127.0.0.1:8006")

def _proxy_ingestion(path, method="GET", json_data=None):
    import requests as req
    try:
        if method == "GET":
            r = req.get(f"{INGESTION_URL}{path}", timeout=5)
        else:
            r = req.post(f"{INGESTION_URL}{path}", json=json_data, timeout=5)
        return r.json()
    except Exception as e:
        raise HTTPException(502, f"Ingestion service unreachable: {e}")


@app.get("/api/v1/engine-health", tags=["engine"])
def engine_health(authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    return _proxy_ingestion("/engine-health")

@app.get("/api/v1/engine-report", tags=["engine"])
def engine_report(authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    return _proxy_ingestion("/engine-report")

@app.get("/api/v1/fleet-status", tags=["control"])
def fleet_status(authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "telemetry.read")
    return _proxy_ingestion("/control/fleet-status")


# ═══════════════════════════════════════════
# Control Panel API Proxies
# ═══════════════════════════════════════════

from pydantic import BaseModel as BM

class AddNodeReq(BM):
    node_id: str
    domain: str
    node_type: str
    location: str = "Dynamic"

class AddBulkReq(BM):
    count: int
    domain: str = "energy"
    node_type: str = "solar_panel"
    prefix: str = "DYN"

class RemoveNodeReq(BM):
    node_id: str

class IntervalReq(BM):
    interval: float


@app.post("/api/v1/control/set-interval", tags=["control"])
def ctrl_set_interval(req: IntervalReq, authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "config.manage")
    return _proxy_ingestion("/control/set-interval", "POST", {"interval": req.interval})

@app.post("/api/v1/control/add-node", tags=["control"])
def ctrl_add_node(req: AddNodeReq, authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "config.manage")
    return _proxy_ingestion("/control/add-node", "POST", req.dict())

@app.post("/api/v1/control/add-bulk-nodes", tags=["control"])
def ctrl_add_bulk(req: AddBulkReq, authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "config.manage")
    return _proxy_ingestion("/control/add-bulk-nodes", "POST", req.dict())

@app.post("/api/v1/control/remove-node", tags=["control"])
def ctrl_remove_node(req: RemoveNodeReq, authorization: Optional[str] = Header(None)):
    user = _extract_user(authorization)
    _require(user, "config.manage")
    return _proxy_ingestion("/control/remove-node", "POST", {"node_id": req.node_id})


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Access Management Gateway v3 — Port {SERVER_PORT}")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
