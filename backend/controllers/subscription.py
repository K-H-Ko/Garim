from fastapi import HTTPException
from sqlalchemy.orm import Session

from schemas.subscription import PlanChangeClassifyRequest
from services import subscription as subscription_service


def change_plan(
    body: PlanChangeClassifyRequest,
    current_user: dict,
    db: Session,
):
    try:
        result = subscription_service.request_plan_change(
            db=db,
            user_id=current_user["id"],
            to_plan_id=body.to_plan_id,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        db.rollback()
        raise


def resume_subscription(
    subscription_id: str,
    current_user: dict,
    db: Session,
):
    try:
        result = subscription_service.resume_subscription(
            db=db,
            user_id=current_user["id"],
            subscription_id=subscription_id,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        db.rollback()
        raise


def cancel_plan_change(
    plan_change_id: str,
    current_user: dict,
    db: Session,
):
    try:
        result = subscription_service.cancel_scheduled_plan_change(
            db=db,
            user_id=current_user["id"],
            plan_change_id=plan_change_id,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        db.rollback()
        raise
