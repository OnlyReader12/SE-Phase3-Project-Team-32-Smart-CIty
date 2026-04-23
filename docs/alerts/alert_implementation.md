# 🔧 Alert Implementation Guide — UserService Changes

This document describes the concrete code changes needed in `UserService` to implement the full alert system designed in the other docs.

---

## What Exists vs What Needs to Change

| Component | Current State | Needs |
|---|---|---|
| `Alert` DB model | Basic (zone, domain, message, ack) | +`alert_type`, `rule_id`, `status`, `resolved`, `escalated_from`, `target_user_id` |
| `AlertService.process_alert` | Engine-only, no cooldown | +All 5 event types, +cooldown check, +routing algorithm |
| `TwilioService` | Basic SMS | +Rate limiter (3/hr/user) |
| `SendGrid` | Basic email | +Severity filter (no INFO emails) |
| `AlertDeliveryLog` | Missing | New table |
| `AlertCooldown` check | Missing | In-memory dict + DB check |
| Endpoints | `/internal/alerts` only | +`GET /alerts/my`, `PUT /alerts/{id}/acknowledge`, `PUT /alerts/{id}/resolve` |
| Background jobs | Missing | +Auto-ack job (24h), +Escalation job (30min) |

---

## 1. Updated DB Models

```python
# In database/models.py — ADD to Alert class:

class AlertType(str, enum.Enum):
    DOMAIN     = "DOMAIN"
    NODE       = "NODE"
    ASSIGNMENT = "ASSIGNMENT"
    ACTUATOR   = "ACTUATOR"
    SYSTEM     = "SYSTEM"

class AlertStatus(str, enum.Enum):
    DELIVERED   = "DELIVERED"
    RESOLVED    = "RESOLVED"

# Updated Alert model columns:
class Alert(Base):
    __tablename__ = "alerts"
    id             = Column(String, primary_key=True, default=_uuid)
    alert_type     = Column(SAEnum(AlertType), default=AlertType.DOMAIN)
    rule_id        = Column(String, nullable=True)        # e.g. 'water_safety'
    zone_id        = Column(String, nullable=True, index=True)
    domain         = Column(String, nullable=True)        # loosened to String for system alerts
    node_id        = Column(String, nullable=True)
    severity       = Column(SAEnum(AlertSeverity), nullable=False)
    message        = Column(Text, nullable=False)
    status         = Column(SAEnum(AlertStatus), default=AlertStatus.DELIVERED)
    field          = Column(String, nullable=True)
    value          = Column(String, nullable=True)
    threshold      = Column(String, nullable=True)
    acknowledged   = Column(Boolean, default=False)
    acknowledged_by = Column(String, nullable=True)
    auto_acked     = Column(Boolean, default=False)
    resolved       = Column(Boolean, default=False)
    resolved_at    = Column(DateTime, nullable=True)
    escalated_from = Column(String, nullable=True)  # parent alert id
    target_user_id = Column(String, nullable=True)  # ASSIGNMENT type direct recipient
    created_at     = Column(DateTime, default=_now, index=True)

class AlertDeliveryLog(Base):
    __tablename__ = "alert_delivery_logs"
    id           = Column(String, primary_key=True, default=_uuid)
    alert_id     = Column(String, nullable=False, index=True)
    user_id      = Column(String, nullable=False)
    channel      = Column(String, nullable=False)  # 'in_app' | 'sms' | 'email'
    status       = Column(String, nullable=False)  # 'sent' | 'failed' | 'rate_limited'
    attempted_at = Column(DateTime, default=_now)
    error_msg    = Column(Text, nullable=True)
```

---

## 2. Updated AlertService

