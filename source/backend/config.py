from pydantic_settings import BaseSettings
from pydantic import field_validator, Field
from typing import Optional
import os

class Settings(BaseSettings):
    # App
    APP_NAME: str = "GrantFlow Modern"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    RUN_LEGACY_STARTUP_IMPORTS: bool = False
    AUTOMATION_WORKER_ENABLED: bool = True
    AUTOMATION_CONCURRENCY: int = Field(default=2, ge=1, le=16)
    AUTOMATION_MAX_PENDING_PER_USER: int = Field(default=100, ge=1, le=10000)

    @field_validator('DEBUG', mode='before')
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, str) and value.lower() in {'release', 'production'}:
            return False
        return value

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    ANTHESIS_GFM_INTROSPECTION_SECRET: str = ""
    ANTHESIS_IDENTITY_URL: str = "http://127.0.0.1:5000/api/gfm/introspect"
    ANTHESIS_REVOKE_URL: str = "http://127.0.0.1:5000/api/gfm/revoke"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./grantflow_modern.db")
    LEGACY_GRANT_DB: str = os.getenv("LEGACY_GRANT_DB", "../grant_flow.db")
    LEGACY_USERS_JSON: str = os.getenv("LEGACY_USERS_JSON", "../users.json")

    # Ollama / AI
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "llama3.2")
    # Lab opt-in: load a cold model before starting the inference deadline.
    AI_PRELOAD_MODEL: bool = False
    AI_LOAD_TIMEOUT_SECONDS: int = Field(default=120, ge=1, le=180)
    AI_INFERENCE_TIMEOUT_SECONDS: int = Field(default=120, ge=1, le=180)
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # Redis (optional — falls back to in-memory)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3002",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]

    # File uploads
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_MB: int = 50
    # Operator-owned JSON manifest; never accept server filesystem paths from web clients.
    INGESTION_SOURCE_MANIFEST: str = ''
    INGESTION_STORAGE_DIR: str = 'private_documents'
    INGESTION_WORKER_REGISTRY: str = ''
    INGESTION_LOCAL_WORKER_ENABLED: bool = True

    # Playwright automation
    PLAYWRIGHT_HEADLESS: bool = True
    SCREENSHOT_DIR: str = os.getenv("SCREENSHOT_DIR", "automation_screenshots")
    AUTOMATION_TIMEOUT_MS: int = 30000

    # Default admin account (auto-created on fresh install)
    DEFAULT_ADMIN_USERNAME: Optional[str] = os.getenv("DEFAULT_ADMIN_USERNAME", None)
    DEFAULT_ADMIN_EMAIL: Optional[str] = os.getenv("DEFAULT_ADMIN_EMAIL", None)
    DEFAULT_ADMIN_PASSWORD: Optional[str] = os.getenv("DEFAULT_ADMIN_PASSWORD", None)
    DEFAULT_ADMIN_FULLNAME: Optional[str] = os.getenv("DEFAULT_ADMIN_FULLNAME", None)

    # Portal credentials (seeded from env at startup)
    GRANTS_GOV_USERNAME: Optional[str] = os.getenv("GRANTS_GOV_USERNAME")
    GRANTS_GOV_PASSWORD: Optional[str] = os.getenv("GRANTS_GOV_PASSWORD")
    GRANTS_GOV_WORKSPACE_USERNAME: Optional[str] = os.getenv("GRANTS_GOV_WORKSPACE_USERNAME")
    GRANTS_GOV_WORKSPACE_PASSWORD: Optional[str] = os.getenv("GRANTS_GOV_WORKSPACE_PASSWORD")
    SAM_GOV_USERNAME: Optional[str] = os.getenv("SAM_GOV_USERNAME")
    SAM_GOV_PASSWORD: Optional[str] = os.getenv("SAM_GOV_PASSWORD")
    JUSTGRANTS_USERNAME: Optional[str] = os.getenv("JUSTGRANTS_USERNAME")
    JUSTGRANTS_PASSWORD: Optional[str] = os.getenv("JUSTGRANTS_PASSWORD")
    FOUNDATION_CENTER_USERNAME: Optional[str] = os.getenv("FOUNDATION_CENTER_USERNAME")
    FOUNDATION_CENTER_PASSWORD: Optional[str] = os.getenv("FOUNDATION_CENTER_PASSWORD")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
