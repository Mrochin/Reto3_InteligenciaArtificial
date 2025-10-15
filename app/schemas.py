# app/schemas.py
from pydantic import BaseModel, Field, conlist
from typing import Optional, Dict, Any

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class SyncRequest(BaseModel):
    # Lista de tablas (opcional), si se envía debe tener al menos 1
    tables: Optional[conlist(str, min_length=1)] = Field(default=None)
    dry_run: bool = True

class StatusResponse(BaseModel):
    sqlserver: bool
    mysql: bool
    configured_tables: int
    enabled_tables: int
    system_health: str
    extra: Dict[str, Any] | None = None