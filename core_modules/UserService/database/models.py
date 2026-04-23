"""
All ORM models: User, Subscription, ServicerAssignment, Alert.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from database.db import Base
import enum


def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ──────────────────────────────────────────────────────────────────

class Role(str, enum.Enum):
    RESIDENT    = "RESIDENT"
    SMART_USER  = "SMART_USER"  # Resident with local actuator control
    ANALYST     = "ANALYST"
    SERVICER    = "SERVICER"
    MANAGER     = "MANAGER"


class Team(str, enum.Enum):
    ENERGY      = "ENERGY"
    EHS         = "EHS"
    RESIDENTS   = "RESIDENTS"


class Domain(str, enum.Enum):
    ENERGY = "energy"
    WATER  = "water"
    AIR    = "air"


class AssignmentStatus(str, enum.Enum):
    ASSIGNED    = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED    = "RESOLVED"
    CLOSED      = "CLOSED"


class AlertSeverity(str, enum.Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


# ── Tables ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id             = Column(String, primary_key=True, default=_uuid)
    email          = Column(String, unique=True, nullable=False, index=True)
    password_hash  = Column(String, nullable=False)
    full_name      = Column(String, nullable=False)
    role           = Column(SAEnum(Role), nullable=False)
    team           = Column(SAEnum(Team), nullable=False, default=Team.RESIDENTS)
    created_by     = Column(String, nullable=True)
    is_active      = Column(Boolean, default=True)
    phone_number   = Column(String, nullable=True)
    created_at     = Column(DateTime, default=_now)

    subscriptions  = relationship("Subscription", back_populates="owner",
                                  cascade="all, delete", foreign_keys="[Subscription.user_id]")
    assignments    = relationship("ServicerAssignment", back_populates="servicer",
                                  foreign_keys="[ServicerAssignment.servicer_id]")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id           = Column(String, primary_key=True, default=_uuid)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    zone_ids     = Column(Text, nullable=False)    # JSON: ["BLK-A","LIB"]
    engine_types = Column(Text, nullable=False)    # JSON: ["energy","air"]
    alert_in_app = Column(Boolean, default=True)
    alert_sms    = Column(Boolean, default=False)
    alert_email  = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=_now)

    owner = relationship("User", back_populates="subscriptions", foreign_keys=[user_id])


class ServicerAssignment(Base):
    __tablename__ = "servicer_assignments"

    id          = Column(String, primary_key=True, default=_uuid)
    servicer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    domain      = Column(SAEnum(Domain), nullable=False)
    node_id     = Column(String, nullable=False)
    zone_id     = Column(String, nullable=True)
    status      = Column(SAEnum(AssignmentStatus), default=AssignmentStatus.ASSIGNED)
    notes       = Column(Text, nullable=True)
    assigned_by = Column(String, nullable=False)   # manager user.id (soft ref, no FK)
    assigned_at = Column(DateTime, default=_now)
    updated_at  = Column(DateTime, default=_now, onupdate=_now)

    servicer = relationship("User", back_populates="assignments",
                            foreign_keys=[servicer_id])


class Alert(Base):
    __tablename__ = "alerts"

    id              = Column(String, primary_key=True, default=_uuid)
    alert_type      = Column(String, default="DOMAIN")  # DOMAIN|NODE|ASSIGNMENT|ACTUATOR|SYSTEM
    rule_id         = Column(String, nullable=True)
    zone_id         = Column(String, nullable=True, index=True)
    domain          = Column(String, nullable=True)      # String (not Enum) so SYSTEM alerts work
    node_id         = Column(String, nullable=True)
    field           = Column(String, nullable=True)
    value           = Column(String, nullable=True)
    threshold       = Column(String, nullable=True)
    severity        = Column(SAEnum(AlertSeverity), nullable=False)
    message         = Column(Text, nullable=False)
    acknowledged    = Column(Boolean, default=False)
    acknowledged_by = Column(String, nullable=True)
    auto_acked      = Column(Boolean, default=False)
    resolved        = Column(Boolean, default=False)
    resolved_at     = Column(DateTime, nullable=True)
    escalated_from  = Column(String, nullable=True)
    target_user_id  = Column(String, nullable=True)
    created_at      = Column(DateTime, default=_now, index=True)


class AlertDeliveryLog(Base):
    """Tracks every alert delivery attempt so Managers can audit who was notified."""
    __tablename__ = "alert_delivery_logs"

    id           = Column(String, primary_key=True, default=_uuid)
    alert_id     = Column(String, nullable=False, index=True)
    user_id      = Column(String, nullable=False)
    channel      = Column(String, nullable=False)   # 'in_app' | 'sms' | 'email'
    status       = Column(String, nullable=False)   # 'sent' | 'failed' | 'rate_limited'
    attempted_at = Column(DateTime, default=_now)
    error_msg    = Column(Text, nullable=True)
