"""
models/schemas.py — Canonical Pydantic Data Models for the Energy Management Engine.

These schemas enforce strict data contracts at every boundary of the service.
The SmartCityObject comes in from RabbitMQ (published by Member 1's Ingestion
Engine); EnergyTelemetry is our typed parse of the payload; AlertPayload is what
we push back to RabbitMQ for Member 4's Alerting Engine to dispatch.

Supports 7 Energy node types:
  - Solar Panel       (power_w, energy_kwh, voltage, current, status)
  - Smart Energy Meter(voltage, current, power_w, energy_kwh, power_factor)
  - Battery Storage   (soc_pct, voltage, charge_rate_w, status)
  - Grid Transformer  (load_pct, temperature_c, fault_status)
  - Occupancy Sensor  (occupancy_detected, person_count)
  - Smart Water Meter (flow_rate_lpm, total_consumption_l, leak_detected)
  - AC Unit           (set_temp_c, mode, power_w, state)
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class SafetyStatus(str, Enum):
    """Possible evaluation outcomes for any Energy metric."""
    SAFE     = "SAFE"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class MetricType(str, Enum):
    """All metric types monitored by the Energy Management Engine."""
    SOLAR_POWER      = "solar_power_w"
    POWER_FACTOR     = "power_factor"
    BATTERY_SOC      = "battery_soc_pct"
    GRID_LOAD        = "grid_load_pct"
    OCCUPANCY_COUNT  = "person_count"
    WATER_FLOW       = "flow_rate_lpm"
    WATER_LEAK       = "leak_detected"
    AC_POWER         = "ac_power_w"
    VOLTAGE          = "voltage"
    CURRENT          = "current"
    ENERGY_KWH       = "energy_kwh"


# ─────────────────────────────────────────────
# Inbound: Telemetry from RabbitMQ
# ─────────────────────────────────────────────

class EnergyData(BaseModel):
    """
    The domain-specific data payload inside a SmartCityObject for Energy.
    All fields are Optional for maximum flexibility across 7 node types.
    """
    # ── Solar Panel ──
    solar_power_w: Optional[float] = Field(None, ge=0, description="Solar generation power (Watts)")
    energy_kwh: Optional[float] = Field(None, ge=0, description="Accumulated energy (kWh)")
    voltage: Optional[float] = Field(None, ge=0, description="Voltage (V)")
    current: Optional[float] = Field(None, ge=0, description="Current (A)")
    solar_status: Optional[str] = Field(None, description="Solar panel status: active/inactive/fault")

    # ── Smart Energy Meter ──
    power_w: Optional[float] = Field(None, ge=0, description="Active power consumption (Watts)")
    power_factor: Optional[float] = Field(None, ge=0, le=1.0, description="Power factor (0–1)")

    # ── Battery Storage ──
    battery_soc_pct: Optional[float] = Field(None, ge=0, le=100, description="State of charge (%)")
    charge_rate_w: Optional[float] = Field(None, description="Charge/discharge rate (Watts, negative=discharging)")
    battery_status: Optional[str] = Field(None, description="Battery status: charging/discharging/idle/fault")

    # ── Grid / Transformer ──
    grid_load_pct: Optional[float] = Field(None, ge=0, description="Grid transformer load (%)")
    grid_temperature_c: Optional[float] = Field(None, description="Transformer temperature (°C)")
    fault_status: Optional[str] = Field(None, description="Fault status: normal/warning/fault")

    # ── Occupancy / Footfall ──
    occupancy_detected: Optional[bool] = Field(None, description="Whether occupancy is detected")
    person_count: Optional[int] = Field(None, ge=0, description="Person count in zone")

    # ── Smart Water Meter ──
    flow_rate_lpm: Optional[float] = Field(None, ge=0, description="Water flow rate (L/min)")
    total_consumption_l: Optional[float] = Field(None, ge=0, description="Total water consumed (liters)")
    leak_detected: Optional[bool] = Field(None, description="Whether a water leak is detected")

    # ── AC Unit / Appliance ──
    ac_power_w: Optional[float] = Field(None, ge=0, description="AC unit power consumption (Watts)")
    set_temp_c: Optional[float] = Field(None, description="AC set temperature (°C)")
    ac_mode: Optional[str] = Field(None, description="AC mode: cool/heat/fan/auto")
    ac_state: Optional[str] = Field(None, description="AC state: on/off")

    # ── General ──
    is_critical: bool = False


class EnergyTelemetry(BaseModel):
    """
    The canonical inbound message from RabbitMQ topic: telemetry.power.*
    Produced by Member 1 (Sandeep's IoT Ingestion Engine).
    """
    node_id: str
    domain: str = "energy"
    node_type: str = "solar_panel"
    timestamp: str
    data: EnergyData


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
    """
    node_id: str
    node_type: str = "solar_panel"
    timestamp: str
    overall_status: SafetyStatus
    # All metric evaluations for this reading
    metric_evaluations: List[MetricEvaluation] = []
    # Primary metrics (for quick access)
    primary_metric: Optional[str] = None
    primary_value: Optional[float] = None
    primary_status: Optional[SafetyStatus] = None
    primary_forecast: Optional[ForecastResult] = None


# ─────────────────────────────────────────────
# Outbound: Alert payload to RabbitMQ → Member 4
# ─────────────────────────────────────────────

class AlertPayload(BaseModel):
    """
    Minimal warning payload published to 'alerts.critical' topic.
    Member 4's Alerting Engine (Bharat) will consume this and dispatch
    SMS via Twilio / Email via SendGrid. We NEVER call Twilio ourselves.
    """
    source: str = "energy_engine"
    metric: str
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
    INFO      = "INFO"
    CAUTION   = "CAUTION"
    URGENT    = "URGENT"
    EMERGENCY = "EMERGENCY"


class EnergySuggestion(BaseModel):
    """
    An actionable recommendation generated by the Energy Engine.
    Based on current readings + ML forecasts.
    Implements the Command Pattern concept — each suggestion represents
    a potential automation command (e.g., TurnOffLamppost, ReduceACLoad).
    """
    id: str
    severity: SuggestionSeverity
    category: str  # "solar", "battery", "grid", "efficiency", "water", "hvac"
    title: str
    description: str
    affected_nodes: List[str] = []
    command_type: Optional[str] = None  # Command Pattern: "turn_off", "reduce_load", etc.
    timestamp: str


class NodeStatus(BaseModel):
    """Status card for a single Energy node."""
    node_id: str
    node_type: str
    status: SafetyStatus
    last_value: Dict[str, Any] = {}
    last_seen: str


class EnergyDashboardSummary(BaseModel):
    """
    Aggregated campus-wide Energy dashboard data.
    Consumed by the dashboard.html frontend.
    """
    campus_energy_score: float = Field(..., ge=0, le=100, description="0=critical grid failure, 100=optimal efficiency")
    total_nodes: int
    critical_count: int
    warning_count: int
    safe_count: int
    total_solar_generation_w: float = 0
    total_consumption_w: float = 0
    avg_battery_soc: float = 0
    avg_grid_load: float = 0
    metric_cards: Dict[str, Any] = {}
    suggestions: List[EnergySuggestion] = []
    node_statuses: List[NodeStatus] = []
    generated_at: Optional[str] = None
