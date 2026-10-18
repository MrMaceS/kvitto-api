from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tariff import Tariff
from app.schemas.tariff import TariffOut

router = APIRouter()


@router.get("", response_model=list[TariffOut])
async def list_tariffs(session: AsyncSession = Depends(get_db)):
    """GET /tariffs — возвращает список всех тарифов."""
    result = await session.execute(select(Tariff).order_by(Tariff.id))
    return result.scalars().all()
