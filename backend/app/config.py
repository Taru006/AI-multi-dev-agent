"""
Centralized application configuration using Pydantic BaseSettings.
All values can be overridden via environment variables or .env file.
"""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_dev_agency"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Gemini API
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-pro"
    GEMINI_FLASH_MODEL: str = "gemini-1.5-flash"
    GEMINI_MAX_TOKENS: int = 8192
    GEMINI_TEMPERATURE: float = 0.7
    GEMINI_MAX_RETRIES: int = 3

    # GitHub
    GITHUB_TOKEN: str = ""
    GITHUB_ORG: str = ""

    # Docker Sandbox
    SANDBOX_IMAGE: str = "ai-dev-agency-sandbox:latest"
    SANDBOX_TIMEOUT: int = 60  # seconds
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_CPU_PERIOD: int = 100000
    SANDBOX_CPU_QUOTA: int = 50000  # 50% CPU

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # Agent settings
    AGENT_MAX_ITERATIONS: int = 10
    AGENT_MAX_RETRIES: int = 3
    TOKEN_BUDGET_PER_PROJECT: int = 500_000

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # File storage
    ARTIFACTS_DIR: str = "./artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
