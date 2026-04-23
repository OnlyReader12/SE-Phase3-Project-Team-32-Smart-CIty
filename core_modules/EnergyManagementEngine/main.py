"""
EnergyManagementEngine — FastAPI Entry Point (port 8004)
Exposes /metrics/* and /thresholds endpoints used by UserService.
"""
import asyncio, os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)

from engine import EnergyManagementEngine
from shared.metrics_service import MetricsService

MIDDLEWARE_URL  = os.getenv("MIDDLEWARE_URL",   "http://127.0.0.1:8001")
USERSERVICE_URL = os.getenv("USERSERVICE_URL",  "http://127.0.0.1:8003")
INTERNAL_KEY    = os.getenv("INTERNAL_API_KEY", "internal-secret-key")
POLL_INTERVAL   = int(os.getenv("POLL_INTERVAL_SEC", "30"))

engine = EnergyManagementEngine(
    middleware_url=MIDDLEWARE_URL,
    userservice_url=USERSERVICE_URL,
    internal_api_key=INTERNAL_KEY,
    poll_interval_sec=POLL_INTERVAL,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(engine.start())
    yield
    task.cancel()


app = FastAPI(
    title="Energy Management Engine",
    description="Rule-based energy analytics & alert generation (port 8004)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {
        "engine": "EnergyManagementEngine",
        "rules":  [r.rule_id for r in engine.get_rules()],
        "nodes_cached": len(engine.get_latest_readings()),
    }


@app.get("/metrics/summary")
def metrics_summary():
    """KPI cards for the Analyst Flutter dashboard."""
    readings = engine.get_latest_readings()
    # Solar
    solar_kw  = sum(r.get("data", {}).get("power_w", 0) / 1000
                    for r in readings if "solar" in r.get("node_type", "").lower())
    # Consumption
    usage_kw  = sum(r.get("data", {}).get("power", 0) / 1000
                    for r in readings if "energy_meter" in r.get("node_type", "").lower())
    # Battery SOC average
    bats      = [r.get("data", {}).get("soc") for r in readings
                 if "battery" in r.get("node_type", "").lower() and r.get("data", {}).get("soc")]
    avg_soc   = round(sum(bats) / len(bats), 1) if bats else None

    return {
        "solar_generation_kw":  round(solar_kw, 3),
        "total_consumption_kw": round(usage_kw, 3),
        "net_balance_kw":       round(solar_kw - usage_kw, 3),
        "avg_battery_soc_pct":  avg_soc,
        "recent_alerts":        len(engine.get_recent_alerts(10)),
    }


@app.get("/metrics/timeseries")
async def metrics_timeseries(node_id: str, param: str, window: str = "1h"):
    """Time-series {ts, value} data for a specific node parameter (for fl_chart)."""
    from shared.middleware_client import MiddlewareClient
    client = MiddlewareClient(MIDDLEWARE_URL)
    data = await client.fetch_timeseries(node_id, param, window)
    return {"node_id": node_id, "param": param, "window": window, "series": data}


@app.get("/metrics/aggregate")
def metrics_aggregate(zone: str = None, param: str = "power_w"):
    """Aggregate stats for a zone (used by bar charts in Flutter)."""
    readings = engine.get_latest_readings()
    if zone:
        readings = [r for r in readings if r.get("zone") == zone]
    return MetricsService.aggregate_zone(readings, param)


@app.get("/trends/{domain}")
def trends(domain: str):
    """SMA-3 trend + 3-step prediction for a domain parameter."""
    readings  = engine.get_latest_readings()
    values    = [r.get("data", {}).get("power_w", 0) / 1000
                 for r in readings if r.get("data", {}).get("power_w") is not None]
    sma       = MetricsService.simple_moving_average(values)
    predicted = MetricsService.predict_next(values, steps=3)
    return {"sma": sma[-10:], "predicted_next_3": predicted, "domain": domain}


@app.get("/alerts")
def get_alerts(limit: int = 50):
    """Recent rule-triggered alerts (last N)."""
    return engine.get_recent_alerts(limit)


@app.get("/thresholds")
def get_thresholds():
    """All analyst-adjustable thresholds (drives Flutter sliders)."""
    return engine.get_thresholds()


@app.put("/thresholds/{rule_id}")
def update_threshold(rule_id: str, key: str, value: float):
    """Analyst updates a slider value live."""
    success = engine.update_threshold(rule_id, key, value)
    if not success:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' or key '{key}' not found")
    return {"updated": True, "rule_id": rule_id, "key": key, "value": value}
