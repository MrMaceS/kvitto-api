from fastapi import APIRouter, Depends, Header, Response, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.payment import PaymentCreate, PaymentOut
from app.services.payments import create_payment, get_payment_or_404

router = APIRouter()


@router.post(
    "",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment_endpoint(
    data: PaymentCreate,
    response: Response,
    session: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """
    POST /payments

    - 201 — платёж создан
    - 200 — платёж с таким Idempotency-Key уже существует (идемпотентность)
    """
    payment, is_new = await create_payment(session, data, idempotency_key)

    # Если платёж уже существовал — меняем статус ответа на 200
    if not is_new:
        response.status_code = status.HTTP_200_OK

    return payment


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: int,
    session: AsyncSession = Depends(get_db),
):
    """
    GET /payments/{id}

    - 200 — платёж найден
    - 404 — платёж не найден
    """
    return await get_payment_or_404(session, payment_id)


@router.get("", response_model=list[PaymentOut])
async def list_payments(
    email: str | None = Query(default=None, description="Фильтр по email (точное совпадение)"),
    status: str | None = Query(
        default=None, description="Фильтр по статусу: pending, succeeded, failed, refunded"
    ),
    session: AsyncSession = Depends(get_db),
):
    """
    GET /payments

    Возвращает список платежей с опциональными фильтрами:
    - email=user@example.com — точное совпадение по email
    - status=succeeded — фильтр по статусу

    Примеры:
    - GET /payments — все платежи
    - GET /payments?email=test@example.com — платежи конкретного пользователя
    - GET /payments?status=succeeded — все успешные платежи
    - GET /payments?email=test@example.com&status=succeeded — комбинация фильтров
    """
    from sqlalchemy import select
    from app.models.payment import Payment, PaymentStatus

    query = select(Payment)

    # Применяем фильтр по email
    if email:
        query = query.where(Payment.email == email)

    # Применяем фильтр по статусу
    if status:
        try:
            status_enum = PaymentStatus(status)
            query = query.where(Payment.status == status_enum)
        except ValueError:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=f"Invalid status: {status}. "
                f"Must be one of: pending, succeeded, failed, refunded",
            )

    result = await session.execute(query.order_by(Payment.created_at.desc()))
    return result.scalars().all()
