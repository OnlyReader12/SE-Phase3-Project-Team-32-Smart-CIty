"""
Persistent Middleware — API routes.

Provides read access to the SQLite telemetry store for Domain Engines,
dashboards, and debugging tools.

Routes
------
GET /health                     Health check
GET /history/{node_id}          Last N records for a specific node
GET /nodes                      List of all distinct nodes ever seen
GET /domain/{domain}            Latest record per node in a domain
GET /view                       HTML live dashboard (human-readable)
"""
import json
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.db_core import get_db
from database.models import TelemetryRecord

router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────

@router.get("/health", summary="Middleware health check")
def health(db: Session = Depends(get_db)):
    count = db.query(func.count(TelemetryRecord.id)).scalar()
    return {"status": "ok", "total_records": count}


# ── Node history ──────────────────────────────────────────────────────────

@router.get("/history/{node_id}", summary="Get telemetry history for a node")
def get_node_history(
    node_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Returns the most recent `limit` telemetry records for the given node_id.
    Used by Domain Engines to reconstruct node state history.
    """
    records = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.node_id == node_id)
        .order_by(TelemetryRecord.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "node_id": node_id,
        "count": len(records),
        "history": [
            {
                "id":              r.id,
                "node_type":       r.node_type,
                "domain":          r.domain,
                "timestamp":       r.timestamp,
                "state":           r.state,
                "health_status":   r.health_status,
                "protocol_source": r.protocol_source,
                "location":        r.location_dict(),
                "payload":         r.payload_dict(),
            }
            for r in records
        ],
    }


# ── Node registry ─────────────────────────────────────────────────────────

@router.get("/nodes", summary="List all distinct nodes seen by the Middleware")
def list_nodes(db: Session = Depends(get_db)):
    """
    Returns one entry per distinct node_id with its latest metadata.
    Useful for Domain Engines to discover what nodes are active.
    """
    rows = (
        db.query(
            TelemetryRecord.node_id,
            TelemetryRecord.node_type,
            TelemetryRecord.domain,
            TelemetryRecord.protocol_source,
            func.max(TelemetryRecord.timestamp).label("last_seen"),
            func.count(TelemetryRecord.id).label("total_records"),
        )
        .group_by(TelemetryRecord.node_id)
        .all()
    )
    return {
        "total_nodes": len(rows),
        "nodes": [
            {
                "node_id":         r.node_id,
                "node_type":       r.node_type,
                "domain":          r.domain,
                "protocol_source": r.protocol_source,
                "last_seen":       r.last_seen,
                "total_records":   r.total_records,
            }
            for r in rows
        ],
    }


# ── Domain view ───────────────────────────────────────────────────────────

@router.get("/domain/{domain}", summary="Latest record per node in a domain")
def get_domain_latest(domain: str, db: Session = Depends(get_db)):
    """
    Returns the most recent telemetry record for each node in the given
    domain (energy | water | air).
    """
    subq = (
        db.query(
            TelemetryRecord.node_id,
            func.max(TelemetryRecord.id).label("max_id"),
        )
        .filter(TelemetryRecord.domain == domain)
        .group_by(TelemetryRecord.node_id)
        .subquery()
    )
    records = (
        db.query(TelemetryRecord)
        .join(subq, TelemetryRecord.id == subq.c.max_id)
        .all()
    )
    return {
        "domain": domain,
        "node_count": len(records),
        "latest": [
            {
                "node_id":         r.node_id,
                "node_type":       r.node_type,
                "timestamp":       r.timestamp,
                "state":           r.state,
                "health_status":   r.health_status,
                "protocol_source": r.protocol_source,
                "payload":         r.payload_dict(),
            }
            for r in records
        ],
    }


# ── HTML Dashboard ────────────────────────────────────────────────────────

@router.get("/view", response_class=HTMLResponse, summary="HTML live dashboard")
def view_live_dashboard(db: Session = Depends(get_db)):
    """
    Generates a human-readable HTML page showing all nodes that have
    checked in, grouped by domain with protocol badges.
    """
    rows = (
        db.query(
            TelemetryRecord.node_id,
            TelemetryRecord.node_type,
            TelemetryRecord.domain,
            TelemetryRecord.protocol_source,
            TelemetryRecord.state,
            TelemetryRecord.health_status,
            func.max(TelemetryRecord.timestamp).label("last_seen"),
            func.count(TelemetryRecord.id).label("records"),
        )
        .group_by(TelemetryRecord.node_id)
        .order_by(TelemetryRecord.domain, TelemetryRecord.node_id)
        .all()
    )

    total = db.query(func.count(TelemetryRecord.id)).scalar()

    protocol_colors = {
        "HTTP_POST":  "#3b82f6",
        "MQTT_PUB":   "#8b5cf6",
        "CoAP_PUT":   "#f59e0b",
        "WebSocket":  "#10b981",
    }
    domain_icons = {"energy": "⚡", "water": "💧", "air": "🌬️"}

    rows_html = ""
    for r in rows:
        badge_color = protocol_colors.get(r.protocol_source, "#6b7280")
        icon = domain_icons.get(r.domain, "📡")
        health_color = "#10b981" if r.health_status == "OK" else "#ef4444"
        rows_html += f"""
        <tr>
          <td>{icon} <strong>{r.node_id}</strong></td>
          <td><code>{r.node_type}</code></td>
          <td>{r.domain}</td>
          <td><span style="background:{badge_color};color:#fff;padding:2px 8px;border-radius:12px;font-size:11px">{r.protocol_source}</span></td>
          <td>{r.state or "—"}</td>
          <td style="color:{health_color}">{r.health_status or "—"}</td>
          <td>{r.records}</td>
          <td style="font-size:11px;color:#6b7280">{r.last_seen}</td>
          <td><a href="/history/{r.node_id}" style="color:#3b82f6">History</a></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Smart City — Persistent Middleware Dashboard</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; }}
    h1   {{ font-size: 1.5rem; margin-bottom: 4px; color: #f8fafc; }}
    p.sub{{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 20px; }}
    .stat-row {{ display: flex; gap: 16px; margin-bottom: 24px; }}
    .stat {{ background: #1e293b; border-radius: 8px; padding: 14px 20px; flex: 1; }}
    .stat .val {{ font-size: 2rem; font-weight: 700; color: #38bdf8; }}
    .stat .lbl {{ font-size: 0.8rem; color: #94a3b8; }}
    table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; }}
    th    {{ background: #0ea5e9; color: #fff; padding: 10px 14px; text-align: left; font-size: 0.8rem; }}
    td    {{ padding: 9px 14px; border-bottom: 1px solid #334155; font-size: 0.85rem; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #263347; }}
    a    {{ text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .refresh {{ font-size: 0.8rem; color: #64748b; float: right; margin-top: -40px; }}
  </style>
  <meta http-equiv="refresh" content="5">
</head>
<body>
  <h1>🌐 Smart City — Persistent Middleware</h1>
  <p class="sub">Live telemetry store • Auto-refreshes every 5 seconds</p>
  <span class="refresh">📡 {total} total records</span>

  <div class="stat-row">
    <div class="stat"><div class="val">{len(rows)}</div><div class="lbl">Active Nodes</div></div>
    <div class="stat"><div class="val">{total}</div><div class="lbl">Total Records</div></div>
    <div class="stat"><div class="val">{sum(1 for r in rows if r.domain=='energy')}</div><div class="lbl">Energy Nodes</div></div>
    <div class="stat"><div class="val">{sum(1 for r in rows if r.domain=='water')}</div><div class="lbl">Water Nodes</div></div>
    <div class="stat"><div class="val">{sum(1 for r in rows if r.domain=='air')}</div><div class="lbl">Air Nodes</div></div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Node ID</th><th>Type</th><th>Domain</th><th>Protocol</th>
        <th>State</th><th>Health</th><th>Records</th><th>Last Seen</th><th>History</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(content=html)
