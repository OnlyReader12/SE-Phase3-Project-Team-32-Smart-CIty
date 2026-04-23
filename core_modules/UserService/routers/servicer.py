"""Servicer router: view and update own assignments."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import User, Role, ServicerAssignment
from core.dependencies import require_role
from schemas import AssignmentOut, AssignmentStatusUpdate, AssignmentNotesUpdate, AssignmentResolve

router = APIRouter(prefix="/servicer", tags=["Servicer"])

_ROLE = Depends(require_role(Role.SERVICER))


@router.get("/assignments", response_model=list[AssignmentOut])
def my_assignments(db: Session = Depends(get_db), current_user: User = _ROLE):
    return db.query(ServicerAssignment).filter(
        ServicerAssignment.servicer_id == current_user.id
    ).all()


@router.put("/assignments/{assignment_id}/status", response_model=AssignmentOut)
def update_status(
    assignment_id: str,
    body: AssignmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    a = db.query(ServicerAssignment).filter(
        ServicerAssignment.id == assignment_id,
        ServicerAssignment.servicer_id == current_user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    a.status = body.status
    a.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return a


@router.put("/assignments/{assignment_id}/notes", response_model=AssignmentOut)
def update_notes(
    assignment_id: str,
    body: AssignmentNotesUpdate,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    a = db.query(ServicerAssignment).filter(
        ServicerAssignment.id == assignment_id,
        ServicerAssignment.servicer_id == current_user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    a.notes = body.notes
    a.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return a

@router.put("/assignments/{assignment_id}/resolve", response_model=AssignmentOut)
def resolve_assignment(
    assignment_id: str,
    body: AssignmentResolve,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    from database.models import AssignmentStatus
    a = db.query(ServicerAssignment).filter(
        ServicerAssignment.id == assignment_id,
        ServicerAssignment.servicer_id == current_user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Enforce State Pattern transitions
    if a.status in [AssignmentStatus.RESOLVED, AssignmentStatus.CLOSED]:
        raise HTTPException(status_code=400, detail="Assignment is already resolved or closed")
        
    a.status = body.status
    a.notes = body.notes
    a.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return a
