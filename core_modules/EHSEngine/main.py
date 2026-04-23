"""
EHSEngine — FastAPI Entry Point (port 8005)
Exposes /metrics/* and /thresholds endpoints used by UserService.
"""
import asyncio, os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)

from engine import EHSEngine
from shared.metrics_service import MetricsService

MIDDLEWARE_URL  = os.getenv("MIDDLEWARE_URL",   "http://127.0.0.1:8001")
USERSERVICE_URL = os.getenv("USERSERVICE_URL",  "http://127.0.0.1:8003")
INTERNAL_KEY    = os.getenv("INTERNAL_API_KEY", "internal-secret-key")
POLL_INTERVAL   = int(os.getenv("POLL_INTERVAL_SEC", "30"))

engine = EHSEngine(
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
    title="EHS Engine",
    description="Environmental Health & Safety analytics & alert generation (port 8005)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {
        "engine": "EHSEngine",
        "rules":  [r.rule_id for r in engine.get_rules()],
        "nodes_cached": len(engine.get_latest_readings()),
    }


@app.get("/metrics/summary")
def metrics_summary():
    """KPI cards for the Analyst Flutter dashboard (EHS team)."""
    readings = engine.get_latest_readings()

    # Average AQI-proxy (PM2.5 values)
    pm25_vals   = [r.get("data", {}).get("pm2_5") for r in readings
                   if r.get("data", {}).get("pm2_5") is not None]
    avg_pm25    = round(sum(pm25_vals) / len(pm25_vals), 2) if pm25_vals else None

    # Water quality score: avg incoming water quality readings
    wq_nodes    = [r for r in readings if "water_quality" in r.get("node_type", "").lower()]
    unsafe_wq   = sum(1 for r in wq_nodes 
                      if (r.get("data", {}).get("ph") or 7) < 6.5 or
                         (r.get("data", {}).get("ph") or 7) > 8.5 or
                         (r.get("data", {}).get("turbidity") or 0) > 4)
    wq_score    = max(0, 100 - (unsafe_wq / len(wq_nodes) * 100)) if wq_nodes else 100

    # Equipment at risk
    pumps_on    = [r for r in readings 
                   if "water_pump" in r.get("node_type", "").lower() 
                   and r.get("data", {}).get("state") == "ON"
                   and (r.get("data", {}).get("flow_level") or 0) < 2]
    dry_runs    = len(pumps_on)

    return {
        "avg_pm2_5_ugm3":      avg_pm25,
        "water_quality_score": round(wq_score, 1),
        "dry_run_risk_nodes":  dry_runs,
        "recent_alerts":       len(engine.get_recent_alerts(10)),
    }


@app.get("/metrics/timeseries")
async def metrics_timeseries(node_id: str, param: str, window: str = "1h"):
    """Time-series {ts, value} data for fl_chart in Flutter."""
    from shared.middleware_client import MiddlewareClient
    client = MiddlewareClient(MIDDLEWARE_URL)
    data = await client.fetch_timeseries(node_id, param, window)
    return {"node_id": node_id, "param": param, "window": window, "series": data}


@app.get("/metrics/aggregate")
def metrics_aggregate(zone: str = None, param: str = "pm2_5"):
    """Zone-level aggregation for bar charts."""
    readings = engine.get_latest_readings()
    if zone:
        readings = [r for r in readings if r.get("zone") == zone]
    return MetricsService.aggregate_zone(readings, param)


@app.get("/trends/{domain}")
def trends(domain: str):
    """SMA-3 trend + 3-step next prediction for PM2.5 or flow rate."""
    readings = engine.get_latest_readings()
    param = "pm2_5" if domain == "air" else "flow_rate_lpm"
    values = [r.get("data", {}).get(param) for r in readings
              if r.get("data", {}).get(param) is not None]
    sma       = MetricsService.simple_moving_average(values)
    predicted = MetricsService.predict_next(values, steps=3)
    return {"sma": sma[-10:], "predicted_next_3": predicted, "domain": domain, "param": param}


@app.get("/alerts")
def get_alerts(limit: int = 50):
    """Recent rule-triggered alerts (up to N)."""
    return engine.get_recent_alerts(limit)


@app.get("/thresholds")
def get_thresholds():
    """All EHS thresholds (drives Flutter analyst sliders)."""
    return engine.get_thresholds()


@app.put("/thresholds/{rule_id}")
def update_threshold(rule_id: str, key: str, value: float):
    """Analyst live-updates a threshold via slider."""
    success = engine.update_threshold(rule_id, key, value)
    if not success:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' or key '{key}' not found")
    return {"updated": True, "rule_id": rule_id, "key": key, "value": value}