```python
# services/alert_service.py — FULL REPLACEMENT

from datetime import datetime, timedelta
from collections import defaultdict
import json, logging
from sqlalchemy.orm import Session
from database.models import Alert, AlertType, AlertDeliveryLog, Subscription, User, Role, ServicerAssignment
from services.twilio_service import send_sms
from services.sendgrid_service import send_email

logger = logging.getLogger(__name__)

# ── Cooldown config ─────────────────────────────────────────────────────────
COOLDOWN = {
    "DOMAIN":     300,
    "NODE":       600,
    "SYSTEM":     900,
    "ASSIGNMENT": 0,
    "ACTUATOR":   0,
}

# ── SMS rate limiter ─────────────────────────────────────────────────────────
_sms_count: dict = defaultdict(int)
_sms_window_end: datetime = datetime.utcnow() + timedelta(hours=1)
SMS_MAX_PER_HOUR = 3


def _check_cooldown(alert_type: str, rule_id: str, node_id: str, db: Session) -> bool:
    """Returns True if alert should be SUPPRESSED (within cooldown)."""
    cd = COOLDOWN.get(alert_type, 0)
    if cd == 0:
        return False
    cutoff = datetime.utcnow() - timedelta(seconds=cd)
    return db.query(Alert).filter(
        Alert.rule_id    == rule_id,
        Alert.node_id    == node_id,
        Alert.alert_type == alert_type,
        Alert.created_at >= cutoff,
        Alert.resolved   == False,
    ).first() is not None


def _get_recipients(alert: Alert, db: Session) -> list[tuple]:
    """Returns list of (user, subscription_or_None) tuples."""
    recipients = []

    # Managers always receive everything
    managers = db.query(User).filter(User.role == Role.MANAGER, User.is_active == True).all()
    for m in managers:
        recipients.append((m, None))

    if alert.alert_type in [AlertType.DOMAIN.value, AlertType.NODE.value]:
        # Resident subscription matching
        for sub in db.query(Subscription).all():
            try:
                zones   = json.loads(sub.zone_ids)
                domains = json.loads(sub.engine_types)
            except Exception:
                continue
            if alert.zone_id in zones and alert.domain in domains:
                user = db.query(User).filter(User.id == sub.user_id, User.is_active == True).first()
                if user and user.role == Role.RESIDENT:
                    recipients.append((user, sub))

        # Servicer assignment matching
        if alert.node_id:
            for asgn in db.query(ServicerAssignment).filter(
                ServicerAssignment.node_id == alert.node_id,
                ServicerAssignment.status.in_(["ASSIGNED", "IN_PROGRESS"])
            ).all():
                user = db.query(User).filter(User.id == asgn.servicer_id, User.is_active == True).first()
                if user:
                    recipients.append((user, None))

    if alert.alert_type == AlertType.ASSIGNMENT.value and alert.target_user_id:
        user = db.query(User).filter(User.id == alert.target_user_id, User.is_active == True).first()
        if user:
            recipients.append((user, None))

    # Deduplicate by user.id
    seen, unique = set(), []
    for item in recipients:
        uid = item[0].id
        if uid not in seen:
            seen.add(uid)
            unique.append(item)
    return unique


def _send_sms_safe(user_id: str, phone: str, message: str, db: Session, alert_id: str):
    global _sms_count, _sms_window_end
    if datetime.utcnow() > _sms_window_end:
        _sms_count.clear()
        _sms_window_end = datetime.utcnow() + timedelta(hours=1)

    log = AlertDeliveryLog(alert_id=alert_id, user_id=user_id, channel="sms")
    if _sms_count[user_id] >= SMS_MAX_PER_HOUR:
        log.status, log.error_msg = "rate_limited", "Max 3 SMS/hour exceeded"
    else:
        try:
            send_sms(phone, message)
            _sms_count[user_id] += 1
            log.status = "sent"
        except Exception as e:
            log.status, log.error_msg = "failed", str(e)
    db.add(log)


def _send_email_safe(user_id: str, email: str, full_name: str, alert, db: Session, alert_id: str):
    log = AlertDeliveryLog(alert_id=alert_id, user_id=user_id, channel="email")
    try:
        send_email(email, full_name, alert)
        log.status = "sent"
    except Exception as e:
        log.status, log.error_msg = "failed", str(e)
    db.add(log)


def process_alert(alert_in, db: Session):
    """Main entry point. Call for all alert types."""
    alert_type = getattr(alert_in, "alert_type", "DOMAIN")
    rule_id    = getattr(alert_in, "rule_id", None) or alert_type
    node_id    = getattr(alert_in, "node_id", None)

    # 1. Cooldown check
    if _check_cooldown(alert_type, rule_id, node_id, db):
        logger.debug(f"[AlertService] Suppressed (cooldown): {rule_id}/{node_id}")
        return

    # 2. Persist
    alert = Alert(
        alert_type     = alert_type,
        rule_id        = rule_id,
        zone_id        = getattr(alert_in, "zone_id", None),
        domain         = getattr(alert_in, "domain", None),
        node_id        = node_id,
        severity       = alert_in.severity,
        message        = alert_in.message,
        field          = getattr(alert_in, "metric_key", None),
        value          = str(getattr(alert_in, "metric_value", "")),
        threshold      = str(getattr(alert_in, "threshold_value", "")),
        target_user_id = getattr(alert_in, "target_user_id", None),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    # 3. Log in-app delivery
    db.add(AlertDeliveryLog(alert_id=alert.id, user_id="system", channel="in_app", status="sent"))

    # 4. Route + dispatch channels
    for user, sub in _get_recipients(alert, db):
        severity = alert.severity.value if hasattr(alert.severity, "value") else alert.severity

        # SMS: CRITICAL only
        if severity == "CRITICAL" and user.phone_number:
            wants_sms = (sub and sub.alert_sms) or user.role.value in ["MANAGER", "SERVICER"]
            if wants_sms:
                _send_sms_safe(user.id, user.phone_number, alert.message, db, alert.id)

        # Email: WARNING+
        if severity in ["WARNING", "CRITICAL"]:
            wants_email = (sub and sub.alert_email) or user.role.value == "MANAGER"
            if wants_email and user.email:
                _send_email_safe(user.id, user.email, user.full_name, alert_in, db, alert.id)

    db.commit()
    logger.info(f"[AlertService] Alert delivered: [{alert.severity}] {alert.message[:60]}")
```

