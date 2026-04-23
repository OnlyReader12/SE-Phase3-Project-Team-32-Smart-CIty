"""
Alert service — full subsystem implementation.

Handles:
  1. Cooldown deduplication (suppress repeated alerts within window)
  2. Persistence to alerts table
  3. Team-scoped routing (Manager/Analyst/Servicer)
  4. Subscription-scoped routing (Resident/SmartUser)
  5. Channel dispatch: in-app (always) + SMS (CRITICAL + opt-in) + Email (WARNING+ + opt-in)
  6. Delivery log — every attempt is tracked in alert_delivery_logs

External dependencies (SMS/Email) fail gracefully — alerts still stored in DB.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from sqlalchemy.orm import Session

from database.models import Alert, AlertDeliveryLog, Subscription, User, Role, Team
from core.config import settings

logger = logging.getLogger(__name__)

# ── Cooldown Store ─────────────────────────────────────────────────────────
# key: (rule_id, node_id)  value: last triggered timestamp
_cooldown: dict[tuple, datetime] = {}

COOLDOWN_SECONDS = {
    "DOMAIN":     300,   # 5 min
    "NODE":       600,   # 10 min
    "SYSTEM":     900,   # 15 min
    "ASSIGNMENT": 0,
    "ACTUATOR":   0,
}

def _is_rate_limited(alert_type: str, rule_id: str, node_id: str) -> bool:
    secs = COOLDOWN_SECONDS.get(alert_type, 300)
    if secs == 0:
        return False
    key = (rule_id or alert_type, node_id or "")
    last = _cooldown.get(key)
    if last and (datetime.now(timezone.utc) - last).total_seconds() < secs:
        logger.debug(f"[AlertService] Suppressed (cooldown): {key}")
        return True
    _cooldown[key] = datetime.now(timezone.utc)
    return False

# ── SMS Rate Limiter ───────────────────────────────────────────────────────
_sms_count: dict[str, int] = defaultdict(int)
_sms_window_end: datetime = datetime.now(timezone.utc) + timedelta(hours=1)
SMS_MAX_PER_HOUR = 3

# ── Team → Domain mapping ─────────────────────────────────────────────────
DOMAIN_TO_TEAM = {
    "energy": Team.ENERGY,
    "water":  Team.EHS,
    "air":    Team.EHS,
}


def _log_delivery(db: Session, alert_id: str, user_id: str,
                  channel: str, status: str, error: str = None):
    try:
        log = AlertDeliveryLog(
            alert_id=alert_id, user_id=user_id,
            channel=channel, status=status, error_msg=error
        )
        db.add(log)
    except Exception as e:
        logger.error(f"[AlertService] Failed to write delivery log: {e}")


def _send_sms(user_id: str, phone: str, message: str,
              db: Session, alert_id: str):
    global _sms_count, _sms_window_end
    if datetime.now(timezone.utc) > _sms_window_end:
        _sms_count.clear()
        _sms_window_end = datetime.now(timezone.utc) + timedelta(hours=1)

    if _sms_count[user_id] >= SMS_MAX_PER_HOUR:
        _log_delivery(db, alert_id, user_id, "sms", "rate_limited",
                      "Max 3 SMS/hour exceeded")
        return

    try:
        if settings.twilio_enabled:
            from services.twilio_service import send_sms
            send_sms(phone, message)
        else:
            logger.info(f"[AlertService] SMS (disabled) → {phone}: {message[:60]}")
        _sms_count[user_id] += 1
        _log_delivery(db, alert_id, user_id, "sms", "sent")
    except Exception as e:
        _log_delivery(db, alert_id, user_id, "sms", "failed", str(e))
        logger.error(f"[AlertService] SMS error for {user_id}: {e}")


def _send_email(user_id: str, email: str, name: str,
                alert_in, db: Session, alert_id: str):
    try:
        if settings.sendgrid_enabled:
            from services.sendgrid_service import send_email
            send_email(email, name, alert_in)
        else:
            logger.info(f"[AlertService] Email (disabled) → {email}")
        _log_delivery(db, alert_id, user_id, "email", "sent")
    except Exception as e:
        _log_delivery(db, alert_id, user_id, "email", "failed", str(e))
        logger.error(f"[AlertService] Email error for {user_id}: {e}")


def process_alert(alert_in, db: Session):
    """
    Main entry point called by all alert sources.
    alert_in: AlertIn schema object
    """
    alert_type = getattr(alert_in, "alert_type", None) or "DOMAIN"
    rule_id    = getattr(alert_in, "rule_id", None) or alert_type
    node_id    = getattr(alert_in, "node_id", None)
    severity   = alert_in.severity.value if hasattr(alert_in.severity, "value") else str(alert_in.severity)
    domain     = getattr(alert_in, "domain", None)
    if hasattr(domain, "value"):
        domain = domain.value

    # 1. Cooldown check
    if _is_rate_limited(alert_type, rule_id, node_id):
        return

    # 2. Persist
    alert = Alert(
        alert_type=alert_type,
        rule_id=rule_id,
        zone_id=getattr(alert_in, "zone_id", None),
        domain=domain,
        node_id=node_id,
        severity=alert_in.severity,
        message=alert_in.message,
        field=getattr(alert_in, "field", None),
        value=str(getattr(alert_in, "value", "") or ""),
        threshold=str(getattr(alert_in, "threshold", "") or ""),
        target_user_id=getattr(alert_in, "target_user_id", None),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    # Log in-app delivery (always)
    _log_delivery(db, alert.id, "broadcast", "in_app", "sent")

    # 3. Route to staff (Manager/Analyst/Servicer) by team domain
    target_team = DOMAIN_TO_TEAM.get(domain) if domain else None
    if target_team:
        staff = db.query(User).filter(
            User.team == target_team,
            User.is_active == True,
            User.role.in_([Role.MANAGER, Role.SERVICER])
        ).all()
        for member in staff:
            # SMS: CRITICAL only, Manager + Servicer
            if severity == "CRITICAL" and member.phone_number:
                _send_sms(member.id, member.phone_number,
                          f"[{target_team.value} ALERT] {alert_in.message}",
                          db, alert.id)
            # Email: WARNING+ for Managers
            if severity in ["WARNING", "CRITICAL"] and member.role == Role.MANAGER and member.email:
                _send_email(member.id, member.email, member.full_name,
                            alert_in, db, alert.id)

    # 4. Route to Residents by subscription
    for sub in db.query(Subscription).all():
        try:
            zone_ids     = json.loads(sub.zone_ids)
            engine_types = json.loads(sub.engine_types)
        except Exception:
            continue

        zone_ok   = (not alert.zone_id) or (alert.zone_id in zone_ids)
        domain_ok = (not domain) or (domain in engine_types)
        if not (zone_ok and domain_ok):
            continue

        user = db.query(User).filter(
            User.id == sub.user_id, User.is_active == True
        ).first()
        if not user or user.role not in [Role.RESIDENT, Role.SMART_USER]:
            continue

        if sub.alert_sms and user.phone_number and severity == "CRITICAL":
            _send_sms(user.id, user.phone_number, alert_in.message, db, alert.id)

        if sub.alert_email and user.email and severity in ["WARNING", "CRITICAL"]:
            _send_email(user.id, user.email, user.full_name, alert_in, db, alert.id)

    db.commit()
    logger.info(f"[AlertService] [{severity}] Alert {alert.id} stored: {alert_in.message[:60]}")


def get_alerts_for_user(user: User, db: Session,
                        acknowledged: bool = None, limit: int = 50) -> list:
    """
    Returns alerts visible to the given user based on their role + team.
    acknowledged=None → all, =False → unread only, =True → read only
    """
    q = db.query(Alert)

    if user.role == Role.MANAGER:
        # Sees all alerts for their team's domains
        from routers.nodes import TEAM_TO_DOMAINS
        allowed_domains = TEAM_TO_DOMAINS.get(user.team, [])
        q = q.filter(Alert.domain.in_(allowed_domains))

    elif user.role == Role.ANALYST:
        from routers.nodes import TEAM_TO_DOMAINS
        allowed_domains = TEAM_TO_DOMAINS.get(user.team, [])
        q = q.filter(Alert.domain.in_(allowed_domains))

    elif user.role == Role.SERVICER:
        from database.models import ServicerAssignment
        node_ids = [
            a.node_id for a in db.query(ServicerAssignment).filter(
                ServicerAssignment.servicer_id == user.id
            ).all()
        ]
        q = q.filter(Alert.node_id.in_(node_ids))

    elif user.role in [Role.RESIDENT, Role.SMART_USER]:
        subs = db.query(Subscription).filter(Subscription.user_id == user.id).all()
        zone_ids = list({z for s in subs for z in json.loads(s.zone_ids)})
        q = q.filter(Alert.zone_id.in_(zone_ids))

    if acknowledged is not None:
        q = q.filter(Alert.acknowledged == acknowledged)

    return q.order_by(Alert.created_at.desc()).limit(limit).all()
