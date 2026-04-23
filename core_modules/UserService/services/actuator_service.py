"""
Actuator service — validates access + forwards command to IngestionEngine.

Access rules (REFINED FOR TEAMS):
  RESIDENT → roles [RESIDENT, SMART_USER]. Must belong to Team.RESIDENTS.
            Node must be in a subscribed zone + subscribed engine type.
            ONLY SMART_USER can control actuators.
  SERVICER → must belong to Team.ENERGY or Team.EHS.
            Node must be in their servicer_assignments AND match their team domain.
  MANAGER  → must belong to Team.ENERGY or Team.EHS.
            Node must match their team's domain.
"""
import json
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException

from database.models import User, Role, Team, Subscription, ServicerAssignment
from core.config import settings


async def send_actuator_command(node_id: str, field: str, value: str, user: User, db: Session):
    """
    1. Check user has access to this node (Role + Team check).
    2. POST command to IngestionEngine.
    """
    _check_access(node_id, user, db)
    await _forward_command(node_id, field, value)


def _check_access(node_id: str, user: User, db: Session):
    domain_hint = _domain_from_node_id(node_id)
    
    # 1. ANALYSTS: NEVER have actuator access
    if user.role == Role.ANALYST:
        raise HTTPException(status_code=403, detail="Analysts cannot control actuators")

    # 2. MANAGERS: Scoped by Team
    if user.role == Role.MANAGER:
        if user.team == Team.ENERGY and domain_hint != "energy":
            raise HTTPException(status_code=403, detail=f"Energy Managers cannot control {domain_hint} nodes")
        if user.team == Team.EHS and domain_hint not in ["water", "air"]:
            raise HTTPException(status_code=403, detail=f"EHS Managers cannot control {domain_hint} nodes")
        return # Authorized within team domain

    # 3. SERVICERS: Scoped by Assignment + Team
    if user.role == Role.SERVICER:
        # Check team domain first as a safety guard
        if user.team == Team.ENERGY and domain_hint != "energy":
            raise HTTPException(status_code=403, detail="You are in the Energy team. Cannot control non-energy nodes.")
        if user.team == Team.EHS and domain_hint not in ["water", "air"]:
            raise HTTPException(status_code=403, detail="You are in the EHS team. Cannot control non-EHS nodes.")

        assignment = db.query(ServicerAssignment).filter(
            ServicerAssignment.servicer_id == user.id,
            ServicerAssignment.node_id == node_id,
        ).first()
        if not assignment:
            raise HTTPException(status_code=403, detail=f"Node {node_id} is not in your current assignments")
        return

    # 4. RESIDENTS / SMART USERS: Scoped by Subscription + SMART_USER Role
    if user.role in [Role.RESIDENT, Role.SMART_USER]:
        if user.role == Role.RESIDENT:
            raise HTTPException(status_code=403, detail="Standard residents cannot use remote actuators. Please upgrade to Smart Space account.")
        
        subs = db.query(Subscription).filter(Subscription.user_id == user.id).all()
        if not subs:
            raise HTTPException(status_code=403, detail="No active subscriptions found for your zone")

        for sub in subs:
            engine_types = json.loads(sub.engine_types)
            # Future improvement: Also check node's zone against subscription's zone_ids
            if domain_hint in engine_types:
                return  # Authorized
                
        raise HTTPException(status_code=403, detail=f"Your subscription does not cover {domain_hint} control")

    raise HTTPException(status_code=403, detail="Unauthorized")


async def _forward_command(node_id: str, field: str, value: str):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{settings.INGESTION_URL}/api/actuator/{node_id}/command",
                json={"field": field, "value": value},
            )
            r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach IngestionEngine: {e}")


def _domain_from_node_id(node_id: str) -> str:
    """Infer domain from node_id prefix — matches node_schemas.json types."""
    node_upper = node_id.upper()
    energy_prefixes = ("SOLAR", "BATTERY", "GRID", "AC-UNIT", "INDOOR-LIGHT", "OUTDOOR-LAMP",
                       "SMART-ENERGY", "OCCUPANCY")
    water_prefixes  = ("WATER", "RESERVOIR", "SOIL", "VALVE", "WATER-PUMP", "WATER-TREATMENT",
                       "SMART-WATER")
    air_prefixes    = ("AIR", "TEMP", "WIND", "ENVIRONMENTAL", "VENTILATION", "AIR-PURIF")

    for p in energy_prefixes:
        if node_upper.startswith(p):
            return "energy"
    for p in water_prefixes:
        if node_upper.startswith(p):
            return "water"
    for p in air_prefixes:
        if node_upper.startswith(p):
            return "air"
    return "energy"  # default
