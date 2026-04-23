from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime


class GeoLocation(BaseModel):
    latitude: float
    longitude: float
    zone: Optional[str] = None   # e.g., "Building-A", "Sector-3"


class IOT_Node(BaseModel):
    # -------------------------
    # 🧾 Identity & Classification
    # -------------------------
    node_id: str
    node_type: str            # e.g., "water_pump", "air_sensor"
    domain: str               # "energy" | "water" | "air"

    # -------------------------
    # ⏱️ Time (CRITICAL)
    # -------------------------
    timestamp: datetime

    # -------------------------
    # 📍 Location
    # -------------------------
    location: GeoLocation

    # -------------------------
    # 📡 Communication Context
    # -------------------------
    protocol_source: str             # MQTT / HTTP / CoAP / WebSocket

    # -------------------------
    # 🔄 State & Health
    # -------------------------
    state: Optional[str] = None      # ON / OFF / RUNNING / etc.
    health_status: Optional[str] = "OK"  # OK / DEGRADED / FAILED

    # -------------------------
    # 📦 Node-Specific Data
    # -------------------------
    payload: Dict[str, Any]          # ← THIS is your "specific params"

