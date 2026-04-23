"""Manager router: team management + node assignments."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

from database.db import get_db
from database.models import User, Role, Team, ServicerAssignment, AssignmentStatus
from core.security import hash_password
from core.dependencies import require_role
from core.config import settings
from schemas import CreateUserRequest, UserOut, AssignmentCreate, AssignmentOut, AssignmentStatusUpdate, AssignmentNotesUpdate

router = APIRouter(prefix="/manager", tags=["Manager"])

_ROLE = Depends(require_role(Role.MANAGER))
_ALLOWED_CREATE_ROLES = {Role.ANALYST, Role.SERVICER}


@router.post("/create-user", response_model=UserOut, status_code=201)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    if body.role not in _ALLOWED_CREATE_ROLES:
        raise HTTPException(status_code=400, detail="Managers can only create ANALYST or SERVICER accounts")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        team=current_user.team,   # BUG FIX: inherit manager's team
        phone_number=body.phone_number,
        created_by=current_user.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/team", response_model=list[UserOut])
def list_team(db: Session = Depends(get_db), current_user: User = _ROLE):
    """List all non-manager users in the same team as this manager."""
    return db.query(User).filter(
        User.team == current_user.team,
        User.role != Role.MANAGER,
        User.is_active == True,
    ).all()


@router.get("/nodes")
async def browse_team_nodes(current_user: User = _ROLE):
    """
    Returns all live nodes belonging to this manager's team domain.
    Proxies to Middleware /domain/{domain}.
    """
    from routers.nodes import _fetch_domain, TEAM_TO_DOMAINS
    domains = TEAM_TO_DOMAINS.get(current_user.team, [])
    all_nodes = []
    for domain in domains:
        all_nodes.extend(await _fetch_domain(domain))
    return {"nodes": all_nodes, "total": len(all_nodes)}


@router.put("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    user = db.query(User).filter(
        User.id == user_id, User.created_by == current_user.id
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found or not in your team")
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(
    body: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    # BUG FIX: Look up servicer by team membership, not created_by
    # (seeded users have created_by=None so created_by check always fails)
    servicer = db.query(User).filter(
        User.id == body.servicer_id,
        User.team == current_user.team,
        User.role == Role.SERVICER,
    ).first()
    if not servicer:
        raise HTTPException(status_code=404, detail="Servicer not found in your team")

    assignment = ServicerAssignment(
        servicer_id=body.servicer_id,
        domain=body.domain,
        node_id=body.node_id,
        zone_id=body.zone_id,
        notes=body.notes,
        assigned_by=current_user.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(db: Session = Depends(get_db), current_user: User = _ROLE):
    return db.query(ServicerAssignment).filter(
        ServicerAssignment.assigned_by == current_user.id
    ).all()


@router.put("/assignments/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: str,
    body: AssignmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    a = db.query(ServicerAssignment).filter(
        ServicerAssignment.id == assignment_id,
        ServicerAssignment.assigned_by == current_user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    a.status = body.status
    a.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return a
