"""
models/schemas.py — Canonical Pydantic Data Models for the EHS Engine.

These schemas enforce strict data contracts at every boundary of the service.
The SmartCityObject comes in from RabbitMQ (published by Member 1's Ingestion
Engine); EHSTelemetry is our typed parse of the payload; AlertPayload is what
we push back to RabbitMQ for Member 4's Alerting Engine to dispatch.
"""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class SafetyStatus(str, Enum):
    """Possible safety evaluation outcomes for any EHS metric."""
    SAFE     = "SAFE"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class MetricType(str, Enum):
    AQI      = "aqi"
    WATER_PH = "water_ph"


# ─────────────────────────────────────────────
# Inbound: Telemetry from RabbitMQ
# ─────────────────────────────────────────────

class EHSData(BaseModel):
    """The domain-specific data payload inside a SmartCityObject for EHS."""
    aqi: float = Field(..., ge=0, description="Air Quality Index (0–500 scale)")
    water_ph: float = Field(..., ge=0, le=14, description="Water pH (0–14 scale)")
    is_critical: bool = False


class EHSTelemetry(BaseModel):
    """
    The canonical inbound message from RabbitMQ topic: telemetry.enviro.*
    Produced by Member 1 (Sandeep's IoT Ingestion Engine).
    """
    node_id: str
    domain: str = "ehs"
    timestamp: str
    data: EHSData


# ─────────────────────────────────────────────
# Internal: Evaluation Result
# ─────────────────────────────────────────────

class ForecastResult(BaseModel):
    """Output of the Strategy-Pattern ML predictor."""
    predicted_value: float
    confidence: float = Field(..., ge=0.0, le=1.0)
    model: str
    horizon_minutes: int = 60
    trend: str = "stable"  # "rising" | "falling" | "stable"


class EvaluatedReading(BaseModel):
    """
    The fully evaluated state of a single telemetry event.
    Written to InfluxDB and (if CRITICAL) triggers an alert.
    """
    node_id: str
    timestamp: str
    aqi_value: float
    aqi_status: SafetyStatus
    water_ph_value: float
    water_ph_status: SafetyStatus
    overall_status: SafetyStatus
    aqi_forecast: Optional[ForecastResult] = None
    water_ph_forecast: Optional[ForecastResult] = None


# ─────────────────────────────────────────────
# Outbound: Alert payload to RabbitMQ → Member 4
# ─────────────────────────────────────────────

class AlertPayload(BaseModel):
    """
    Minimal warning payload published to 'alerts.critical' topic.
    Member 4's Alerting Engine (Bharat) will consume this and dispatch
    SMS via Twilio / Email via SendGrid. We NEVER call Twilio ourselves.
    """
    source: str = "ehs_engine"
    metric: MetricType
    value: float
    threshold: float
    severity: SafetyStatus
    node_id: str
    timestamp: str
    message: str
