import enum
from datetime import datetime
from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    CARD = "card"
    SBP = "sbp"
    INSTALLMENT = "installment"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))
    amount: Mapped[int]
    discount: Mapped[int] = mapped_column(Integer)  # Убрали default, ставим в коде
    email: Mapped[str] = mapped_column(String(255))

    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    installment_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
