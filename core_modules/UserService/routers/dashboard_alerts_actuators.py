"""
Dashboard, actuator, and alert routers.
ENFORCES TEAM ISOLATION.
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional

from database.db import get_db
from database.models import User, Role, Team, Subscription, ServicerAssignment, Alert
from core.dependencies import get_current_user, require_role
from core.config import settings
from schemas import AlertIn, AlertOut, ActuatorCommand, SubscriptionOut
from services import dashboard_service, alert_service, actuator_service

# --- Helper: Map User Team to Engine Types for Dashboard ---
def _get_team_domains(team: Team) -> list[str]:
    if team == Team.ENERGY:
        return ["energy"]
    if team == Team.EHS:
        return ["water", "air"]
    return []

# ── Dashboard ─────────────────────────────────────────────────────────────
dash = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@dash.get("/resident")
async def resident_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.RESIDENT, Role.SMART_USER)),
):
    subs = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()
    if not subs:
        return {"summary": {}, "message": "No subscriptions yet"}

    zone_ids     = list({z for s in subs for z in json.loads(s.zone_ids)})
    engine_types = list({e for s in subs for e in json.loads(s.engine_types)})

    data = await dashboard_service.get_resident_dashboard(zone_ids, engine_types)

    # Attach in-app alerts (zone-filtered)
    alerts = (
        db.query(Alert)
        .filter(Alert.zone_id.in_(zone_ids), Alert.acknowledged == False)
        .order_by(Alert.created_at.desc())
        .limit(10)
        .all()
    )
    data["active_alerts"] = [
        {"id": a.id, "severity": a.severity.value, "message": a.message,
         "zone_id": a.zone_id, "domain": a.domain, "created_at": str(a.created_at)}
        for a in alerts
    ]
    return data


@dash.get("/analyst")
async def analyst_dashboard(
    current_user: User = Depends(require_role(Role.ANALYST, Role.MANAGER)),
):
    # Team Isolation: Only fetch data for the user's team domain
    domains = _get_team_domains(current_user.team)
    return await dashboard_service.get_analyst_dashboard(domains)


@dash.get("/analyst/timeseries")
async def analyst_timeseries(
    node_id: str,
    limit: int = 50,
    current_user: User = Depends(require_role(Role.ANALYST, Role.MANAGER)),
):
    """
    Returns time-series history for a specific node.
    Flutter LineChart uses this for real historical data (not SMA prediction).
    Proxies to: GET Middleware /history/{node_id}
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{settings.MIDDLEWARE_URL}/history/{node_id}",
                params={"limit": limit},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(502, f"Middleware unavailable: {e}")


@dash.get("/servicer")
async def servicer_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.SERVICER, Role.MANAGER)),
):
    # Servicers see their assignments; Managers see their team's assignments
    if current_user.role == Role.MANAGER:
        # Team Isolation: Only see assignments that match my team's domain
        allowed_domains = _get_team_domains(current_user.team)
        assignments = db.query(ServicerAssignment).filter(
            ServicerAssignment.domain.in_(allowed_domains)
        ).all()
    else:
        assignments = db.query(ServicerAssignment).filter(
            ServicerAssignment.servicer_id == current_user.id
        ).all()

    node_ids = [a.node_id for a in assignments]
    return await dashboard_service.get_servicer_dashboard(node_ids)


@dash.get("/manager/team")
def manager_team_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.MANAGER)),
):
    # Team Isolation: A manager only oversees people in their own team
    team_members = db.query(User).filter(
        User.team == current_user.team,
        User.role != Role.MANAGER # Don't list other managers in my team view
    ).all()
    
    result = []
    for member in team_members:
        assignments = db.query(ServicerAssignment).filter(
            ServicerAssignment.servicer_id == member.id
        ).all() if member.role == Role.SERVICER else []
        
        result.append({
            "user_id":    member.id,
            "full_name":  member.full_name,
            "email":      member.email,
            "role":       member.role.value,
            "is_active":  member.is_active,
            "assignments": [
                {"node_id": a.node_id, "domain": a.domain.value, "status": a.status.value}
                for a in assignments
            ],
        })
    return {"team": result, "total": len(result)}


