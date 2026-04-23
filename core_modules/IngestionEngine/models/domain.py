"""
Canonical domain model for the Ingestion Engine.

Every raw payload — regardless of origin protocol (HTTP, MQTT, CoAP,
WebSocket) — is normalised into this SmartCityObject before being
forwarded to the Persistent Middleware via RabbitMQ.

This gives the entire backend a single, typed contract.
"""
from pydantic import BaseModel
from typing import Any, Dict, Optional


class SmartCityObject(BaseModel):
    """
    Unified canonical data structure for the Smart City backend.

    After normalisation all downstream consumers (Middleware, Domain Engines)
    work with this object only — they never see raw protocol payloads.
    """

    # ── Identity ──────────────────────────────────────────────────────
    node_id:         str
    node_type:       str = "unknown"      # e.g. "solar_panel", "water_quality"
    domain:          str                  # "energy" | "water" | "air"

    # ── Time ──────────────────────────────────────────────────────────
    timestamp:       str                  # ISO-8601 UTC string

    # ── Node state & health ───────────────────────────────────────────
    state:           Optional[str] = None           # ON / OFF / RUNNING / …
    health_status:   Optional[str] = "OK"           # OK / DEGRADED / FAILED

    # ── Location ──────────────────────────────────────────────────────
    location:        Optional[Dict[str, Any]] = None

    # ── Communication ─────────────────────────────────────────────────
    protocol_source: str                  # HTTP_POST / MQTT_PUB / CoAP_PUT / WebSocket

    # ── Domain-specific data ──────────────────────────────────────────
    payload:         Dict[str, Any]       # node-type-specific field dict
