"""
nodes.py — Role-aware node browsing endpoints.

GET /nodes/my           → Nodes the current user has access to (role-scoped)
GET /nodes/browse       → Catalog of all zones+domains (for Resident subscription UI)
GET /nodes/browse/{zone_id} → All nodes in a specific zone
GET /nodes/{node_id}/history → Proxy to Middleware /history/{node_id}
"""
import json
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import User, Role, Team, Subscription, ServicerAssignment
from core.dependencies import get_current_user
from core.config import settings
from schemas import NodeOut

router = APIRouter(prefix="/nodes", tags=["Nodes"])

# --- Domain-to-Team mapping ---
TEAM_TO_DOMAINS = {
    Team.ENERGY:    ["energy"],
    Team.EHS:       ["water", "air"],
    Team.RESIDENTS: ["energy", "water", "air"],  # residents can subscribe to anything
}


async def _fetch_domain(domain: str) -> list[dict]:
    """Fetch latest nodes for a domain from Middleware."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.MIDDLEWARE_URL}/domain/{domain}")
            r.raise_for_status()
            data = r.json()
            nodes = []
            for n in data.get("latest", []):
                payload = n.get("payload") or {}
                loc = n.get("location") or {}
                nodes.append({
                    "node_id":   n.get("node_id", ""),
                    "node_type": n.get("node_type", ""),
                    "zone":      loc.get("zone") or loc.get("zone_id") or "UNKNOWN",
                    "domain":    domain,
                    "health":    n.get("health_status", "UNKNOWN"),
                    "state":     n.get("state", "UNKNOWN"),
                    "last_seen": n.get("timestamp"),
                    "payload":   payload,
                })
            return nodes
    except Exception as e:
        return []


@router.get("/my", response_model=list[NodeOut])
async def my_nodes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns nodes the current user has access to:
    - MANAGER/ANALYST → all nodes in their team's domains
    - SERVICER        → only nodes from active assignments
    - RESIDENT/SMART_USER → nodes in subscribed zones + domains
    """
    all_nodes: list[dict] = []

    if current_user.role in [Role.MANAGER, Role.ANALYST]:
        domains = TEAM_TO_DOMAINS.get(current_user.team, [])
        for domain in domains:
            all_nodes.extend(await _fetch_domain(domain))

    elif current_user.role == Role.SERVICER:
        assignments = db.query(ServicerAssignment).filter(
            ServicerAssignment.servicer_id == current_user.id,
            ServicerAssignment.status.in_(["ASSIGNED", "IN_PROGRESS"])
        ).all()
        assigned_node_ids = {a.node_id for a in assignments}

        # Figure out which domains we need
        domains = TEAM_TO_DOMAINS.get(current_user.team, [])
        for domain in domains:
            nodes = await _fetch_domain(domain)
            for n in nodes:
                if n["node_id"] in assigned_node_ids:
                    all_nodes.append(n)

    elif current_user.role in [Role.RESIDENT, Role.SMART_USER]:
        subs = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()
        subscribed_zones: set[str] = set()
        subscribed_domains: set[str] = set()
        for sub in subs:
            subscribed_zones.update(json.loads(sub.zone_ids))
            subscribed_domains.update(json.loads(sub.engine_types))

        for domain in subscribed_domains:
            nodes = await _fetch_domain(domain)
            for n in nodes:
                if n["zone"] in subscribed_zones:
                    all_nodes.append(n)

    return all_nodes


@router.get("/browse")
async def browse_nodes():
    """
    Public catalog of all zones and domains available in the system.
    Used by Resident UI to discover what to subscribe to.
    """
    all_nodes: list[dict] = []
    for domain in ["energy", "water", "air"]:
        all_nodes.extend(await _fetch_domain(domain))

    zones = sorted({n["zone"] for n in all_nodes if n["zone"] != "UNKNOWN"})
    domain_map: dict[str, list[str]] = {}
    for n in all_nodes:
        domain_map.setdefault(n["zone"], set()).add(n["domain"])

    return {
        "zones": [
            {
                "zone_id": z,
                "domains": list(domain_map.get(z, [])),
                "node_count": sum(1 for n in all_nodes if n["zone"] == z),
            }
            for z in zones
        ],
        "total_zones": len(zones),
        "total_nodes": len(all_nodes),
    }


@router.get("/browse/{zone_id}", response_model=list[NodeOut])
async def browse_zone(zone_id: str):
    """All nodes in a specific zone (for Resident node picker)."""
    all_nodes: list[dict] = []
    for domain in ["energy", "water", "air"]:
        nodes = await _fetch_domain(domain)
        all_nodes.extend([n for n in nodes if n["zone"] == zone_id])
    return all_nodes


@router.get("/{node_id}/history")
async def node_history(
    node_id: str,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user),
):
    """Proxy to Middleware /history/{node_id}. Returns time-series for charting."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.MIDDLEWARE_URL}/history/{node_id}",
                params={"limit": limit},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Middleware unavailable: {e}")
