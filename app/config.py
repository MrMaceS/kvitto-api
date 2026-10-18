from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки БД"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://kvitto:kvitto@localhost:5432/kvitto"
    webhook_secret: str = "super-secret-webhook-key"
    promo_code: str = "KVITTO10"
    promo_discount_percent: int = 10


settings = Settings()
