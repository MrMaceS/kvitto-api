import asyncio
import hashlib
import hmac

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.payment import Payment, PaymentMethod
from app.schemas.payment import PaymentCreate
from app.services.payments import apply_promo_code, create_payment


def generate_signature(payload: dict) -> str:
    import json

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hmac.new(settings.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_promo_code_applied(client: AsyncClient, tariffs: dict):
    """Тест 1: Промокод применяется, регистр не важен."""
    standard_id = tariffs["standard"]

    # Без промокода
    response = await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "test@example.com", "method": "card"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 1990000
    assert data["discount"] == 0

    # С промокодом в верхнем регистре
    response = await client.post(
        "/payments",
        json={
            "tariff_id": standard_id,
            "email": "test2@example.com",
            "method": "card",
            "promo_code": "KVITTO10",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 1791000
    assert data["discount"] == 199000

    # С промокодом в нижнем регистре
    response = await client.post(
        "/payments",
        json={
            "tariff_id": standard_id,
            "email": "test3@example.com",
            "method": "card",
            "promo_code": "kvitto10",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 1791000
    assert data["discount"] == 199000


@pytest.mark.parametrize(
    ("price", "promo", "expected"),
    [
        (990000, "KVITTO10", (891000, 99000)),
        (1990000, "KVITTO10", (1791000, 199000)),
        (2990000, "KVITTO10", (2691000, 299000)),
        (1990000, None, (1990000, 0)),
        (999, "KVITTO10", (900, 99)),  # 99.9 копейки скидки округляются вниз до 99
    ],
)
def test_apply_promo_code_integer_math(monkeypatch, price: int, promo: str | None, expected: tuple):
    """Скидка считается целыми копейками: итог и скидка — int, вместе дают исходную цену."""
    monkeypatch.setattr(settings, "promo_discount_percent", 10)

    final_price, discount = apply_promo_code(price, promo)

    assert (final_price, discount) == expected
    assert type(final_price) is int and type(discount) is int
    assert final_price + discount == price


@pytest.mark.asyncio
async def test_installment_schedule(client: AsyncClient, tariffs: dict):
    """Тест 2: График рассрочки — сумма графика равна сумме к оплате."""
    standard_id = tariffs["standard"]

    for months in [3, 6, 12]:
        response = await client.post(
            "/payments",
            json={
                "tariff_id": standard_id,
                "email": f"test{months}@example.com",
                "method": "installment",
                "installment_months": months,
            },
        )
        assert response.status_code == 201
        data = response.json()

        # Проверяем, что сумма графика равна amount
        assert sum(data["schedule"]) == data["amount"], (
            f"Schedule sum {sum(data['schedule'])} != amount {data['amount']} for {months} months"
        )

        # Проверяем, что график содержит ровно `months` элементов
        assert len(data["schedule"]) == months


@pytest.mark.asyncio
async def test_installment_schedule_exact_values(client: AsyncClient, tariffs: dict):
    """График рассрочки: точные значения, в том числе от суммы после скидки."""
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariffs["standard"],
            "email": "exact@example.com",
            "method": "installment",
            "installment_months": 3,
        },
    )
    assert response.status_code == 201
    assert response.json()["schedule"] == [663334, 663333, 663333]

    # standard со скидкой: 1791000 / 12 = 149250 без остатка
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariffs["standard"],
            "email": "exact2@example.com",
            "method": "installment",
            "installment_months": 12,
            "promo_code": "kvitto10",
        },
    )
    data = response.json()
    assert data["amount"] == 1791000
    assert data["schedule"] == [149250] * 12

    # basic со скидкой на 6 месяцев: 891000 / 6 = 148500
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariffs["basic"],
            "email": "exact3@example.com",
            "method": "installment",
            "installment_months": 6,
            "promo_code": "KVITTO10",
        },
    )
    assert response.json()["schedule"] == [148500] * 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {},  # срок не передан вовсе
        {"installment_months": None},
        {"installment_months": 5},
        {"installment_months": 0},
    ],
)
async def test_installment_requires_valid_months(client: AsyncClient, tariffs: dict, extra: dict):
    """Для рассрочки срок обязателен и должен быть 3, 6 или 12 — иначе 422, а не 500."""
    response = await client.post(
        "/payments",
        json={
            "tariff_id": tariffs["standard"],
            "email": "m@example.com",
            "method": "installment",
            **extra,
        },
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.asyncio
async def test_idempotency_key(client: AsyncClient, tariffs: dict):
    """Тест 3: Повторный запрос с тем же Idempotency-Key не создаёт второй платёж."""
    standard_id = tariffs["standard"]

    payload = {"tariff_id": standard_id, "email": "test@example.com", "method": "card"}

    # Первый запрос
    response1 = await client.post(
        "/payments", json=payload, headers={"Idempotency-Key": "unique-key-123"}
    )
    assert response1.status_code == 201
    payment1 = response1.json()

    # Второй запрос с тем же ключом
    response2 = await client.post(
        "/payments", json=payload, headers={"Idempotency-Key": "unique-key-123"}
    )
    assert response2.status_code == 200  # Не 201, а 200
    payment2 = response2.json()

    # ID должен быть одинаковым, тело — тем же
    assert payment1["id"] == payment2["id"]
    assert payment1 == payment2

    # Другой ключ — другой платёж
    response3 = await client.post(
        "/payments", json=payload, headers={"Idempotency-Key": "another-key"}
    )
    assert response3.status_code == 201
    assert response3.json()["id"] != payment1["id"]

    # Запросы без ключа не объединяются
    no_key_1 = await client.post("/payments", json=payload)
    no_key_2 = await client.post("/payments", json=payload)
    assert no_key_1.status_code == no_key_2.status_code == 201
    assert no_key_1.json()["id"] != no_key_2.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_concurrent_requests(db_session: AsyncSession, tariffs: dict):
    """Параллельные запросы с одним ключом: один платёж, ни одной ошибки."""
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    data = PaymentCreate(
        tariff_id=tariffs["basic"], email="race@example.com", method=PaymentMethod.CARD
    )

    async def attempt() -> tuple[int, bool]:
        async with maker() as session:
            payment, is_new = await create_payment(session, data, "race-key")
            await session.commit()
            return payment.id, is_new

    results = await asyncio.gather(*[attempt() for _ in range(8)])

    assert len({payment_id for payment_id, _ in results}) == 1
    assert sum(1 for _, is_new in results if is_new) == 1

    count = await db_session.scalar(
        select(func.count()).select_from(Payment).where(Payment.idempotency_key == "race-key")
    )
    assert count == 1


@pytest.mark.asyncio
async def test_invalid_status_transition(client: AsyncClient, tariffs: dict):
    """Тест: Запрещённый переход статуса возвращает 409 и не меняет статус."""
    standard_id = tariffs["standard"]

    response = await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "test@example.com", "method": "card"}
    )
    assert response.status_code == 201
    payment_id = response.json()["id"]

    webhook_payload = {"payment_id": payment_id, "status": "refunded"}
    headers = {"X-Signature": generate_signature(webhook_payload)}

    response = await client.post("/webhooks/bank", json=webhook_payload, headers=headers)
    assert response.status_code == 409
    assert response.json() == {"error": "invalid_transition"}

    response = await client.get(f"/payments/{payment_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_payment_not_found(client: AsyncClient):
    """Тест 5: Запрос несуществующего платежа возвращает 404."""
    response = await client.get("/payments/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unknown_promo_code(client: AsyncClient, tariffs: dict):
    """Бонусный тест: Неизвестный промокод возвращает 422."""
    standard_id = tariffs["standard"]

    response = await client.post(
        "/payments",
        json={
            "tariff_id": standard_id,
            "email": "test@example.com",
            "method": "card",
            "promo_code": "UNKNOWN_CODE",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_allowed_status_transitions(client: AsyncClient, tariffs: dict):
    """Тест: Разрешённые переходы работают."""
    standard_id = tariffs["standard"]

    response = await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "test1@example.com", "method": "card"}
    )
    payment_id = response.json()["id"]

    # pending → succeeded
    payload1 = {"payment_id": payment_id, "status": "succeeded"}
    headers1 = {"X-Signature": generate_signature(payload1)}
    response = await client.post("/webhooks/bank", json=payload1, headers=headers1)
    assert response.status_code == 200

    response = await client.get(f"/payments/{payment_id}")
    assert response.json()["status"] == "succeeded"

    # succeeded → refunded
    payload2 = {"payment_id": payment_id, "status": "refunded"}
    headers2 = {"X-Signature": generate_signature(payload2)}
    response = await client.post("/webhooks/bank", json=payload2, headers=headers2)
    assert response.status_code == 200

    response = await client.get(f"/payments/{payment_id}")
    assert response.json()["status"] == "refunded"


@pytest.mark.asyncio
async def test_webhook_missing_signature(client: AsyncClient, tariffs: dict):
    """Вебхук без заголовка X-Signature возвращает 401."""
    standard_id = tariffs["standard"]
    response = await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "t@t.com", "method": "card"}
    )
    payment_id = response.json()["id"]

    response = await client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "succeeded"},
        # Без заголовка X-Signature
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_invalid_signature(client: AsyncClient, tariffs: dict):
    """Вебхук с неверной подписью возвращает 401."""
    standard_id = tariffs["standard"]
    response = await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "t@t.com", "method": "card"}
    )
    payment_id = response.json()["id"]

    response = await client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "succeeded"},
        headers={"X-Signature": "fake-signature-123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_payments_no_filters(client: AsyncClient, tariffs: dict):
    """GET /payments без фильтров возвращает все платежи."""
    standard_id = tariffs["standard"]

    # Создаём 2 платежа
    await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "user1@example.com", "method": "card"}
    )
    await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "user2@example.com", "method": "card"}
    )

    response = await client.get("/payments")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_list_payments_filter_by_email(client: AsyncClient, tariffs: dict):
    """GET /payments?email=... возвращает только платежи с этим email."""
    standard_id = tariffs["standard"]

    # Создаём платежи с разными email
    await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "alice@example.com", "method": "card"}
    )
    await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "bob@example.com", "method": "card"}
    )

    # Фильтруем по alice
    response = await client.get("/payments?email=alice@example.com")
    assert response.status_code == 200
    data = response.json()
    assert all(p["email"] == "alice@example.com" for p in data)


@pytest.mark.asyncio
async def test_list_payments_filter_by_status(client: AsyncClient, tariffs: dict):
    """GET /payments?status=... возвращает только платежи с этим статусом."""
    standard_id = tariffs["standard"]

    # Создаём платёж и меняем его статус на succeeded
    response = await client.post(
        "/payments", json={"tariff_id": standard_id, "email": "test@example.com", "method": "card"}
    )
    payment_id = response.json()["id"]

    payload = {"payment_id": payment_id, "status": "succeeded"}
    headers = {"X-Signature": generate_signature(payload)}
    await client.post("/webhooks/bank", json=payload, headers=headers)

    # Фильтруем по succeeded
    response = await client.get("/payments?status=succeeded")
    assert response.status_code == 200
    data = response.json()
    assert all(p["status"] == "succeeded" for p in data)


@pytest.mark.asyncio
async def test_list_payments_invalid_status(client: AsyncClient):
    """GET /payments?status=invalid возвращает 422."""
    response = await client.get("/payments?status=invalid_status")
    assert response.status_code == 422
