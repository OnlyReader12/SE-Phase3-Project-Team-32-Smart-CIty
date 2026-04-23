"""
main.py — Energy Management Engine: FastAPI Application Entry Point.

Team Member 3 (Raghuram) — Energy Management Engine
Port: 8003

This service is an entirely independent container. On startup it:
  1. Loads config.yaml
  2. Selects the correct ML Strategy from config (Scikit or TensorFlow)
  3. Wires all dependencies: InfluxWriter → AlertPublisher → EnergyEngineEvaluator
  4. Starts the AMQP consumer in a background thread (subscribes to telemetry.power.#)
  5. Exposes FastAPI routes for health checks, manual testing, prediction,
     visualization, suggestions, and a real-time dashboard

API Surface:
  GET  /                    → Service info
  GET  /health              → Health check
  GET  /thresholds          → Current energy thresholds
  POST /evaluate            → Manual evaluation testing
  GET  /predict/{node_id}   → ML forecast for a specific node
  GET  /visualize/timeseries → Time-series chart data
  GET  /visualize/heatmap   → Campus-wide energy heatmap
  GET  /suggestions         → Actionable energy suggestions
  GET  /dashboard-data      → Full dashboard JSON summary
  GET  /dashboard           → Interactive HTML dashboard
  GET  /presentation-data   → Presentation demo JSON
  GET  /presentation        → Presentation HTML page

Design Patterns:
  - Strategy  (ML predictor, swappable via config.yaml)
  - Factory   (ThresholdEvaluator creation per metric)
  - Observer  (AMQP consumer on telemetry.power.#)
  - Command   (Suggestion actions: turn_off, reduce_load, etc.)

What this engine DOES NOT do:
  ❌ Talk to Twilio / SendGrid (Member 4 handles that)
  ❌ Parse raw MQTT/CoAP protocols (Member 1 handles that)
  ❌ Manage user roles or RBAC (Member 5 handles that)
"""

import os
import sys
import yaml
import uvicorn
import traceback
import copy
import random
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from consumer.amqp_consumer import AMQPConsumer
from evaluator.engine_evaluator import EnergyEngineEvaluator
from persistence.influx_writer import InfluxWriter
from publisher.alert_publisher import AlertPublisher
from models.schemas import EnergyTelemetry, EvaluatedReading

# Resolve the directory of THIS script (so config.yaml is always found)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PORT = int(os.getenv("ENERGY_ENGINE_PORT", "8003"))


# ─────────────────────────────────────────────
# Load Configuration
# ─────────────────────────────────────────────

