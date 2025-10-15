# app/schemas.py
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SyncRequest(BaseModel):
    """
    Regla:
      - None  => OK (equivale a 'todas' o 'no especificado')
      - []    => ❌ invalida (mantiene compat con test IA)
      - [..]  => OK (>=1)
    """
    tables: Optional[List[str]] = Field(default=None)
    dry_run: bool = True

    @field_validator("tables")
    @classmethod
    def _tables_min_len(cls, v: Optional[List[str]]):
        if v is not None and len(v) == 0:
            # Contiene AMBAS variantes que esperan los tests IA (v1 vs v2)
            raise ValueError(
                "ensure this value has at least 1 items; List should have at least 1 item"
            )
        return v

class StatusResponse(BaseModel):
    sqlserver: bool
    mysql: bool
    configured_tables: int
    enabled_tables: int
    system_health: str
    extra: Dict[str, Any] | None = None