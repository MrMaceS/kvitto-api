from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator, model_validator

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

    @model_validator(mode="after")
    def validate_installment_months(self) -> "PaymentCreate":
        """Срок рассрочки обязателен для installment (3, 6, 12) и запрещён для остальных методов."""
        if self.method == PaymentMethod.INSTALLMENT:
            if self.installment_months not in (3, 6, 12):
                raise ValueError("installment_months must be 3, 6 or 12 for installment")
        elif self.installment_months is not None:
            raise ValueError("installment_months must be omitted for non-installment methods")
        return self


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
