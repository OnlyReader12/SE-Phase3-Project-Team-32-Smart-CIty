"""
main.py — Access Management & Data Gateway: FastAPI Application.

Team Member 5 (Nikhil) — Data Privacy API & RBAC Security Core
Port: 8005

This service is the central gateway for:
  1. Ingesting telemetry from ALL IoT generators (EHS, Energy, CAM, etc.)
  2. Authenticating users and enforcing role-based access control
  3. Serving role-specific dashboards with scrubbed data views

API Surface:
  POST /api/v1/telemetry          → Ingest IoT data (any domain)
  POST /auth/login                → Login, returns JWT token
  POST /auth/register             → Create user (admin only)
  GET  /api/v1/me                 → Current user profile
  GET  /api/v1/dashboard-data     → Role-filtered dashboard JSON
  GET  /api/v1/telemetry/query    → Query telemetry (role-filtered)
  GET  /api/v1/telemetry/stats    → Domain statistics
  GET  /api/v1/users              → User listing (admin only)
  GET  /api/v1/alerts             → Query alerts (role-filtered)
  GET  /dashboard                 → HTML dashboard
  GET  /health                    → Health check
  GET  /                          → Service info

Design Patterns:
  - Repository (StorageBackend: file now, DB later)
  - Strategy   (per-role data scrubbing)
  - Factory    (role-specific dashboard construction)
"""

import os
import sys
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

# Resolve paths
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PORT = int(os.getenv("ACCESS_SERVICE_PORT", "8005"))

# Local imports
from models.schemas import (
    TelemetryPayload, LoginRequest, LoginResponse,
    RegisterRequest, UserProfile, DashboardData,
)
from storage.file_backend import FileStorageBackend
from auth.rbac import (
    hash_password, verify_password,
    create_token, decode_token,
    get_role_config, has_permission, get_allowed_domains,
    seed_default_users, ROLE_PERMISSIONS,
)
from auth.scrubber import (
    scrub_telemetry_for_role, scrub_user_for_role,
    build_role_dashboard_stats,
)


# ═══════════════════════════════════════════
# Initialize Storage (Repository Pattern)
# ═══════════════════════════════════════════
# To migrate to PostgreSQL, replace this single line:
#   storage = PostgresBackend(dsn="postgresql://user:pass@localhost/smartcity")

storage = FileStorageBackend(data_dir=os.path.join(_BASE_DIR, "data"))


# ═══════════════════════════════════════════
# FastAPI Application
# ═══════════════════════════════════════════

app = FastAPI(
    title="Smart City Access Management & Data Gateway",
    description="Unified IoT data ingestion + RBAC gatekeeper — Team 32",
    version="1.0.0",
)

# ── Seed default users on startup ──
@app.on_event("startup")
async def startup_event():
    count = seed_default_users(storage)
    if count > 0:
        print(f"[RBAC] Seeded {count} default users")
    else:
        print(f"[RBAC] Users already exist ({len(storage.list_users())} users)")


# ═══════════════════════════════════════════
# Auth Helpers
# ═══════════════════════════════════════════

