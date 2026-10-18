from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.database import async_session
from app.routers import payments, tariffs, webhooks
from app.seed import seed_tariffs
from app.services.payments import InvalidTransitionError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Схему БД создаёт Alembic (`alembic upgrade head`); при старте — только сидирование."""
    async with async_session() as session:
        await seed_tariffs(session)
        await session.commit()
    yield


app = FastAPI(title="Kvitto API", version="1.0.0", lifespan=lifespan)

app.include_router(tariffs.router, prefix="/tariffs", tags=["tariffs"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])


@app.exception_handler(InvalidTransitionError)
async def invalid_transition_handler(request: Request, exc: InvalidTransitionError) -> JSONResponse:
    """Запрещённый переход статуса: 409 с {"error": "invalid_transition"} на верхнем уровне."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "invalid_transition"}
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
