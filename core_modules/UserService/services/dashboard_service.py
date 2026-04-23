"""
Dashboard service — queries PersistentMiddleware (:8001) and
aggregates data into role-specific shapes.

Includes TEAM ISOLATION:
Managers and Analysts pass their allowed domains to filter results.
"""
import json
import statistics
from typing import Optional
import httpx
from core.config import settings


async def _get(path: str) -> dict | list | None:
    """Fire a GET to PersistentMiddleware and return parsed JSON, or None on error."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.MIDDLEWARE_URL}{path}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"[DashboardService] Middleware call failed: {e}")
        return None


async def get_resident_dashboard(zone_ids: list[str], engine_types: list[str]) -> dict:
    """
    Fetch latest telemetry for each subscribed domain/zone,
    compute simple per-domain summaries.
    """
    summary = {}
    for domain in engine_types:
        data = await _get(f"/domain/{domain}")
        if not data:
            continue
        nodes = [
            n for n in data.get("latest", [])
            if n.get("payload") and _node_in_zones(n, zone_ids)
        ]
        summary[domain] = _summarise_domain(domain, nodes)

    return {"summary": summary}


async def get_analyst_dashboard(engine_types: list[str]) -> dict:
    """
    Fetch trends for allowed domains based on user's team.
    engine_types: ['energy'] or ['water', 'air']
    """
    result = {}
    for domain in engine_types:
        data = await _get(f"/domain/{domain}")
        if not data:
            continue
        nodes = data.get("latest", [])
        result[domain] = _analyst_domain(domain, nodes)
    return result


async def get_servicer_dashboard(node_ids: list[str]) -> dict:
    """
    Return live status for all assigned nodes.
    """
    nodes_out = []
    for node_id in node_ids:
        data = await _get(f"/history/{node_id}?limit=1")
        if not data or not data.get("history"):
            nodes_out.append({
                "node_id": node_id, "node_type": "unknown",
                "zone": "unknown", "state": "OFFLINE",
                "health": "UNKNOWN", "last_seen": None,
                "lat": None, "lon": None, "payload": {}
            })
            continue
        rec = data["history"][0]
        loc = rec.get("location") or {}
        nodes_out.append({
            "node_id": node_id,
            "node_type": rec.get("node_type", "unknown"),
            "zone": loc.get("zone", "unknown"),
            "state": rec.get("state", "UNKNOWN"),
            "health": rec.get("health_status", "UNKNOWN"),
            "last_seen": rec.get("timestamp"),
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "payload": rec.get("payload", {}),
        })

    healthy  = sum(1 for n in nodes_out if n["health"] == "OK")
    degraded = sum(1 for n in nodes_out if n["health"] == "DEGRADED")
    offline  = sum(1 for n in nodes_out if n["state"] == "OFFLINE")

    return {
        "nodes": nodes_out,
        "summary": {
            "total": len(nodes_out),
            "healthy": healthy,
            "degraded": degraded,
            "offline": offline,
        }
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _node_in_zones(node: dict, zone_ids: list[str]) -> bool:
    loc = node.get("location") or {}
    return loc.get("zone") in zone_ids


def _summarise_domain(domain: str, nodes: list) -> dict:
    if domain == "energy":
        powers = [n["payload"].get("power_w") or n["payload"].get("power") for n in nodes if n.get("payload")]
        powers = [p for p in powers if p is not None]
        return {
            "avg_power_w": round(statistics.mean(powers), 1) if powers else 0,
            "active_nodes": len(nodes),
        }
    elif domain == "water":
        phs = [n["payload"].get("ph") for n in nodes if n.get("payload")]
        phs = [p for p in phs if p is not None]
        return {"ph_avg": round(statistics.mean(phs), 2) if phs else 0, "node_count": len(nodes)}
    elif domain == "air":
        aqis = [n["payload"].get("pm2_5") for n in nodes if n.get("payload")]
        aqis = [a for a in aqis if a is not None]
        co2s = [n["payload"].get("co2") for n in nodes if n.get("payload")]
        co2s = [c for c in co2s if c is not None]
        return {
            "aqi_avg": round(statistics.mean(aqis), 1) if aqis else 0,
            "co2_avg": round(statistics.mean(co2s), 1) if co2s else 0,
        }
    return {}


def _moving_avg_prediction(values: list[float], steps: int = 3) -> list[float]:
    if not values:
        return []
    window = values[-min(5, len(values)):]
    avg = statistics.mean(window)
    return [round(avg, 2)] * steps


def _analyst_domain(domain: str, nodes: list) -> dict:
    if domain == "energy":
        powers = [n["payload"].get("power_w") or n["payload"].get("power") for n in nodes if n.get("payload")]
        powers = [p for p in powers if p is not None]
        faults = sum(1 for n in nodes if n.get("health") != "OK")
        return {
            "avg_power_w": round(statistics.mean(powers), 1) if powers else 0,
            "peak_power_w": max(powers, default=0),
            "fault_count": faults,
            "prediction_3_readings": _moving_avg_prediction(powers),
        }
    elif domain == "water":
        phs = [n["payload"].get("ph") for n in nodes if n.get("payload")]
        phs = [p for p in phs if p is not None]
        return {
            "ph_avg": round(statistics.mean(phs), 2) if phs else 0,
            "contamination_events": sum(
                1 for n in nodes
                if (n.get("payload") or {}).get("contamination_level") == "CRITICAL"
            ),
            "prediction_3_readings": _moving_avg_prediction(phs),
        }
    elif domain == "air":
        pm25 = [n["payload"].get("pm2_5") for n in nodes if n.get("payload")]
        pm25 = [p for p in pm25 if p is not None]
        co2  = [n["payload"].get("co2")  for n in nodes if n.get("payload")]
        co2  = [c for c in co2 if c is not None]
        return {
            "pm25_avg": round(statistics.mean(pm25), 1) if pm25 else 0,
            "co2_avg":  round(statistics.mean(co2),  1) if co2  else 0,
            "prediction_3_readings": _moving_avg_prediction(pm25),
        }
    return {}