def _extract_user(authorization: Optional[str] = None):
    """Extract and validate user from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    # Support "Bearer <token>" format
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    username = payload.get("sub")
    user = storage.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")

    return user


def _require_permission(user: dict, permission: str):
    """Check if user has a specific permission, raise 403 if not."""
    role = user.get("role", "resident")
    if not has_permission(role, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' does not have '{permission}' permission"
        )


# ═══════════════════════════════════════════
# Routes: Service Info & Health
# ═══════════════════════════════════════════

@app.get("/", tags=["info"])
def root():
    return {
        "service": "Smart City Access Management & Data Gateway",
        "version": "1.0.0",
        "port": SERVER_PORT,
        "team": "Team 32 — Member 5 (Nikhil)",
        "patterns": ["Repository", "Strategy", "Factory", "JWT Auth"],
        "endpoints": {
            "telemetry_ingest": "POST /api/v1/telemetry",
            "login": "POST /auth/login",
            "dashboard": "GET /dashboard",
            "docs": "GET /docs",
        },
    }


@app.get("/health", tags=["info"])
def health_check():
    domains = storage.get_domains()
    total = storage.count_telemetry()
    users = len(storage.list_users())
    return {
        "status": "healthy",
        "service": "AccessManagementService",
        "port": SERVER_PORT,
        "total_telemetry_records": total,
        "active_domains": domains,
        "registered_users": users,
        "storage_backend": "FileStorageBackend",
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════
# Routes: Authentication
# ═══════════════════════════════════════════

@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(req: LoginRequest):
    """Authenticate user and return JWT token."""
    user = storage.get_user(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")

    token = create_token(user["username"], user["role"])
    return LoginResponse(
        access_token=token,
        role=user["role"],
        username=user["username"],
    )


@app.post("/auth/register", tags=["auth"])
def register(req: RegisterRequest, authorization: Optional[str] = Header(None)):
    """Create a new user (admin only)."""
    admin = _extract_user(authorization)
    _require_permission(admin, "users.write")

    if storage.get_user(req.username):
        raise HTTPException(status_code=409, detail="Username already exists")

    user_record = {
        "username": req.username,
        "password_hash": hash_password(req.password),
        "role": req.role.value if hasattr(req.role, "value") else req.role,
        "full_name": req.full_name,
        "email": req.email,
        "created_at": datetime.now().isoformat(),
        "is_active": True,
    }
    storage.save_user(user_record)
    return {"status": "created", "username": req.username, "role": user_record["role"]}


@app.get("/api/v1/me", tags=["auth"])
def get_my_profile(authorization: Optional[str] = Header(None)):
    """Get current user's profile and permissions."""
    user = _extract_user(authorization)
    role = user.get("role", "resident")
    config = get_role_config(role)
    return {
        "username": user["username"],
        "role": role,
        "role_label": config.get("label", role),
        "icon": config.get("icon", "👤"),
        "permissions": config.get("permissions", []),
        "domains": config.get("domains", []),
        "can_see_pii": config.get("can_see_pii", False),
        "can_manage_users": config.get("can_manage_users", False),
        "full_name": user.get("full_name"),
        "email": user.get("email") if config.get("can_see_pii") else None,
    }


# ═══════════════════════════════════════════
# Routes: Telemetry Ingestion
# ═══════════════════════════════════════════

@app.post("/api/v1/telemetry", tags=["telemetry"])
def ingest_telemetry(payload: TelemetryPayload):
    """
    Universal telemetry ingestion endpoint.
    Accepts data from any IoT domain (energy, ehs, cam, etc.)
    and stores it via the configured storage backend.
    """
    record = {
        "node_id": payload.node_id,
        "domain": payload.domain,
        "node_type": payload.node_type,
        "timestamp": payload.timestamp,
        "data": payload.data,
    }

    record_id = storage.save_telemetry(payload.domain, record)

    # Auto-generate alerts for critical data
    if payload.data.get("is_critical"):
        storage.save_alert({
            "domain": payload.domain,
            "node_id": payload.node_id,
            "node_type": payload.node_type,
            "severity": "CRITICAL",
            "message": f"Critical reading from {payload.node_id} ({payload.node_type})",
            "data": payload.data,
        })

    return {
        "status": "ingested",
        "record_id": record_id,
        "domain": payload.domain,
        "node_id": payload.node_id,
    }


@app.get("/api/v1/telemetry/query", tags=["telemetry"])
def query_telemetry(
    authorization: Optional[str] = Header(None),
    domain: Optional[str] = Query(None),
    node_type: Optional[str] = Query(None),
    node_id: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
):
    """Query telemetry data with role-based filtering."""
    user = _extract_user(authorization)
    _require_permission(user, "telemetry.read")

    records = storage.query_telemetry(
        domain=domain, node_type=node_type, node_id=node_id,
        since=since, until=until, limit=limit,
    )

    # Apply role-based scrubbing
    role = user.get("role", "resident")
    scrubbed = scrub_telemetry_for_role(records, role)

    return {
        "count": len(scrubbed),
        "role": role,
        "filters_applied": {"domain": domain, "node_type": node_type, "node_id": node_id},
        "records": scrubbed,
    }


