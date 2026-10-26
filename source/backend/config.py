from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator, Field
from typing import Optional
import os

class Settings(BaseSettings):
    # App
    APP_NAME: str = "GrantFlow Modern"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    AUTH_MODE: str = "anthesis"
    SESSION_SECURE: bool = True
    SESSION_ACCESS_SECONDS: int = Field(default=900, ge=60, le=3600)
    SESSION_ABSOLUTE_SECONDS: int = Field(default=604800, ge=3600, le=604800)
    GFM_BOOTSTRAP_TOKEN: str = ""
    GFM_BOOTSTRAP_TOKEN_FILE: str = ""
    GFM_DATA_ROOT: str = "/var/data"
    GFM_REQUIRE_PERSISTENT_STORAGE: bool = True
    AI_ENABLED: bool = False
    AI_PROVIDER: str = 'ollama'
    ALAMBDA_CHAT_URL: str = 'https://api.alambda.com/api/chat'
    ALAMBDA_API_TOKEN: str = ''
    ALAMBDA_API_TOKEN_FILE: str = ''
    ALAMBDA_MODEL: str = ''
    GFM_MODEL_HOST: str = ""
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
    ANTHESIS_GFM_INTROSPECTION_SECRET_FILE: str = ""
    ANTHESIS_PLATFORM_ME_URL: str = ""
    ANTHESIS_EMAIL_SAFETY_BASE_URL: str = ""
    ANTHESIS_CA_BUNDLE: str = ""
    ANTHESIS_ALLOWED_HOSTS: list[str] = []
    PUBLIC_ORIGIN: str = ""

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./grantflow_modern.db")
    LEGACY_GRANT_DB: str = os.getenv("LEGACY_GRANT_DB", "../grant_flow.db")
    LEGACY_USERS_JSON: str = os.getenv("LEGACY_USERS_JSON", "../users.json")

    # Ollama / AI
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "llama3.2")
    # Lab opt-in: load a cold model before starting the inference deadline.
    AI_PRELOAD_MODEL: bool = False
    AI_LOAD_TIMEOUT_SECONDS: int = Field(default=120, ge=1, le=600)
    AI_INFERENCE_TIMEOUT_SECONDS: int = Field(default=120, ge=1, le=600)
    EXPECTED_MODEL_DIGEST: str = ""
    AI_CA_BUNDLE: str = ""
    AI_CLIENT_CERT_FILE: str = ""
    AI_CLIENT_KEY_FILE: str = ""
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

    @model_validator(mode='after')
    def validate_connected_trial(self):
        if self.AI_PROVIDER not in {'ollama', 'alambda'}:
            raise ValueError('Unknown AI provider')
        if self.AI_PROVIDER == 'alambda':
            from urllib.parse import urlsplit
            remote = urlsplit(self.ALAMBDA_CHAT_URL)
            if (remote.scheme != 'https' or remote.hostname != 'api.alambda.com'
                    or remote.port not in {None, 443} or remote.path != '/api/chat'
                    or remote.username or remote.password or remote.query or remote.fragment):
                raise ValueError('Alambda chat requires the approved HTTPS endpoint')
        if self.AUTH_MODE not in {'anthesis', 'standalone'}:
            raise ValueError('Unknown authentication mode')
        if self.AUTH_MODE == 'standalone':
            if not self.DATABASE_URL.startswith('sqlite+aiosqlite:///'):
                raise ValueError('Standalone sessions currently require the reviewed SQLite storage configuration')
            import re
            if self.GFM_MODEL_HOST:
                if not re.fullmatch(r'[A-Za-z0-9.-]+',self.GFM_MODEL_HOST):
                    raise ValueError('Invalid private model host')
                self.OLLAMA_URL='http://'+self.GFM_MODEL_HOST+':11434'
            if self.AI_ENABLED and self.AI_PROVIDER == 'ollama' and not re.fullmatch(r'[a-f0-9]{64}',self.EXPECTED_MODEL_DIGEST):
                raise ValueError('Approve an exact model digest before enabling AI')
            from urllib.parse import urlsplit
            public = urlsplit(self.PUBLIC_ORIGIN)
            if (not public.hostname or public.username or public.password or public.query or public.fragment
                    or public.path not in {'', '/'} or public.scheme not in {'http', 'https'}):
                raise ValueError('An explicit standalone public origin is required')
            if self.ENVIRONMENT == 'render-standalone' and (public.scheme != 'https' or not self.SESSION_SECURE
                    or self.DEBUG or self.RUN_LEGACY_STARTUP_IMPORTS or self.DEFAULT_ADMIN_PASSWORD or not self.GFM_REQUIRE_PERSISTENT_STORAGE):
                raise ValueError('Render requires secure standalone sessions and no legacy seeding')
            if self.ALLOWED_ORIGINS != [self.PUBLIC_ORIGIN.rstrip('/')]:
                raise ValueError('Standalone CORS must match its public origin')
            return self
        if self.ENVIRONMENT not in {'standalone-trial', 'production'}:
            return self
        from urllib.parse import urlsplit
        urls = [self.ANTHESIS_IDENTITY_URL, self.ANTHESIS_REVOKE_URL,
                self.ANTHESIS_PLATFORM_ME_URL, self.ANTHESIS_EMAIL_SAFETY_BASE_URL]
        for raw in urls:
            url = urlsplit(raw)
            if (url.scheme != 'https' or not url.hostname or url.hostname not in self.ANTHESIS_ALLOWED_HOSTS
                    or url.hostname in {'localhost', '127.0.0.1', 'host.docker.internal'}
                    or url.hostname.endswith('.invalid') or url.username or url.password or url.query or url.fragment):
                raise ValueError('Configure explicit approved HTTPS Anthesis endpoints before a connected trial')
        public = urlsplit(self.PUBLIC_ORIGIN)
        if (public.scheme != 'https' or not public.hostname or public.path not in {'', '/'}
                or public.query or public.fragment or public.username or public.password
                or public.hostname.endswith('.invalid')):
            raise ValueError('A public HTTPS origin is required')
        if self.ALLOWED_ORIGINS != [self.PUBLIC_ORIGIN.rstrip('/')]:
            raise ValueError('Trial CORS must contain only the explicit public origin')
        if self.RUN_LEGACY_STARTUP_IMPORTS or self.DEBUG or self.DEFAULT_ADMIN_PASSWORD:
            raise ValueError('Trial must disable legacy imports, debug and local credential seeding')
        if not self.ANTHESIS_GFM_INTROSPECTION_SECRET_FILE or self.ANTHESIS_GFM_INTROSPECTION_SECRET:
            raise ValueError('Trial identity service key must use a mounted secret file')
        import re
        if not re.fullmatch(r'[a-f0-9]{64}', self.EXPECTED_MODEL_DIGEST):
            raise ValueError('An approved model digest is required')
        model = urlsplit(self.OLLAMA_URL)
        if model.username or model.password or model.query or model.fragment or model.path not in {'', '/', '/api/chat'}:
            raise ValueError('Model URL must not contain credentials, query or an arbitrary path')
        if model.scheme != 'https' and not (model.scheme == 'http' and model.hostname == 'ollama'):
            raise ValueError('Use the private local model service or an HTTPS remote model endpoint')
        if model.scheme == 'https' and not all([self.AI_CA_BUNDLE, self.AI_CLIENT_CERT_FILE, self.AI_CLIENT_KEY_FILE]):
            raise ValueError('Remote model transport requires CA verification and mutual TLS')
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
        hide_input_in_errors = True


settings = Settings()