@dash.get("/alerts")
def alert_feed(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.RESIDENT, Role.SMART_USER)),
):
    subs = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()
    zone_ids = list({z for s in subs for z in json.loads(z.zone_ids)})
    if not zone_ids:
        return {"alerts": []}
    
    alerts = (
        db.query(Alert)
        .filter(Alert.zone_id.in_(zone_ids), Alert.acknowledged == False)
        .order_by(Alert.created_at.desc())
        .limit(50)
        .all()
    )
    return {"alerts": [
        {"id": a.id, "severity": a.severity.value, "message": a.message,
         "zone_id": a.zone_id, "node_id": a.node_id, "domain": a.domain,
         "created_at": str(a.created_at)}
        for a in alerts
    ]}


# ── Alerts (internal + management) ────────────────────────────────────────
alerts_router = APIRouter(prefix="/alerts", tags=["Alerts"])

@alerts_router.post("/internal", status_code=202)
def receive_alert(
    body: AlertIn,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal API key")
    alert_service.process_alert(body, db)
    return {"status": "queued"}


@alerts_router.get("/my")
def my_alerts(
    acknowledged: bool = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns alerts scoped to current user's role + team + subscriptions."""
    alerts = alert_service.get_alerts_for_user(current_user, db, acknowledged, limit)
    return [
        {
            "id":           a.id,
            "alert_type":   a.alert_type,
            "severity":     a.severity.value,
            "message":      a.message,
            "zone_id":      a.zone_id,
            "domain":       a.domain,
            "node_id":      a.node_id,
            "rule_id":      a.rule_id,
            "acknowledged": a.acknowledged,
            "created_at":   str(a.created_at),
        }
        for a in alerts
    ]


@alerts_router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns count of unacknowledged alerts — used for notification badge."""
    alerts = alert_service.get_alerts_for_user(current_user, db, acknowledged=False, limit=200)
    return {"unread": len(alerts)}


@alerts_router.get("/history")
def alert_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.MANAGER, Role.ANALYST)),
):
    """Full alert history scoped to manager/analyst's team domain."""
    alerts = alert_service.get_alerts_for_user(current_user, db, limit=200)
    return alerts


@alerts_router.put("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged    = True
    alert.acknowledged_by = current_user.id
    db.commit()
    return {"status": "acknowledged", "alert_id": alert_id}


@alerts_router.put("/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.MANAGER, Role.SERVICER)),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.resolved    = True
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"status": "resolved", "alert_id": alert_id}


# ── Actuators ─────────────────────────────────────────────────────────────
actuators_router = APIRouter(prefix="/actuators", tags=["Actuators"])

@actuators_router.patch("/{node_id}/command")
async def send_command(
    node_id: str,
    body: ActuatorCommand,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Logic moved into actuator_service.send_actuator_command (team-scoped)
    await actuator_service.send_actuator_command(
        node_id=node_id, field=body.field, value=body.value,
        user=current_user, db=db,
    )
    return {"status": "command_sent", "node_id": node_id, "field": body.field, "value": body.value}


@actuators_router.get("/{node_id}/state")
async def get_node_state(
    node_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Analysts cannot view raw actuator state normally in our design
    if current_user.role == Role.ANALYST:
        raise HTTPException(status_code=403, detail="Access denied")
        
    import httpx
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{settings.MIDDLEWARE_URL}/history/{node_id}?limit=1")
            data = r.json()
            history = data.get("history", [])
            if not history:
                return {"node_id": node_id, "state": "UNKNOWN", "last_seen": None}
            rec = history[0]
            return {
                "node_id":   node_id,
                "state":     rec.get("state"),
                "health":    rec.get("health_status"),
                "payload":   rec.get("payload", {}),
                "last_seen": rec.get("timestamp"),
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Middleware unavailable: {e}")
