from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import async_session, init_db
from app.routers import payments, tariffs, webhooks
from app.seed import seed_tariffs


@asynccontextmanager
async def lifespan(app: FastAPI):

    await init_db()

    async with async_session() as session:
        await seed_tariffs(session)
        await session.commit()
    yield


app = FastAPI(title="Kvitto API", version="1.0.0", lifespan=lifespan)

app.include_router(tariffs.router, prefix="/tariffs", tags=["tariffs"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])


@app.get("/health")
async def health():
    return {"status": "ok"}
