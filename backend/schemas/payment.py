from typing import Literal

from pydantic import BaseModel, Field


class PaymentConfirmRequest(BaseModel):
    paymentKey: str
    orderId: str
    amount: int


class TempOrderRequest(BaseModel):
    product_type: Literal["subscription", "credit"]
    product_code: str
    amount: int


class TempOrderResponse(BaseModel):
    orderId: str
    amount: int
    orderName: str
    productType: Literal["subscription", "credit"]
    productCode: str


class BillingKeyRegisterRequest(BaseModel):
    billingKey: str = Field(..., min_length=1)
    customerKey: str | None = None
    cardCompany: str | None = None
    maskedCardNumber: str | None = None
    methodType: Literal["card", "easy_pay", "account", "unknown"] = "unknown"
