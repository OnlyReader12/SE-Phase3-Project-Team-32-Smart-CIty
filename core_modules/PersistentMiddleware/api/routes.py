"""
api/routes.py — Persistent Middleware API Routes (Expanded EHS Edition)

Provides:
  - POST /middleware/ingest     — Ingests telemetry from IoT Ingestion Engine
  - GET  /history/{node_id}     — Historical records for a specific node
  - GET  /view                  — Live HTML dashboard of all active nodes
  - GET  /ehs/nodes             — All active EHS nodes with latest readings
  - GET  /ehs/latest/{node_type}— Latest readings filtered by EHS node type
  - GET  /ehs/timeseries/{node_id} — Time-series data for a specific EHS node
  - GET  /ehs/summary           — Aggregated campus-wide EHS health summary
"""

import json
from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from fastapi.responses import HTMLResponse
from database.db_core import get_db
from database.models import TelemetryRecord
from services.message_broker import RabbitMQPublisher

router = APIRouter()
publisher = RabbitMQPublisher()


EHS_NODE_CATALOG = [
    {
        "node_type": "air_quality",
        "label": "Air Quality Station",
        "prefix": "EHS-AQI",
        "count": 40,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["aqi", "pm25", "pm10", "co2_ppm", "temperature_c", "humidity_pct"],
        "used_for": ["prediction", "visualization", "suggestions"],
    },
    {
        "node_type": "water_quality",
        "label": "Water Quality Probe",
        "prefix": "EHS-WTR",
        "count": 25,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["water_ph", "turbidity_ntu", "dissolved_oxygen_mgl", "water_temp_c"],
        "used_for": ["prediction", "visualization", "suggestions"],
    },
    {
        "node_type": "noise_monitor",
        "label": "Noise Level Monitor",
        "prefix": "EHS-NOS",
        "count": 20,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["noise_db", "peak_db", "frequency_hz"],
        "used_for": ["visualization", "suggestions"],
    },
    {
        "node_type": "weather_station",
        "label": "Weather Station",
        "prefix": "EHS-WEA",
        "count": 10,
        "protocol": "http",
        "protocols": ["HTTP"],
        "parameters": ["temperature_c", "humidity_pct", "wind_speed_ms", "wind_direction_deg", "pressure_hpa", "uv_index", "rainfall_mm"],
        "used_for": ["visualization", "suggestions"],
    },
    {
        "node_type": "soil_sensor",
        "label": "Soil Sensor",
        "prefix": "EHS-SOL",
        "count": 15,
        "protocol": "coap",
        "protocols": ["CoAP"],
        "parameters": ["soil_moisture_pct", "soil_ph", "soil_temp_c"],
        "used_for": ["visualization", "suggestions"],
    },
    {
        "node_type": "radiation_gas",
        "label": "Radiation/Gas Detector",
        "prefix": "EHS-RAD",
        "count": 10,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["radiation_usv", "voc_ppb", "co_ppm", "methane_ppm"],
        "used_for": ["prediction", "visualization", "suggestions"],
    },
]

EHS_NODE_CATALOG_BY_TYPE = {item["node_type"]: item for item in EHS_NODE_CATALOG}


# ─────────────────────────────────────────────
# Core Ingestion Route (Enhanced)
# ─────────────────────────────────────────────