---

## 3. Background Jobs (add to main.py startup)

```python
# In UserService/main.py — add to lifespan:

async def _auto_ack_job(db_factory):
    """Auto-acknowledge alerts older than 24h."""
    while True:
        await asyncio.sleep(3600)  # run hourly
        db = next(db_factory())
        cutoff = datetime.utcnow() - timedelta(hours=24)
        stale = db.query(Alert).filter(
            Alert.acknowledged == False,
            Alert.created_at < cutoff
        ).all()
        for a in stale:
            a.acknowledged = True
            a.auto_acked   = True
        db.commit()
        db.close()
        logger.info(f"[AutoAck] Auto-acknowledged {len(stale)} stale alerts.")
```

---

## 4. New API Endpoints (add to dashboard_alerts_actuators.py)

```python
@router.get("/alerts/my")
def my_alerts(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns alerts visible to this user based on role."""
    if current_user.role == Role.MANAGER:
        return db.query(Alert).filter(Alert.resolved == False).order_by(Alert.created_at.desc()).limit(100).all()
    if current_user.role == Role.RESIDENT:
        subs = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()
        zone_ids = [z for sub in subs for z in json.loads(sub.zone_ids)]
        return db.query(Alert).filter(Alert.zone_id.in_(zone_ids), Alert.resolved == False).all()
    if current_user.role == Role.SERVICER:
        asgns = db.query(ServicerAssignment).filter(ServicerAssignment.servicer_id == current_user.id).all()
        node_ids = [a.node_id for a in asgns]
        return db.query(Alert).filter(Alert.node_id.in_(node_ids), Alert.resolved == False).all()
    return []

@router.put("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged    = True
    alert.acknowledged_by = current_user.id
    db.commit()
    return {"acknowledged": True}

@router.put("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in [Role.MANAGER, Role.SERVICER]:
        raise HTTPException(403, "Only Managers and Servicers can resolve alerts")
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.resolved    = True
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"resolved": True}
```
