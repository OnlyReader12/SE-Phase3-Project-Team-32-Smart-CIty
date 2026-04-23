"""
models/schemas.py — Canonical Pydantic Data Models for the EHS Engine (Expanded).

These schemas enforce strict data contracts at every boundary of the service.
The SmartCityObject comes in from RabbitMQ (published by Member 1's Ingestion
Engine); EHSTelemetry is our typed parse of the payload; AlertPayload is what
we push back to RabbitMQ for Member 4's Alerting Engine to dispatch.

Expanded to support 6 EHS node types:
  - Air Quality (AQI, PM2.5, PM10, CO2, temp, humidity)
  - Water Quality (pH, turbidity, dissolved O2, water temp)
  - Noise (dB, peak dB, frequency)
  - Weather (temp, humidity, wind, pressure, UV, rainfall)
  - Soil (moisture, pH, temp)
  - Radiation/Gas (radiation µSv, VOC, CO, methane)
"""

from enum import Enum
from typing import Dict, Any, Optional, List
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
    """All metric types monitored by the EHS Engine."""
    AQI              = "aqi"
    WATER_PH         = "water_ph"
    PM25             = "pm25"
    PM10             = "pm10"
    CO2              = "co2_ppm"
    NOISE_DB         = "noise_db"
    UV_INDEX         = "uv_index"
    VOC              = "voc_ppb"
    CO_PPM           = "co_ppm"
    TURBIDITY        = "turbidity_ntu"
    SOIL_MOISTURE    = "soil_moisture_pct"
    RADIATION        = "radiation_usv"
    METHANE          = "methane_ppm"


# ─────────────────────────────────────────────
# Inbound: Telemetry from RabbitMQ
# ─────────────────────────────────────────────

class EHSData(BaseModel):
    """
    The domain-specific data payload inside a SmartCityObject for EHS.
    All new fields are Optional for backward compatibility with existing payloads.
    """
    # ── Air Quality (always present for AQI nodes) ──
    aqi: float = Field(default=0, ge=0, description="Air Quality Index (0–500 scale)")
    water_ph: float = Field(default=7.0, ge=0, le=14, description="Water pH (0–14 scale)")
    is_critical: bool = False

    # ── Air Quality Extended ──
    pm25: Optional[float] = Field(None, ge=0, description="PM2.5 particulate matter (µg/m³)")
    pm10: Optional[float] = Field(None, ge=0, description="PM10 particulate matter (µg/m³)")
    co2_ppm: Optional[float] = Field(None, ge=0, description="Carbon dioxide concentration (ppm)")

    # ── Weather & Environment ──
    temperature_c: Optional[float] = Field(None, description="Ambient temperature (°C)")
    humidity_pct: Optional[float] = Field(None, ge=0, le=100, description="Relative humidity (%)")
    wind_speed_ms: Optional[float] = Field(None, ge=0, description="Wind speed (m/s)")
    wind_direction_deg: Optional[int] = Field(None, ge=0, le=360, description="Wind direction (degrees)")
    pressure_hpa: Optional[float] = Field(None, description="Atmospheric pressure (hPa)")
    uv_index: Optional[float] = Field(None, ge=0, description="UV radiation index")
    rainfall_mm: Optional[float] = Field(None, ge=0, description="Rainfall (mm)")

    # ── Water Quality Extended ──
    turbidity_ntu: Optional[float] = Field(None, ge=0, description="Water turbidity (NTU)")
    dissolved_oxygen_mgl: Optional[float] = Field(None, ge=0, description="Dissolved oxygen (mg/L)")
    water_temp_c: Optional[float] = Field(None, description="Water temperature (°C)")

    # ── Noise ──
    noise_db: Optional[float] = Field(None, ge=0, description="Ambient noise level (dB)")
    peak_db: Optional[float] = Field(None, ge=0, description="Peak noise level (dB)")
    frequency_hz: Optional[int] = Field(None, ge=0, description="Dominant noise frequency (Hz)")

    # ── Soil ──
    soil_moisture_pct: Optional[float] = Field(None, ge=0, le=100, description="Soil moisture (%)")
    soil_ph: Optional[float] = Field(None, ge=0, le=14, description="Soil pH (0–14)")
    soil_temp_c: Optional[float] = Field(None, description="Soil temperature (°C)")

    # ── Radiation & Gas ──
    radiation_usv: Optional[float] = Field(None, ge=0, description="Radiation dose rate (µSv/h)")
    voc_ppb: Optional[float] = Field(None, ge=0, description="Volatile organic compounds (ppb)")
    co_ppm: Optional[float] = Field(None, ge=0, description="Carbon monoxide (ppm)")
    methane_ppm: Optional[float] = Field(None, ge=0, description="Methane concentration (ppm)")


class EHSTelemetry(BaseModel):
    """
    The canonical inbound message from RabbitMQ topic: telemetry.enviro.*
    Produced by Member 1 (Sandeep's IoT Ingestion Engine).
    """
    node_id: str
    domain: str = "ehs"
    node_type: str = "air_quality"
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


class MetricEvaluation(BaseModel):
    """Evaluation result for a single metric."""
    metric: str
    value: float
    status: SafetyStatus
    forecast: Optional[ForecastResult] = None


class EvaluatedReading(BaseModel):
    """
    The fully evaluated state of a single telemetry event.
    Written to InfluxDB and (if CRITICAL) triggers an alert.
    Extended with per-metric detail list for multi-metric nodes.
    """
    node_id: str
    node_type: str = "air_quality"
    timestamp: str
    aqi_value: float
    aqi_status: SafetyStatus
    water_ph_value: float
    water_ph_status: SafetyStatus
    overall_status: SafetyStatus
    aqi_forecast: Optional[ForecastResult] = None
    water_ph_forecast: Optional[ForecastResult] = None
    # Extended metric evaluations (noise, PM2.5, UV, VOC, turbidity, etc.)
    extended_metrics: Optional[List[MetricEvaluation]] = None


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


# ─────────────────────────────────────────────
# Suggestions & Dashboard Models
# ─────────────────────────────────────────────

class SuggestionSeverity(str, Enum):
    """Severity level for actionable suggestions."""
    INFO     = "INFO"
    CAUTION  = "CAUTION"
    URGENT   = "URGENT"
    EMERGENCY = "EMERGENCY"


class EHSSuggestion(BaseModel):
    """
    An actionable recommendation generated by the EHS Engine.
    Based on current readings + ML forecasts.
    """
    id: str
    severity: SuggestionSeverity
    category: str  # "air_quality", "water", "noise", "radiation", "weather"
    title: str
    description: str
    affected_nodes: List[str] = []
    timestamp: str


class NodeStatus(BaseModel):
    """Status card for a single EHS node."""
    node_id: str
    node_type: str
    status: SafetyStatus
    last_value: Dict[str, Any] = {}
    last_seen: str


class EHSDashboardSummary(BaseModel):
    """
    Aggregated campus-wide EHS dashboard data.
    Consumed by the dashboard.html frontend.
    """
    campus_health_score: float = Field(..., ge=0, le=100, description="0=hazardous, 100=pristine")
    total_nodes: int
    critical_count: int
    warning_count: int
    safe_count: int
    metric_cards: Dict[str, Any] = {}
    suggestions: List[EHSSuggestion] = []
    node_statuses: List[NodeStatus] = []
