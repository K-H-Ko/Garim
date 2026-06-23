from fastapi import HTTPException
from sqlalchemy.orm import Session
from schemas.payment import (
    BillingKeyRegisterRequest,
    PaymentConfirmRequest,
    TempOrderRequest
)

from services import billing, payment


async def create_temp_order(
    body: TempOrderRequest,
    current_user: dict,
    db: Session
):
    try:
        result = await payment.create_temp_order(
            db=db,
            user_id=current_user["id"],
            product_type=body.product_type,
            product_code=body.product_code,
            amount=body.amount
        )
        return {
            "orderId": result["payment_id"],
            "amount": result["amount"],
            "orderName": result["order_name"],
            "productType": result["product_type"],
            "productCode": result["product_code"]
        }
    except ValueError as ve:
        raise HTTPException(
            status_code=400,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )




async def confirm_payment(
    body: PaymentConfirmRequest,
    db: Session
):
    try:
        result = await payment.confirm_payment(
            db=db,
            payment_key=body.paymentKey,
            order_id=body.orderId,
            amount=body.amount
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

def get_my_payment_info(current_user: dict, db: Session):
    try:
        # services/payment.py의 함수 호출
        return payment.get_my_payment_info(
            db=db,
            user_id=current_user["id"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


def get_my_credit_balance(current_user: dict, db: Session):
    try:
        return payment.get_my_credit_balance(
            db=db,
            user_id=current_user["id"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def register_billing_key(
    body: BillingKeyRegisterRequest,
    current_user: dict,
    db: Session,
):
    try:
        result = billing.save_billing_key(
            db=db,
            user_id=current_user["id"],
            billing_key=body.billingKey,
            customer_key=body.customerKey,
            card_company=body.cardCompany,
            masked_card_number=body.maskedCardNumber,
            method_type=body.methodType,
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        db.rollback()
        raise


def list_billing_keys(current_user: dict, db: Session):
    try:
        return {
            "billing_keys": billing.list_billing_keys(
                db=db,
                user_id=current_user["id"],
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
