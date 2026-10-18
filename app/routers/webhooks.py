import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.config import settings
from app.database import get_db
from app.schemas.payment import WebhookIn
from app.services.payments import update_payment_status

router = APIRouter()


async def verify_webhook_signature(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    """Зависимость для проверки HMAC-SHA256 подписи вебхука."""
    if not x_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Signature header"
        )

    # Читаем сырое тело запроса
    body = await request.body()

    # Вычисляем ожидаемую подпись
    expected_signature = hmac.new(
        settings.webhook_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    # защита от timing attacks
    if not hmac.compare_digest(expected_signature, x_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


@router.post("/bank")
async def bank_webhook(
    data: WebhookIn,
    request: Request,
    session=Depends(get_db),
    _=Depends(verify_webhook_signature),
):
    """
    POST /webhooks/bank

    Требует заголовок X-Signature с HMAC-SHA256(body, WEBHOOK_SECRET).
    - 200 { result: "ok" } — статус успешно обновлён
    - 401 — отсутствует или неверная подпись
    - 404 — платёж не найден
    - 409 { error: "invalid transition" } — запрещённый переход
    """
    await update_payment_status(session, data.payment_id, data)
    return {"result": "ok"}
