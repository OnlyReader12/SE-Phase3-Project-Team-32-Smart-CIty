"""
MiddlewareClient — async fetcher from PersistentMiddleware (:8001).
Shared across all engines.

Real Middleware endpoints (as implemented):
  GET /domain/{domain}         → latest record per node in that domain
  GET /history/{node_id}       → last N records for one node
  GET /nodes                   → all distinct nodes seen

engine_type mapping:
  'energy' → domain 'energy'
  'ehs'    → domains 'water' + 'air'  (fetched and merged)
"""
import httpx
import logging

logger = logging.getLogger(__name__)

# Maps engine_type filter value → list of Middleware domain names
ENGINE_TYPE_TO_DOMAINS = {
    "energy": ["energy"],
    "ehs":    ["water", "air"],
    "water":  ["water"],
    "air":    ["air"],
}


class MiddlewareClient:
    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")

    async def fetch_latest(self, params: dict = None) -> list[dict]:
        """
        Fetch latest readings for all nodes relevant to this engine.
        Uses GET /domain/{domain} — the real Middleware endpoint.
        If engine_type is 'ehs', merges water + air domain results.
        Returns a normalised list of node dicts.
        """
        engine_type = (params or {}).get("engine_type", "energy")
        domains = ENGINE_TYPE_TO_DOMAINS.get(engine_type, [engine_type])

        all_nodes = []
        async with httpx.AsyncClient(timeout=10) as client:
            for domain in domains:
                try:
                    resp = await client.get(f"{self._base}/domain/{domain}")
                    resp.raise_for_status()
                    data = resp.json()
                    raw  = data.get("latest", [])
                    # Normalise to the shape expected by AnalysisRules:
                    # { node_id, node_type, zone, health, state, data:{...} }
                    for r in raw:
                        all_nodes.append({
                            "node_id":   r.get("node_id"),
                            "node_type": r.get("node_type", ""),
                            "zone":      (r.get("payload") or {}).get("zone_id", "UNKNOWN"),
                            "health":    r.get("health_status"),
                            "state":     r.get("state"),
                            "last_seen": r.get("timestamp"),
                            "data":      r.get("payload") or {},
                        })
                except Exception as exc:
                    logger.warning(f"[MiddlewareClient] Fetch failed for domain '{domain}': {exc}")

        logger.debug(f"[MiddlewareClient] Fetched {len(all_nodes)} nodes for engine_type='{engine_type}'")
        return all_nodes

    async def fetch_timeseries(self, node_id: str, param: str, window: str = "1h") -> list[dict]:
        """
        Fetch time-series data using GET /history/{node_id}.
        Extracts the requested param from each record's payload.
        Returns list of {ts, value} dicts.
        """
        limit_map = {"1h": 120, "6h": 720, "24h": 2880}
        limit = limit_map.get(window, 120)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base}/history/{node_id}",
                    params={"limit": limit},
                )
                resp.raise_for_status()
                history = resp.json().get("history", [])
                series = []
                for record in history:
                    payload = record.get("payload") or {}
                    value = payload.get(param)
                    if value is not None:
                        series.append({"ts": record.get("timestamp"), "value": value})
                return series
        except Exception as exc:
            logger.warning(f"[MiddlewareClient] Timeseries fetch failed for {node_id}/{param}: {exc}")
            return []