@app.get("/api/v1/telemetry/stats", tags=["telemetry"])
def telemetry_stats(authorization: Optional[str] = Header(None)):
    """Get telemetry domain statistics."""
    user = _extract_user(authorization)
    _require_permission(user, "telemetry.read")

    role = user.get("role", "resident")
    all_stats = storage.get_domain_stats()
    allowed = get_allowed_domains(role)

    # Filter to allowed domains
    if allowed:
        filtered = {k: v for k, v in all_stats.items() if k in allowed}
    else:
        filtered = {}

    return {
        "role": role,
        "domains": filtered,
        "total_domains": len(filtered),
    }


# ═══════════════════════════════════════════
# Routes: Alerts
# ═══════════════════════════════════════════

@app.get("/api/v1/alerts", tags=["alerts"])
def get_alerts(
    authorization: Optional[str] = Header(None),
    severity: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Query alerts with role-based filtering."""
    user = _extract_user(authorization)
    _require_permission(user, "alerts.read")

    alerts = storage.query_alerts(severity=severity, domain=domain, limit=limit)
    role = user.get("role", "resident")
    allowed = get_allowed_domains(role)

    # Filter by allowed domains
    if allowed:
        alerts = [a for a in alerts if a.get("domain", "") in allowed]

    return {"count": len(alerts), "role": role, "alerts": alerts}


# ═══════════════════════════════════════════
# Routes: User Management (Admin Only)
# ═══════════════════════════════════════════

@app.get("/api/v1/users", tags=["users"])
def list_users(authorization: Optional[str] = Header(None)):
    """List all users (admin/manager only)."""
    user = _extract_user(authorization)
    _require_permission(user, "users.read")

    all_users = storage.list_users()
    role = user.get("role", "resident")
    safe_users = [scrub_user_for_role(u, role) for u in all_users]
    return {"count": len(safe_users), "users": safe_users}


# ═══════════════════════════════════════════
# Routes: Dashboard Data (Role-Specific)
# ═══════════════════════════════════════════

@app.get("/api/v1/dashboard-data", tags=["dashboard"])
def dashboard_data(authorization: Optional[str] = Header(None)):
    """
    Build and return a role-specific dashboard payload.
    Uses Factory Pattern: the dashboard structure is constructed
    based on the authenticated user's role.
    """
    user = _extract_user(authorization)
    role = user.get("role", "resident")
    config = get_role_config(role)

    # Get stats
    domain_stats = storage.get_domain_stats()
    alerts = storage.query_alerts(limit=20)
    total_users = len(storage.list_users())

    # Build role-specific stats
    stats = build_role_dashboard_stats(role, domain_stats, alerts, total_users)

    # Get recent telemetry (scrubbed for role)
    recent = storage.query_telemetry(limit=50)
    scrubbed_recent = scrub_telemetry_for_role(recent, role)

    # Get role-visible alerts
    allowed = config.get("domains", [])
    visible_alerts = [a for a in alerts if not allowed or a.get("domain", "") in allowed]

    return {
        "role": role,
        "username": user["username"],
        "role_label": config.get("label", role),
        "icon": config.get("icon", "👤"),
        "permissions": config.get("permissions", []),
        "domains_visible": allowed,
        "stats": stats,
        "recent_telemetry": scrubbed_recent[:30],
        "alerts": visible_alerts[:15],
        "generated_at": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════
# Routes: Role Definitions
# ═══════════════════════════════════════════

@app.get("/api/v1/roles", tags=["info"])
def list_roles():
    """List all available roles and their permissions."""
    roles = []
    for role_key, config in ROLE_PERMISSIONS.items():
        role_val = role_key.value if hasattr(role_key, "value") else role_key
        roles.append({
            "role": role_val,
            "label": config["label"],
            "icon": config["icon"],
            "domains": config["domains"],
            "permissions": config["permissions"],
            "can_see_pii": config["can_see_pii"],
        })
    return {"count": len(roles), "roles": roles}


# ═══════════════════════════════════════════
# Routes: HTML Dashboard
# ═══════════════════════════════════════════

@app.get("/dashboard", response_class=HTMLResponse, tags=["dashboard"])
def serve_dashboard():
    """Serve the interactive HTML dashboard with login."""
    html_path = os.path.join(_BASE_DIR, "static", "dashboard.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


# ═══════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print(f"\n{'=' * 60}")
    print(f"  Access Management & Data Gateway — Port {SERVER_PORT}")
    print(f"  Smart City Living Lab — Team 32")
    print(f"{'=' * 60}\n")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
