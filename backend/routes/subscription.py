from fastapi import APIRouter, Cookie, Depends
from sqlalchemy.orm import Session

from controllers import subscription
from schemas.subscription import PlanChangeClassifyRequest
from services import auth
from utils.database import get_db

router = APIRouter(tags=["subscriptions"])


@router.post("/change-plan")
def change_plan(
    body: PlanChangeClassifyRequest,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    current_user = auth.authenticate_access_token(access_token)
    return subscription.change_plan(body, current_user, db)


@router.post("/{subscription_id}/resume")
def resume_subscription(
    subscription_id: str,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    current_user = auth.authenticate_access_token(access_token)
    return subscription.resume_subscription(subscription_id, current_user, db)


@router.post("/plan-changes/{plan_change_id}/cancel")
def cancel_plan_change(
    plan_change_id: str,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    current_user = auth.authenticate_access_token(access_token)
    return subscription.cancel_plan_change(plan_change_id, current_user, db)
