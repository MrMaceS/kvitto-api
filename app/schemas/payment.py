from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator
from app.models.payment import PaymentMethod, PaymentStatus


class PaymentCreate(BaseModel):
    tariff_id: int
    email: EmailStr
    method: PaymentMethod
    installment_months: int | None = None
    promo_code: str | None = None

    @field_validator("promo_code", mode="before")
    @classmethod
    def normalize_promo(cls, v: str | None) -> str | None:
        return v.upper() if isinstance(v, str) else v

    @field_validator("installment_months")
    @classmethod
    def validate_months(cls, v: int | None, info) -> int | None:
        method = info.data.get("method")
        if method == PaymentMethod.INSTALLMENT:
            if v not in (3, 6, 12):
                raise ValueError("installment_months must be 3, 6 or 12")
        else:
            if v is not None:
                raise ValueError("installment_months must be None for non-installment methods")
        return v


class PaymentOut(BaseModel):
    id: int
    status: PaymentStatus
    tariff_id: int
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookIn(BaseModel):
    payment_id: int
    status: PaymentStatus
