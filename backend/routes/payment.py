from fastapi import APIRouter, Depends, Cookie
from sqlalchemy.orm import Session
from utils.database import get_db
from services import auth
from controllers import payment
from schemas.payment import (
    BillingKeyRegisterRequest,
    PaymentConfirmRequest,
    TempOrderRequest,
    TempOrderResponse,
)

router = APIRouter(tags=["payment"])

@router.get("/me")
async def get_my_payment_info(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db)
):
    current_user = auth.authenticate_access_token(access_token)
    return payment.get_my_payment_info(current_user, db)


@router.post("/temp-order", response_model=TempOrderResponse)
async def create_temp_order(
    body: TempOrderRequest,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db)
):
    current_user = auth.authenticate_access_token(access_token)
    return await payment.create_temp_order(
        body=body,
        current_user=current_user,
        db=db
    )


@router.post("/confirm")
async def confirm_payment(
    body: PaymentConfirmRequest,
    db: Session = Depends(get_db)
):
    return await payment.confirm_payment(
        body,
        db
    )


@router.get("/credits/me")
def get_my_credit_balance(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db)
):
    current_user = auth.authenticate_access_token(access_token)
    return payment.get_my_credit_balance(current_user, db)


@router.post("/billing-keys")
def register_billing_key(
    body: BillingKeyRegisterRequest,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    current_user = auth.authenticate_access_token(access_token)
    return payment.register_billing_key(body, current_user, db)


@router.get("/billing-keys")
def list_billing_keys(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    current_user = auth.authenticate_access_token(access_token)
    return payment.list_billing_keys(current_user, db)
