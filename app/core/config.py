from functools import lru_cache
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "fastapi-starter"
    API_V1_PREFIX: str = "/api/v1"
    
    # Auth configuration
    JWT_ACCESS_SECRET: str = "default_access_secret"
    JWT_REFRESH_SECRET: str = "default_refresh_secret"
    JWT_SECRET: str = "default_secret"
    JWT_ALGORITHM: str = "HS256"
    
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 10080

    # Database configuration
    DATABASE_URL: PostgresDsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/fastapi_starter"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db"


@lru_cache
def get_settings() -> Settings:
    """Return an application Settings singleton loaded from the environment."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
