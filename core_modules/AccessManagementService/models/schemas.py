"""
models/schemas.py — Pydantic Data Models for the Access Management Service.

Defines all request/response schemas used by the gateway:
  - Telemetry ingestion payloads
  - User authentication (login/register)
  - RBAC role definitions
  - Dashboard response models
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════
# RBAC Role Enum
# ═══════════════════════════════════════════

class UserRole(str, Enum):
    ADMIN = "admin"
    CAMPUS_MANAGER = "campus_manager"
    ANALYST = "analyst"
    MAINTENANCE = "maintenance"
    RESEARCHER = "researcher"
    RESIDENT = "resident"
    EMERGENCY_RESPONDER = "emergency_responder"
    OPERATOR = "operator"


# ═══════════════════════════════════════════
# Telemetry Models
# ═══════════════════════════════════════════

class TelemetryPayload(BaseModel):
    """Universal telemetry ingestion payload — accepts data from any IoT domain."""
    node_id: str = Field(..., description="Unique sensor node identifier (e.g. NRG-SOL-001)")
    domain: str = Field(..., description="Domain: 'energy', 'ehs', 'cam', etc.")
    node_type: str = Field(..., description="Node type within domain (e.g. 'solar_panel')")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    data: Dict[str, Any] = Field(..., description="Sensor readings (flexible per node type)")

    class Config:
        schema_extra = {
            "example": {
                "node_id": "NRG-SOL-001",
                "domain": "energy",
                "node_type": "solar_panel",
                "timestamp": "2026-04-23T12:00:00",
                "data": {
                    "solar_power_w": 850.0,
                    "voltage": 36.5,
                    "current": 23.3,
                }
            }
        }


class TelemetryRecord(BaseModel):
    """A stored telemetry record with server-side metadata."""
    id: str
    node_id: str
    domain: str
    node_type: str
    timestamp: str
    data: Dict[str, Any]
    ingested_at: str


class TelemetryQueryParams(BaseModel):
    """Query parameters for telemetry retrieval."""
    domain: Optional[str] = None
    node_type: Optional[str] = None
    node_id: Optional[str] = None
    since: Optional[str] = None   # ISO timestamp
    until: Optional[str] = None   # ISO timestamp
    limit: int = Field(default=100, le=1000)


# ═══════════════════════════════════════════
# Auth Models
# ═══════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    expires_in: int = 3600

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: UserRole
    full_name: Optional[str] = None
    email: Optional[str] = None

class UserProfile(BaseModel):
    username: str
    role: UserRole
    full_name: Optional[str] = None
    email: Optional[str] = None
    created_at: str
    is_active: bool = True

class UserRecord(BaseModel):
    """Internal user record (includes password hash)."""
    username: str
    password_hash: str
    role: UserRole
    full_name: Optional[str] = None
    email: Optional[str] = None
    created_at: str
    is_active: bool = True


# ═══════════════════════════════════════════
# Dashboard Models
# ═══════════════════════════════════════════

class DashboardData(BaseModel):
    """Role-filtered dashboard response."""
    role: str
    username: str
    role_label: str
    permissions: List[str]
    stats: Dict[str, Any]
    recent_telemetry: List[Dict[str, Any]]
    domains_visible: List[str]
    alerts: List[Dict[str, Any]]
    generated_at: str
