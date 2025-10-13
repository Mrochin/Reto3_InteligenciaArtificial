# datasync-mock/src/sync_engine.py
# Mock del motor de sincronización para pruebas sin BD reales.

from typing import List, Optional, Dict, Any

def get_sync_status() -> Dict[str, Any]:
    # Simula que ambas conexiones están operativas
    return {
        "sqlserver": True,
        "mysql": True,
        "configured_tables": 1,
        "enabled_tables": 1,
        "system_health": "healthy-mock"
    }

def sync_all_tables(specific_tables: Optional[List[str]] = None, dry_run: bool = False) -> None:
    # No realiza operaciones reales; simula trabajo y valida parámetros
    tables = specific_tables or ["kpi_jornadas"]
    if any((";" in t) or (" " in t) for t in tables):
        raise ValueError("Nombre de tabla inválido")
    # En entorno mock no hacemos nada más
    return None