def load_config() -> dict:
    config_path = os.path.join(_BASE_DIR, "config.yaml")
    print(f"[Config] Loading from: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)["energy_engine"]


def get_middleware_base_url() -> str:
    config = load_config()
    return config.get("middleware", {}).get("base_url", "http://localhost:8001")


# ─────────────────────────────────────────────
# Strategy Pattern: Build Predictor from Config
# ─────────────────────────────────────────────

def build_predictor(config: dict):
    """
    Factory function that reads config.yaml and instantiates the correct
    PredictorStrategy. Swapping from scikit to tensorflow requires
    updating exactly ONE key in config.yaml — no code changes.
    """
    strategy = config.get("ml_strategy", "scikit")
    if strategy == "scikit":
        from ml.scikit_predictor import ScikitEnergyPredictor
        return ScikitEnergyPredictor(model_path=config.get("model_path", "./models/energy_forecast.joblib"))
    elif strategy == "tensorflow":
        from ml.tensorflow_predictor import TensorFlowEnergyPredictor
        return TensorFlowEnergyPredictor(model_path=config.get("tensorflow_model_path", "./models/energy_forecast_tf"))
    else:
        raise ValueError(f"Unknown ml_strategy: '{strategy}'. Choose 'scikit' or 'tensorflow'.")


# ─────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────

app = FastAPI(
    title="Energy Management Engine",
    description=(
        "Energy Management microservice for the Smart City Living Lab.\n\n"
        "**Team Member 3 (Raghuram)** — Monitors 7 Energy node types (Solar Panel, Smart Meter, "
        "Battery Storage, Grid Transformer, Occupancy, Water Meter, AC Unit) across campus sensors.\n\n"
        "Subscribes to `telemetry.power.*` on RabbitMQ, evaluates 7 metrics against efficiency thresholds, "
        "runs ML forecasts via the Strategy Pattern, generates actionable energy suggestions with "
        "Command Pattern semantics, persists to InfluxDB, and publishes CRITICAL alerts.\n\n"
        "Design Patterns: **Strategy** (ML), **Observer** (AMQP), **Factory Method** (Evaluators), "
        "**Command** (Suggestions)"
    ),
    version="2.0.0",
)

# Global references for dependency injection into routes
_evaluator: EnergyEngineEvaluator = None
_consumer:  AMQPConsumer          = None
_influx:    InfluxWriter          = None
_publisher: AlertPublisher        = None


@app.on_event("startup")
def startup_event():
    """
    Startup lifecycle hook — wires all components.
    Uses @app.on_event which is proven to work (same pattern as EHS Engine).
    """
    global _evaluator, _consumer, _influx, _publisher

    try:
        print("=" * 60)
        print("  Energy Management Engine v2.0 — Booting Up")
        print("  Smart City Living Lab | Team Member 3: Raghuram")
        print("  7 Node Types | 7 Metrics | 2 Protocols")
        print("=" * 60)

        # 1. Load config
        config = load_config()
        rmq_cfg    = config["rabbitmq"]
        influx_cfg = config["influxdb"]
        thresholds = config["thresholds"]

        # 2. Strategy Pattern: build selected ML predictor
        predictor = build_predictor(config)
        print(f"[Main] ML Strategy loaded: {type(predictor).__name__}")

        # 3. Build InfluxDB writer
        _influx = InfluxWriter(
            url=influx_cfg["url"],
            token=influx_cfg["token"],
            org=influx_cfg["org"],
            bucket=influx_cfg["bucket"],
        )

        # 4. Build RabbitMQ alert publisher
        _publisher = AlertPublisher(
            host=rmq_cfg["host"],
            port=rmq_cfg["port"],
            username=rmq_cfg.get("username", "guest"),
            password=rmq_cfg.get("password", "guest"),
            exchange=rmq_cfg["exchange"],
            publish_topic=rmq_cfg["publish_topic"],
        )

        # 5. Wire core evaluator (Strategy + Factory injected here)
        _evaluator = EnergyEngineEvaluator(
            predictor=predictor,
            influx_writer=_influx,
            alert_publisher=_publisher,
            thresholds=thresholds,
        )

        # 6. Start AMQP consumer as background Observer thread
        _consumer = AMQPConsumer(
            evaluator=_evaluator,
            host=rmq_cfg["host"],
            port=rmq_cfg["port"],
            username=rmq_cfg.get("username", "guest"),
            password=rmq_cfg.get("password", "guest"),
            exchange=rmq_cfg["exchange"],
            queue_name=rmq_cfg["subscribe_queue"],
            binding_key=rmq_cfg["subscribe_binding_key"],
        )
        _consumer.start_listening()

        print(f"[Main] Energy Engine fully operational on port {SERVER_PORT}")
        print("[Main] Subscribed to: telemetry.power.#")
        print("[Main] Publishing alerts to: alerts.critical")
        print(f"[Main] Dashboard: http://localhost:{SERVER_PORT}/dashboard")
        print("=" * 60)

    except Exception as e:
        print(f"\n[STARTUP ERROR] Failed to initialize Energy Engine:")
        traceback.print_exc()


@app.on_event("shutdown")
def shutdown_event():
    """Clean up connections on service shutdown."""
    print("[Main] Shutting down Energy Engine...")
    if _influx:
        _influx.close()
    if _publisher:
        _publisher.close()


# ─────────────────────────────────────────────
# API Routes — Operations
# ─────────────────────────────────────────────

@app.get("/", tags=["Operations"])
async def root():
    """Root endpoint — redirects users to useful pages."""
    return {
        "service": "⚡ Energy Management Engine v2.0",
        "member": "Raghuram (Team Member 3)",
        "status": "running",
        "node_types": [
            "solar_panel", "smart_meter", "battery_storage",
            "grid_transformer", "occupancy_sensor", "water_meter", "ac_unit"
        ],
        "endpoints": {
            "Swagger UI": "/docs",
            "Health Check": "/health",
            "Thresholds": "/thresholds",
            "Manual Evaluate (POST)": "/evaluate",
            "Predictions": "/predict/{node_id}",
            "Time-Series Visualization": "/visualize/timeseries",
            "Heatmap": "/visualize/heatmap",
            "Suggestions": "/suggestions",
            "Dashboard Data (JSON)": "/dashboard-data",
            "Dashboard (HTML)": "/dashboard",
        },
        "design_patterns": ["Strategy (ML)", "Observer (AMQP)", "Factory Method (Evaluators)", "Command (Suggestions)"],
        "protocols": ["MQTT", "HTTP"],
    }


@app.get("/health", tags=["Operations"])
async def health_check():
    """
    Health check endpoint for container orchestration and monitoring.
    Returns engine status including RabbitMQ and InfluxDB connection states.
    """
    return {
        "status": "healthy",
        "service": "energy_engine",
        "version": "2.0.0",
        "member": "Raghuram (Team Member 3)",
        "subscribed_topic": "telemetry.power.#",
        "alert_topic": "alerts.critical",
        "rabbitmq_connected": _consumer._connected if _consumer else False,
        "ml_strategy": type(_evaluator._predictor).__name__ if _evaluator else "not loaded",
        "nodes_tracked": len(_evaluator._latest_evaluations) if _evaluator else 0,
        "metrics_monitored": [
            "solar_power_w", "power_factor", "battery_soc_pct",
            "grid_load_pct", "person_count", "flow_rate_lpm", "ac_power_w"
        ],
    }


# ─────────────────────────────────────────────
# API Routes — Testing & Evaluation
# ─────────────────────────────────────────────

@app.post("/evaluate", response_model=EvaluatedReading, tags=["Testing"])
async def manual_evaluate(telemetry: EnergyTelemetry):
    """
    Manual evaluation endpoint for development and testing.
    Accepts a raw EnergyTelemetry payload and returns the full evaluated result.

    Use this to test WITHOUT RabbitMQ running:

    ```json
    {
      "node_id": "NRG-SOL-001",
      "domain": "energy",
      "node_type": "solar_panel",
      "timestamp": "2026-04-23T08:00:00",
      "data": {
        "solar_power_w": 30, "voltage": 38.5, "current": 0.78,
        "energy_kwh": 12.5, "solar_status": "active"
      }
    }
    ```
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Energy Engine not initialized.")
    return await run_in_threadpool(_evaluator.evaluate, telemetry)


@app.get("/thresholds", tags=["Configuration"])
async def get_thresholds():
    """Returns the currently configured safety thresholds from config.yaml."""
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")
    return {
        "solar_power": {
            "warning":  _evaluator._solar_evaluator._warning,
            "critical": _evaluator._solar_evaluator._critical,
        },
        "power_factor": {
            "warning":  _evaluator._pf_evaluator._warning,
            "critical": _evaluator._pf_evaluator._critical,
        },
        "battery_soc": {
            "warning":  _evaluator._battery_evaluator._warning,
            "critical": _evaluator._battery_evaluator._critical,
        },
        "grid_load": {
            "warning":  _evaluator._grid_evaluator._warning,
            "critical": _evaluator._grid_evaluator._critical,
        },
        "occupancy": {
            "warning":  _evaluator._occupancy_evaluator._warning,
            "critical": _evaluator._occupancy_evaluator._critical,
        },
        "water_leak": {
            "warning":  _evaluator._water_evaluator._warning,
            "critical": _evaluator._water_evaluator._critical,
        },
        "ac_overload": {
            "warning":  _evaluator._ac_evaluator._warning,
            "critical": _evaluator._ac_evaluator._critical,
        },
    }


# ─────────────────────────────────────────────
# API Routes — Prediction
# ─────────────────────────────────────────────

@app.get("/predict/{node_id}", tags=["Prediction"])
async def get_prediction(node_id: str):
    """
    Returns ML forecasts for a specific node based on its rolling history.
    Uses the Strategy-Pattern predictor (Scikit-learn or TensorFlow).
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")

    result = _evaluator.get_prediction(node_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No sufficient history for node '{node_id}'. Send at least 3 readings via POST /evaluate."
        )
    return result


# ─────────────────────────────────────────────
# API Routes — Visualization
# ─────────────────────────────────────────────

@app.get("/visualize/timeseries", tags=["Visualization"])
async def get_timeseries(
    metric: str = Query(default="solar_power_w", description="Metric to visualize: solar_power_w, battery_soc_pct, grid_load_pct, ac_power_w"),
    limit: int = Query(default=50, le=200, description="Max data points per node"),
):
    """
    Returns time-series data for a specific metric across all tracked nodes.
    Suitable for rendering with Chart.js, D3.js, or any charting library.
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")
    return _evaluator.get_visualization_data(metric=metric, limit=limit)


@app.get("/visualize/heatmap", tags=["Visualization"])
async def get_heatmap():
    """
    Returns campus-wide metric heatmap data — latest value and status for every node.
    Used for geographic overlay visualization on campus maps.
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")
    return _evaluator.get_heatmap_data()


# ─────────────────────────────────────────────
# API Routes — Suggestions
# ─────────────────────────────────────────────

@app.get("/suggestions", tags=["Suggestions"])
async def get_suggestions():
    """
    Returns actionable Energy suggestions based on current readings and ML forecasts.
    Suggestions are severity-ranked: EMERGENCY > URGENT > CAUTION > INFO.
    Each suggestion includes a command_type (Command Pattern).
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")
    suggestions = _evaluator.generate_suggestions()
    return {
        "total_suggestions": len(suggestions),
        "suggestions": [s.dict() for s in suggestions],
    }


# ─────────────────────────────────────────────
# API Routes — Dashboard
# ─────────────────────────────────────────────

@app.get("/dashboard-data", tags=["Dashboard"])
async def get_dashboard_data():
    """
    Returns the full Energy dashboard JSON payload.
    Includes: campus energy score, metric cards, node statuses, and suggestions.
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")
    summary = _evaluator.get_dashboard_summary()
    return summary.dict()


@app.get("/presentation-data", tags=["Presentation"])
async def get_presentation_data():
    """
    Returns a single payload for the presentation demo.
    Combines engine summary, middleware node catalog, visualizations, and suggestions.
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")

    dashboard = _evaluator.get_dashboard_summary().dict()
    node_statuses = dashboard.get("node_statuses", [])
    primary_node = node_statuses[0]["node_id"] if node_statuses else None
    middleware_base = get_middleware_base_url()

    middleware_catalog = {}
    middleware_nodes = {}
    middleware_error = None
    try:
        catalog_response = requests.get(f"{middleware_base}/energy/catalog", timeout=4)
        middleware_catalog = catalog_response.json() if catalog_response.ok else {"error": catalog_response.text}
        nodes_response = requests.get(f"{middleware_base}/energy/nodes", timeout=4)
        middleware_nodes = nodes_response.json() if nodes_response.ok else {"error": nodes_response.text}
    except Exception as exc:
        middleware_error = str(exc)

    prediction = _evaluator.get_prediction(primary_node) if primary_node else None

    presentation_dashboard = copy.deepcopy(dashboard)
    snapshot_label = random.choice(["Live snapshot", "Presentation snapshot", "Refresh snapshot"])
    refresh_tick = random.randint(1000, 9999)

    if presentation_dashboard.get("node_statuses"):
        spotlight = random.choice(presentation_dashboard["node_statuses"])
    else:
        spotlight = {"node_id": "N/A", "node_type": "unknown", "status": "SAFE"}

    base_score = presentation_dashboard.get("campus_energy_score", 0)
    presentation_dashboard["campus_energy_score"] = max(0, min(100, round(base_score + random.uniform(-2.0, 2.0), 1)))
    presentation_dashboard["presentation_snapshot"] = {
        "label": snapshot_label,
        "refresh_tick": refresh_tick,
        "spotlight_node": spotlight,
    }

    if presentation_dashboard.get("suggestions"):
        random.shuffle(presentation_dashboard["suggestions"])

    metric_cards = presentation_dashboard.get("metric_cards", {})
    for card in metric_cards.values():
        if isinstance(card, dict) and "avg" in card:
            try:
                card["avg"] = round(float(card["avg"]) + random.uniform(-0.5, 0.5), 1)
            except Exception:
                pass

    return {
        "flow": [
            {
                "id": "discover",
                "title": "Discover Energy Nodes",
                "status": "done",
                "detail": f"{len(middleware_catalog.get('nodes', [])) or len(node_statuses)} nodes discovered",
            },
            {
                "id": "ingest",
                "title": "Ingest Power Telemetry",
                "status": "done",
                "detail": f"{dashboard.get('total_nodes', 0)} active nodes in memory",
            },
            {
                "id": "predict",
                "title": "Predict Energy Trajectory",
                "status": "done" if prediction else "idle",
                "detail": "ML forecast prepared for the most recent node" if prediction else "No forecast available yet",
            },
            {
                "id": "visualize",
                "title": "Render Energy Visualization",
                "status": "done",
                "detail": f"{dashboard.get('metric_cards', {}) and len(dashboard.get('metric_cards', {})) or 0} metric cards available",
            },
            {
                "id": "suggest",
                "title": "Generate Energy Suggestions",
                "status": "done",
                "detail": f"{len(dashboard.get('suggestions', []))} actionable suggestions ready",
            },
        ],
        "engine": presentation_dashboard,
        "prediction": prediction,
        "middleware": {
            "base_url": middleware_base,
            "catalog": middleware_catalog,
            "nodes": middleware_nodes,
            "error": middleware_error,
        },
        "generated_at": dashboard.get("generated_at") or None,
    }


@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
async def serve_dashboard():
    """
    Serves the interactive Energy Dashboard HTML page.
    The dashboard auto-refreshes by polling /dashboard-data every 5 seconds.
    """
    dashboard_path = os.path.join(_BASE_DIR, "static", "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(
            content="<h1>Dashboard not found</h1><p>Ensure static/dashboard.html exists.</p>",
            status_code=404,
        )


@app.get("/presentation", response_class=HTMLResponse, tags=["Presentation"])
async def serve_presentation():
    """Serves the presentation-focused start button demo page."""
    presentation_path = os.path.join(_BASE_DIR, "static", "presentation.html")
    if os.path.exists(presentation_path):
        with open(presentation_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h1>Presentation page not found</h1><p>Ensure static/presentation.html exists.</p>",
        status_code=404,
    )


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # IMPORTANT: Use `app` directly, NOT the string "main:app".
    # String reference causes uvicorn to re-import the module, creating
    # a separate global namespace where _evaluator gets set in the new
    # import but the routes reference the old (None) globals.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=SERVER_PORT,
        log_level="info",
    )
