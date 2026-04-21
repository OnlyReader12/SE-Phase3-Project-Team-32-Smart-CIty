"""
main.py — EHS Domain Engine: FastAPI Application Entry Point.

Team Member 2 (Saicharan) — EHS (Environmental Health & Safety) Engine
Port: 8002

This service is an entirely independent container. On startup it:
  1. Loads config.yaml
  2. Selects the correct ML Strategy from config (Scikit or TensorFlow)
  3. Wires all dependencies: InfluxWriter → AlertPublisher → EHSEngineEvaluator
  4. Starts the AMQP consumer in a background thread (subscribes to telemetry.enviro.#)
  5. Exposes FastAPI routes for health checks and manual testing

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
from fastapi import FastAPI, HTTPException

from consumer.amqp_consumer import AMQPConsumer
from consumer.mqtt_consumer import MQTTConsumer
from evaluator.engine_evaluator import EHSEngineEvaluator
from persistence.influx_writer import InfluxWriter
from publisher.alert_publisher import AlertPublisher
from models.schemas import EHSTelemetry, EvaluatedReading

# Resolve the directory of THIS script (so config.yaml is always found)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ─────────────────────────────────────────────
# Load Configuration
# ─────────────────────────────────────────────

def load_config() -> dict:
    config_path = os.path.join(_BASE_DIR, "config.yaml")
    print(f"[Config] Loading from: {config_path}")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)["ehs_engine"]

    # Optional deployment-time overrides. Defaults remain unchanged for local runs.
    rabbitmq_cfg = config.get("rabbitmq", {})
    mqtt_cfg = config.get("mqtt", {})
    influx_cfg = config.get("influxdb", {})

    rabbitmq_cfg["host"] = os.getenv("EHS_RABBITMQ_HOST", rabbitmq_cfg.get("host", "localhost"))
    rabbitmq_cfg["port"] = int(os.getenv("EHS_RABBITMQ_PORT", rabbitmq_cfg.get("port", 5672)))
    rabbitmq_cfg["username"] = os.getenv("EHS_RABBITMQ_USERNAME", rabbitmq_cfg.get("username", "guest"))
    rabbitmq_cfg["password"] = os.getenv("EHS_RABBITMQ_PASSWORD", rabbitmq_cfg.get("password", "guest"))
    rabbitmq_cfg["exchange"] = os.getenv("EHS_RABBITMQ_EXCHANGE", rabbitmq_cfg.get("exchange", "smartcity"))
    rabbitmq_cfg["subscribe_queue"] = os.getenv(
        "EHS_RABBITMQ_SUBSCRIBE_QUEUE",
        rabbitmq_cfg.get("subscribe_queue", "ehs_telemetry_queue"),
    )
    rabbitmq_cfg["subscribe_binding_key"] = os.getenv(
        "EHS_RABBITMQ_SUBSCRIBE_BINDING_KEY",
        rabbitmq_cfg.get("subscribe_binding_key", "telemetry.enviro.#"),
    )
    rabbitmq_cfg["publish_topic"] = os.getenv(
        "EHS_RABBITMQ_PUBLISH_TOPIC",
        rabbitmq_cfg.get("publish_topic", "alerts.critical"),
    )

    mqtt_cfg["broker_host"] = os.getenv("EHS_MQTT_BROKER_HOST", mqtt_cfg.get("broker_host", "localhost"))
    mqtt_cfg["broker_port"] = int(os.getenv("EHS_MQTT_BROKER_PORT", mqtt_cfg.get("broker_port", 1883)))
    mqtt_cfg["topic"] = os.getenv("EHS_MQTT_TOPIC", mqtt_cfg.get("topic", "smartcity/telemetry/ehs"))
    mqtt_cfg["client_id"] = os.getenv("EHS_MQTT_CLIENT_ID", mqtt_cfg.get("client_id", "ehs_engine_subscriber"))

    influx_cfg["url"] = os.getenv("EHS_INFLUXDB_URL", influx_cfg.get("url", "http://localhost:8086"))
    influx_cfg["token"] = os.getenv("EHS_INFLUXDB_TOKEN", influx_cfg.get("token", "dev-token-replace-in-production"))
    influx_cfg["org"] = os.getenv("EHS_INFLUXDB_ORG", influx_cfg.get("org", "smartcity"))
    influx_cfg["bucket"] = os.getenv("EHS_INFLUXDB_BUCKET", influx_cfg.get("bucket", "ehs_telemetry"))

    config["rabbitmq"] = rabbitmq_cfg
    config["mqtt"] = mqtt_cfg
    config["influxdb"] = influx_cfg
    return config


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
        from ml.scikit_predictor import ScikitAQIPredictor
        return ScikitAQIPredictor(model_path=config.get("model_path", "./models/aqi_forecast.joblib"))
    elif strategy == "tensorflow":
        from ml.tensorflow_predictor import TensorFlowAQIPredictor
        return TensorFlowAQIPredictor(model_path=config.get("tensorflow_model_path", "./models/aqi_forecast_tf"))
    else:
        raise ValueError(f"Unknown ml_strategy: '{strategy}'. Choose 'scikit' or 'tensorflow'.")


# ─────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────

app = FastAPI(
    title="EHS Domain Engine",
    description=(
        "Environmental Health & Safety microservice for the Smart City Living Lab.\n\n"
        "**Team Member 2 (Saicharan)** — Subscribes to `telemetry.enviro.*` on RabbitMQ, "
        "evaluates AQI and water pH thresholds, runs ML forecasts via the Strategy Pattern, "
        "persists to InfluxDB, and publishes CRITICAL alerts back to RabbitMQ.\n\n"
        "Design Patterns: **Strategy** (ML), **Observer** (AMQP), **Factory Method** (Evaluators)"
    ),
    version="1.0.0",
)

# Global references for dependency injection into routes
_evaluator:     EHSEngineEvaluator = None
_consumer:      AMQPConsumer       = None
_mqtt_consumer: MQTTConsumer       = None
_influx:        InfluxWriter       = None
_publisher:     AlertPublisher     = None


@app.on_event("startup")
def startup_event():
    """
    Startup lifecycle hook — wires all components.
    Uses @app.on_event which is proven to work (same pattern as IngestionEngine).
    """
    global _evaluator, _consumer, _mqtt_consumer, _influx, _publisher

    try:
        print("=" * 55)
        print("  EHS Domain Engine — Booting Up")
        print("  Smart City Living Lab | Team Member 2: Saicharan")
        print("=" * 55)

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
        _evaluator = EHSEngineEvaluator(
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

        # 7. Start MQTT consumer for direct IoT Generator integration
        mqtt_cfg = config.get("mqtt", {})
        _mqtt_consumer = MQTTConsumer(
            evaluator=_evaluator,
            broker_host=mqtt_cfg.get("broker_host", "localhost"),
            broker_port=mqtt_cfg.get("broker_port", 1883),
            topic=mqtt_cfg.get("topic", "smartcity/telemetry/ehs"),
            client_id=mqtt_cfg.get("client_id", "ehs_engine_subscriber"),
        )
        _mqtt_consumer.start_listening()

        print("[Main] EHS Engine fully operational on port 8002")
        print("[Main] AMQP subscribed to: telemetry.enviro.#")
        print("[Main] MQTT subscribed to: smartcity/telemetry/ehs")
        print("[Main] Publishing alerts to: alerts.critical")
        print("=" * 55)

    except Exception as e:
        print(f"\n[STARTUP ERROR] Failed to initialize EHS Engine:")
        traceback.print_exc()


@app.on_event("shutdown")
def shutdown_event():
    """Clean up connections on service shutdown."""
    print("[Main] Shutting down EHS Engine...")
    if _mqtt_consumer:
        _mqtt_consumer.stop()
    if _influx:
        _influx.close()
    if _publisher:
        _publisher.close()


# ─────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────

@app.get("/", tags=["Operations"])
async def root():
    """Root endpoint — redirects users to useful pages."""
    return {
        "service": "🌿 EHS Domain Engine",
        "member": "Saicharan (Team Member 2)",
        "status": "running",
        "endpoints": {
            "Swagger UI": "/docs",
            "Health Check": "/health",
            "Thresholds": "/thresholds",
            "Manual Evaluate (POST)": "/evaluate",
        },
        "design_patterns": ["Strategy (ML)", "Observer (AMQP)", "Factory Method (Evaluators)"],
    }


@app.get("/health", tags=["Operations"])
async def health_check():
    """
    Health check endpoint for container orchestration and monitoring.
    Returns engine status including RabbitMQ and InfluxDB connection states.
    """
    return {
        "status": "healthy",
        "service": "ehs_engine",
        "member": "Saicharan (Team Member 2)",
        "protocols": {
            "amqp_topic": "telemetry.enviro.#",
            "amqp_connected": _consumer._connected if _consumer else False,
            "mqtt_topic": "smartcity/telemetry/ehs",
            "mqtt_connected": _mqtt_consumer._connected if _mqtt_consumer else False,
        },
        "alert_topic": "alerts.critical",
        "ml_strategy": type(_evaluator._predictor).__name__ if _evaluator else "not loaded",
    }


@app.post("/evaluate", response_model=EvaluatedReading, tags=["Testing"])
async def manual_evaluate(telemetry: EHSTelemetry):
    """
    Manual evaluation endpoint for development and testing.
    Accepts a raw EHSTelemetry payload and returns the full evaluated result.
    
    Use this to test WITHOUT RabbitMQ running:
    
    ```json
    {
      "node_id": "EHS-NODE-001",
      "domain": "ehs",
      "timestamp": "2026-04-21T17:00:00",
      "data": { "aqi": 350, "water_ph": 4.5, "is_critical": false }
    }
    ```
    """
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="EHS Engine not initialized.")
    result = _evaluator.evaluate(telemetry)
    return result


@app.get("/thresholds", tags=["Configuration"])
async def get_thresholds():
    """Returns the currently configured safety thresholds from config.yaml."""
    if _evaluator is None:
        raise HTTPException(status_code=503, detail="Engine not initialized.")
    return {
        "aqi": {
            "warning":  _evaluator._aqi_evaluator._warning,
            "critical": _evaluator._aqi_evaluator._critical,
        },
        "water_ph": {
            "safe_min":   _evaluator._ph_evaluator._safe_min,
            "safe_max":   _evaluator._ph_evaluator._safe_max,
            "danger_min": _evaluator._ph_evaluator._danger_min,
            "danger_max": _evaluator._ph_evaluator._danger_max,
        },
    }


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
        port=8002,
        log_level="info",
    )
