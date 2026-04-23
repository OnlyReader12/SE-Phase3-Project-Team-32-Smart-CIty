"""Resident router: subscription CRUD."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import User, Subscription, Role
from core.dependencies import require_role
from schemas import SubscriptionCreate, SubscriptionOut

router = APIRouter(prefix="/resident", tags=["Resident"])

_ROLE = Depends(require_role(Role.RESIDENT))


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
def create_subscription(
    body: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    sub = Subscription(
        user_id=current_user.id,
        zone_ids=json.dumps(body.zone_ids),
        engine_types=json.dumps(body.engine_types),
        alert_in_app=body.alert_in_app,
        alert_sms=body.alert_sms,
        alert_email=body.alert_email,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return SubscriptionOut.from_orm_obj(sub)


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    subs = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()
    return [SubscriptionOut.from_orm_obj(s) for s in subs]


@router.put("/subscriptions/{sub_id}", response_model=SubscriptionOut)
def update_subscription(
    sub_id: str,
    body: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    sub = db.query(Subscription).filter(
        Subscription.id == sub_id, Subscription.user_id == current_user.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    sub.zone_ids = json.dumps(body.zone_ids)
    sub.engine_types = json.dumps(body.engine_types)
    sub.alert_in_app = body.alert_in_app
    sub.alert_sms = body.alert_sms
    sub.alert_email = body.alert_email
    db.commit()
    db.refresh(sub)
    return SubscriptionOut.from_orm_obj(sub)


@router.delete("/subscriptions/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: str,
    db: Session = Depends(get_db),
    current_user: User = _ROLE,
):
    sub = db.query(Subscription).filter(
        Subscription.id == sub_id, Subscription.user_id == current_user.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.delete(sub)
    db.commit()