@router.post("/middleware/ingest")
async def ingest_standard_data(payload: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Receives standard JSON securely from the IoT Ingestion layer.
    Saves it locally to guarantee persistency.
    Now also extracts and persists the ehs_node_type for EHS domain telemetry.
    """
    # 1. Guarantee Persistence (Local SQLite store)
    record = TelemetryRecord(
        node_id=payload.get("node_id"),
        domain=payload.get("domain"),
        protocol_source=payload.get("protocol_source"),
        timestamp=payload.get("timestamp"),
        payload_json=json.dumps(payload.get("payload", {})),
        ehs_node_type=payload.get("node_type") if payload.get("domain") == "ehs" else None,
    )
    db.add(record)
    db.commit()
    
    # 2. Fire and Forget to the Central RabbitMQ Bus
    # Use background tasks to prevent AMQP latency from blocking HTTP threads
    background_tasks.add_task(publisher.publish_telemetry, payload.get("domain"), payload)
    
    return {"status": "persisted_and_published"}


# ─────────────────────────────────────────────
# Original Routes (Preserved)
# ─────────────────────────────────────────────

@router.get("/history/{node_id}")
def get_node_history(node_id: str, limit: int = 50, db: Session = Depends(get_db)):
    """
    Access point to pull historical records for a specific node directly from 
    the Persistent Middleware source of truth.
    """
    records = db.query(TelemetryRecord).filter(TelemetryRecord.node_id == node_id).order_by(TelemetryRecord.id.desc()).limit(limit).all()
    return {"node_id": node_id, "history": [
        {"ts": r.timestamp, "data": json.loads(r.payload_json), "source": r.protocol_source} for r in records
    ]}

@router.get("/view", response_class=HTMLResponse)
def view_live_dashboard(db: Session = Depends(get_db)):
    """
    Generates a simple HTML view to see all distinct nodes checking in. 
    """
    unique_nodes = db.query(TelemetryRecord.node_id, TelemetryRecord.domain, TelemetryRecord.protocol_source).distinct().all()
    
    html_content = "<html><head><title>Edge Live View</title></head><body style='font-family:sans-serif'>"
    html_content += "<h2>🌐 Persistent Middleware: Live IoT Dashboard</h2>"
    html_content += "<p><a href='/ehs/catalog'>View EHS node catalog</a></p>"
    html_content += "<ul>"
    for node in unique_nodes:
        html_content += f"<li><strong>{node.node_id}</strong> ({node.domain}) - Arriving via {node.protocol_source} <a href='/history/{node.node_id}'>[View History]</a></li>"
    html_content += "</ul></body></html>"
    
    return HTMLResponse(content=html_content)


# ─────────────────────────────────────────────
# NEW: EHS-Specific Routes for Engine Access
# ─────────────────────────────────────────────

@router.get("/ehs/nodes")
def get_ehs_nodes(db: Session = Depends(get_db)):
    """
    Returns all active EHS nodes with their latest reading.
    Used by the EHS Engine dashboard to discover and display all environmental sensors.
    """
    # Get distinct EHS node IDs
    ehs_nodes = (
        db.query(TelemetryRecord.node_id, TelemetryRecord.ehs_node_type)
        .filter(TelemetryRecord.domain == "ehs")
        .distinct()
        .all()
    )

    result = []
    for node_id, node_type in ehs_nodes:
        # Fetch the latest record for each node
        latest = (
            db.query(TelemetryRecord)
            .filter(TelemetryRecord.node_id == node_id)
            .order_by(desc(TelemetryRecord.id))
            .first()
        )
        if latest:
            catalog = EHS_NODE_CATALOG_BY_TYPE.get(node_type or "", {})
            result.append({
                "node_id": node_id,
                "node_type": node_type or "unknown",
                "last_seen": latest.timestamp,
                "protocol": latest.protocol_source,
                "protocols": catalog.get("protocols", []),
                "parameters": catalog.get("parameters", []),
                "used_for": catalog.get("used_for", []),
                "latest_data": json.loads(latest.payload_json) if latest.payload_json else {},
            })

    return {"total_ehs_nodes": len(result), "nodes": result}


@router.get("/ehs/catalog")
def get_ehs_catalog():
    """
    Returns the canonical EHS node catalog with parameters and protocols.
    This is the source of truth used by the presentation demo and by the generator.
    """
    return {
        "total_node_types": len(EHS_NODE_CATALOG),
        "total_nodes": sum(item["count"] for item in EHS_NODE_CATALOG),
        "nodes": EHS_NODE_CATALOG,
    }


@router.get("/ehs/latest/{node_type}")
def get_ehs_latest_by_type(
    node_type: str,
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    """
    Returns latest readings filtered by EHS node type.
    Valid types: air_quality, water_quality, noise_monitor, weather_station, soil_sensor, radiation_gas
    
    Used by the EHS Engine for batch processing of node-type-specific telemetry.
    """
    records = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.domain == "ehs")
        .filter(TelemetryRecord.ehs_node_type == node_type)
        .order_by(desc(TelemetryRecord.id))
        .limit(limit)
        .all()
    )

    return {
        "node_type": node_type,
        "count": len(records),
        "readings": [
            {
                "node_id": r.node_id,
                "timestamp": r.timestamp,
                "protocol": r.protocol_source,
                "data": json.loads(r.payload_json) if r.payload_json else {},
            }
            for r in records
        ],
    }


@router.get("/ehs/timeseries/{node_id}")
def get_ehs_timeseries(
    node_id: str,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    """
    Returns time-series data for a specific EHS node.
    Ordered oldest → newest for direct charting compatibility.
    
    Used by the EHS Engine's visualization endpoints and the dashboard.
    """
    records = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.node_id == node_id)
        .order_by(TelemetryRecord.id.asc())
        .limit(limit)
        .all()
    )

    return {
        "node_id": node_id,
        "count": len(records),
        "timeseries": [
            {
                "timestamp": r.timestamp,
                "data": json.loads(r.payload_json) if r.payload_json else {},
            }
            for r in records
        ],
    }


@router.get("/ehs/summary")
def get_ehs_summary(db: Session = Depends(get_db)):
    """
    Aggregated campus-wide EHS health summary.
    Returns latest readings across all EHS node types with computed averages.
    
    Used by the EHS Engine's /dashboard endpoint to populate the campus health score
    and the real-time metric cards.
    """
    summary = {}
    node_types = ["air_quality", "water_quality", "noise_monitor", "weather_station", "soil_sensor", "radiation_gas"]

    for nt in node_types:
        # Get the latest record for each unique node of this type
        nodes = (
            db.query(TelemetryRecord.node_id)
            .filter(TelemetryRecord.domain == "ehs", TelemetryRecord.ehs_node_type == nt)
            .distinct()
            .all()
        )
        readings = []
        for (nid,) in nodes:
            latest = (
                db.query(TelemetryRecord)
                .filter(TelemetryRecord.node_id == nid)
                .order_by(desc(TelemetryRecord.id))
                .first()
            )
            if latest and latest.payload_json:
                readings.append(json.loads(latest.payload_json))

        summary[nt] = {
            "active_nodes": len(readings),
            "latest_readings": readings[:5],  # Sample of up to 5 for the summary
        }

        # Compute averages for key metrics per node type
        if readings:
            if nt == "air_quality":
                summary[nt]["avg_aqi"] = round(sum(r.get("aqi", 0) for r in readings) / len(readings), 1)
                summary[nt]["avg_pm25"] = round(sum(r.get("pm25", 0) for r in readings) / len(readings), 1)
            elif nt == "water_quality":
                summary[nt]["avg_ph"] = round(sum(r.get("water_ph", 7.0) for r in readings) / len(readings), 2)
                summary[nt]["avg_turbidity"] = round(sum(r.get("turbidity_ntu", 0) for r in readings) / len(readings), 2)
            elif nt == "noise_monitor":
                summary[nt]["avg_noise_db"] = round(sum(r.get("noise_db", 0) for r in readings) / len(readings), 1)
                summary[nt]["max_noise_db"] = round(max(r.get("peak_db", 0) for r in readings), 1)
            elif nt == "weather_station":
                summary[nt]["avg_temp"] = round(sum(r.get("temperature_c", 0) for r in readings) / len(readings), 1)
                summary[nt]["avg_uv"] = round(sum(r.get("uv_index", 0) for r in readings) / len(readings), 1)
            elif nt == "radiation_gas":
                summary[nt]["avg_voc"] = round(sum(r.get("voc_ppb", 0) for r in readings) / len(readings))
                summary[nt]["max_radiation"] = round(max(r.get("radiation_usv", 0) for r in readings), 3)

    return {"campus_ehs_summary": summary}
