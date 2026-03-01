from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://library:library_secret@localhost:5432/tenant_library"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://library:library_secret@localhost:5432/tenant_library"
    REDIS_URL: str = "redis://localhost:6379/0"
    PII_HASH_SECRET: str = "change-me-in-production"
    OL_RATE_LIMIT_RPS: float = 3.0
    OL_REQUEST_TIMEOUT: float = 30.0

    model_config = {"env_file": ".env"}


settings = Settings()
