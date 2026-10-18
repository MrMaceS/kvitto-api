from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tariff import Tariff

TARIFFS = [
    {"title": "basic", "price": 990000},
    {"title": "standard", "price": 1990000},
    {"title": "premium", "price": 2990000},
]


async def seed_tariffs(session: AsyncSession) -> None:
    """Создаёт тарифы, если их ещё нет. Идемпотентно."""
    for data in TARIFFS:
        result = await session.execute(select(Tariff).where(Tariff.title == data["title"]))
        if result.scalar_one_or_none() is None:
            session.add(Tariff(**data))
    await session.flush()
