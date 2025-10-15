# app/settings.py
from functools import lru_cache
from typing import List, Optional, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_NAME: str = "DataSync QA Adapter"

    # Auth / JWT
    JWT_SECRET: str = "dev_secret_change_me"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: Optional[str] = None
    ADMIN_PASSWORD_PLAIN: Optional[str] = "adminadmin"

    # DataSync
    DATASYNC_HOME: str = "./datasync-mock"

    # Rate limiting
    RATE_LIMIT_LOGIN: str = "3/minute"
    RATE_LIMIT_SYNC: str = "5/minute"

    # Seguridad / CORS / Whitelist (acepta str o lista en env)
    CORS_ORIGINS: Union[List[str], str] = ["*"]
    ALLOWED_TABLES: Union[List[str], str] = []

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

# ---- SlowAPI (Rate Limiting) ----
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

def init_rate_limiter(app):
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return limiter