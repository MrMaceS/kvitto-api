import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.tariff import Tariff
from app.seed import TARIFFS

TEST_DATABASE_URL = "postgresql+asyncpg://kvitto_test:kvitto_test@localhost:5433/kvitto_test"


@pytest.fixture(scope="function")
async def db_session():
    # 1. Создаем движок внутри фикстуры, чтобы он принадлежал текущему event loop
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 2. Создаем таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 3. Отдаем сессию в тест
    async with async_session_maker() as session:
        yield session
        await session.rollback()  # Гарантированно откатываем изменения

    # 4. Удаляем таблицы и закрываем движок после теста
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def tariffs(db_session: AsyncSession):
    for data in TARIFFS:
        db_session.add(Tariff(**data))
    await db_session.commit()

    result = await db_session.execute(select(Tariff))
    tariffs_list = result.scalars().all()
    return {t.title: t.id for t in tariffs_list}
