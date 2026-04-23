"""Pydantic schemas for all models."""
import json
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator
from database.models import Role, Team, Domain, AssignmentStatus, AlertSeverity


# ── Auth ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone_number: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    team: str

class RefreshRequest(BaseModel):
    refresh_token: str


# ── User ───────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    team: Team
    is_active: bool
    phone_number: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: Role       # Only ANALYST or SERVICER (Manager enforced in router)
    phone_number: Optional[str] = None


# ── Subscription ───────────────────────────────────────────────────────────

class SubscriptionCreate(BaseModel):
    zone_ids: List[str]        # ["BLK-A", "LIB"]
    engine_types: List[str]    # ["energy", "air"]
    alert_in_app: bool = True
    alert_sms: bool = False
    alert_email: bool = False

class SubscriptionOut(BaseModel):
    id: str
    user_id: str
    zone_ids: List[str]
    engine_types: List[str]
    alert_in_app: bool
    alert_sms: bool
    alert_email: bool
    created_at: datetime

    @classmethod
    def from_orm_obj(cls, obj):
        return cls(
            id=obj.id,
            user_id=obj.user_id,
            zone_ids=json.loads(obj.zone_ids),
            engine_types=json.loads(obj.engine_types),
            alert_in_app=obj.alert_in_app,
            alert_sms=obj.alert_sms,
            alert_email=obj.alert_email,
            created_at=obj.created_at,
        )


# ── ServicerAssignment ─────────────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    servicer_id: str
    domain: Domain
    node_id: str
    zone_id: Optional[str] = None
    notes: Optional[str] = None

class AssignmentStatusUpdate(BaseModel):
    status: AssignmentStatus

class AssignmentNotesUpdate(BaseModel):
    notes: str

class AssignmentResolve(BaseModel):
    status: AssignmentStatus
    notes: str

class AssignmentOut(BaseModel):
    id: str
    servicer_id: str
    domain: Domain
    node_id: str
    zone_id: Optional[str]
    status: AssignmentStatus
    notes: Optional[str]
    assigned_by: str
    assigned_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Alert ──────────────────────────────────────────────────────────────────

class AlertIn(BaseModel):
    """Posted by Domain Engines via /internal/alerts.
    domain is a plain str ('energy', 'water', 'air', 'ehs') — NOT an enum.
    """
    zone_id: Optional[str] = None
    domain: str              # str, not Domain enum — engines send 'ehs' which is not a Domain value
    node_id: Optional[str] = None
    field: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[str] = None
    severity: AlertSeverity
    message: str
    rule_id: Optional[str] = None
    alert_type: Optional[str] = "DOMAIN"

class AlertOut(BaseModel):
    id: str
    zone_id: Optional[str]
    domain: Optional[str]
    node_id: Optional[str]
    field: Optional[str]
    value: Optional[str]
    threshold: Optional[str]
    severity: AlertSeverity
    message: str
    created_at: datetime
    acknowledged: bool
    alert_type: Optional[str]

    class Config:
        from_attributes = True


# ── Actuator ───────────────────────────────────────────────────────────────

class ActuatorCommand(BaseModel):
    field: str    # e.g. "state"
    value: str    # e.g. "OFF", "ON", "OPEN"


# ── Node ───────────────────────────────────────────────────────────────────

class NodeOut(BaseModel):
    """Normalised node entry returned by /nodes/my and /nodes/browse"""
    node_id: str
    node_type: str
    zone: str
    domain: str
    health: Optional[str]
    state: Optional[str]
    last_seen: Optional[str]
    payload: Optional[dict] = {}
