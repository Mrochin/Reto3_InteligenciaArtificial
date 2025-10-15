# app/settings.py
from functools import lru_cache
from typing import List, Optional, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# ---- SlowAPI (Rate Limiting) ----
# Mantener estos imports arriba evita ruff E402. Además, funciona aunque SlowAPI no esté instalado.
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler  # type: ignore
    from slowapi.util import get_remote_address  # type: ignore
    from slowapi.errors import RateLimitExceeded  # type: ignore
except Exception:  # SlowAPI opcional
    Limiter = None  # type: ignore
    _rate_limit_exceeded_handler = None  # type: ignore
    get_remote_address = None  # type: ignore

    class RateLimitExceeded(Exception):  # type: ignore
        pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Si prefieres ignorar variables no declaradas, descomenta la línea de abajo:
        # extra="ignore",
    )

    # App
    APP_NAME: str = "DataSync QA Adapter"
    # Variables que tu CI/compose estaban inyectando y que antes no existían:
    APP_PORT: int = 8000
    HOST_DATASYNC_PATH: Optional[str] = "./datasync-mock"

    # Auth / JWT
    JWT_SECRET: str = "dev_secret_change_me"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: Optional[str] = None
    ADMIN_PASSWORD_PLAIN: Optional[str] = "adminadmin"

    # DataSync (ruta dentro del contenedor)
    DATASYNC_HOME: str = "./datasync-mock"

    # Rate limiting
    RATE_LIMIT_LOGIN: str = "3/minute"
    RATE_LIMIT_SYNC: str = "5/minute"

    # Seguridad / CORS / Whitelist (acepta str o lista en env)
    CORS_ORIGINS: Union[List[str], str] = ["*"]
    ALLOWED_TABLES: Union[List[str], str] = []

    # Dashboard QA (dev-only helpers)
    DASHBOARD_ENABLE_DEV: bool = True

    # IA / Generación de pruebas
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4o"
    MAX_ITERS: int = 3
    MAX_SOURCE_CHARS: int = 10_000

    @field_validator("CORS_ORIGINS", "ALLOWED_TABLES", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        """
        Permite en .env:
        - JSON: '["a","b"]'
        - CSV : 'a,b'
        - '*' : -> ["*"]
        """
        if v is None or isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            if s == "*":
                return ["*"]
            if s.startswith("["):
                import json
                try:
                    return json.loads(s)
                except Exception:
                    # si no parsea como JSON, cae a CSV
                    pass
            return [item.strip() for item in s.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def init_rate_limiter(app):
    """Registrar SlowAPI si está disponible; si no, devolver None sin romper la app."""
    if Limiter is None:
        return None
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return limiter