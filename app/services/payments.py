from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.tariff import Tariff
from app.schemas.payment import PaymentCreate, WebhookIn

# state machine
ALLOWED_TRANSITIONS = {
    PaymentStatus.PENDING: {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED},
    PaymentStatus.SUCCEEDED: {PaymentStatus.REFUNDED},
    PaymentStatus.FAILED: set(),
    PaymentStatus.REFUNDED: set(),
}


def calculate_installment_schedule(amount: int, months: int) -> list[int]:
    """
    Делит сумму в копейках на N месяцев так, чтобы сумма графика была ровно равна amount.
    Остаток от деления раскидывается по первым платежам.

    Пример: 1990000 / 3 = [663334, 663333, 663333]
    """
    base_payment = amount // months  # Базовый платёж
    remainder = amount % months  # Остаток

    # Первые `remainder` платежей будут на 1 копейку больше
    schedule = [base_payment + 1] * remainder + [base_payment] * (months - remainder)

    # Проверка: сумма графика должна быть ровно равна amount
    assert sum(schedule) == amount, f"Schedule sum {sum(schedule)} != amount {amount}"

    return schedule


async def get_tariff_or_404(session: AsyncSession, tariff_id: int) -> Tariff:
    """Получает тариф или возвращает 404."""
    result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
    tariff = result.scalar_one_or_none()
    if tariff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Tariff {tariff_id} not found"
        )
    return tariff


def apply_promo_code(price: int, promo_code: str | None) -> tuple[int, int]:
    """
    Применяет промокод к цене. Возвращает (final_price, discount).

    Если промокод неизвестный — выбрасывает 422.
    """
    if promo_code is None:
        return price, 0

    if promo_code.upper() != settings.promo_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown promo code: {promo_code}",
        )

    discount = int(price * settings.promo_discount_percent / 100)
    final_price = price - discount
    return final_price, discount


async def create_payment(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str | None
) -> tuple[Payment, bool]:
    """
    Создаёт платёж. Возвращает (payment, is_new).

    Если idempotency_key передан и платёж с таким ключом уже есть —
    возвращает существующий платёж с is_new=False.
    """
    if idempotency_key:
        result = await session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        existing_payment = result.scalar_one_or_none()
        if existing_payment:
            return existing_payment, False

    # Получаем тариф
    tariff = await get_tariff_or_404(session, data.tariff_id)

    final_price, discount = apply_promo_code(tariff.price, data.promo_code)

    # Создаём платёж
    payment = Payment(
        idempotency_key=idempotency_key,
        tariff_id=tariff.id,
        amount=final_price,
        discount=discount,
        email=data.email,
        method=data.method,
        status=PaymentStatus.PENDING,  # Явно ставим статус
    )

    # Если рассрочка — считаем график
    if data.method == PaymentMethod.INSTALLMENT:
        assert data.installment_months is not None
        payment.installment_months = data.installment_months
        payment.schedule = calculate_installment_schedule(final_price, data.installment_months)

    session.add(payment)
    await session.flush()

    return payment, True


async def get_payment_or_404(session: AsyncSession, payment_id: int) -> Payment:
    """Получает платёж или возвращает 404."""
    result = await session.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Payment {payment_id} not found"
        )
    return payment


def validate_status_transition(current_status: PaymentStatus, new_status: PaymentStatus) -> None:
    """
    Проверяет, разрешён ли переход из current_status в new_status.
    Если нет — выбрасывает 409 Conflict.
    """
    if new_status not in ALLOWED_TRANSITIONS[current_status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"error": "invalid transition"}
        )


async def update_payment_status(session: AsyncSession, payment_id: int, data: WebhookIn) -> Payment:
    """
    Обновляет статус платежа через вебхук.

    Проверяет:
    - Платёж существует (404 если нет)
    - Переход разрешён (409 если нет)
    """
    payment = await get_payment_or_404(session, payment_id)

    # Проверяем переход
    validate_status_transition(payment.status, data.status)

    # Обновляем статус
    payment.status = data.status
    await session.flush()

    return payment
