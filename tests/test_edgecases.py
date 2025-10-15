# tests/test_edgecases.py
import builtins
import importlib
import sys
from fastapi.testclient import TestClient

def test__load_sync_engine_fallback_import_error():
    """
    Fuerza un ImportError SOLO al importar 'sync_engine', con un app/main recargado.
    Así garantizamos que se ejecute el except del loader y devuelva el fallback.
    """
    # 1) Asegura que no esté cacheado
    sys.modules.pop("sync_engine", None)

    # 2) Recarga app.main para tener app y _load_sync_engine sin parches previos
    import app.main as main_local
    importlib.reload(main_local)

    # 3) Parchea __import__ para fallar justo cuando pidan 'sync_engine'
    original_import = builtins.__import__
    def fake_import(name, *args, **kwargs):
        if name == "sync_engine":
            raise ImportError("boom")
        return original_import(name, *args, **kwargs)

    try:
        # Aplica el parche
        builtins.__import__ = fake_import

        # 4) Reaplica override de auth a la NUEVA app (si no, 401)
        main_local.app.dependency_overrides[main_local.require_auth] = lambda: "admin"

        # 5) Llama al endpoint
        client = TestClient(main_local.app)
        r = client.get("/status", headers={"Authorization": "Bearer valid_token_example"})
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        # Debe venir del Fallback de app.main._load_sync_engine
        assert body.get("system_health", "").startswith("fallback: ImportError")
    finally:
        # Limpieza: quita el parche y los overrides locales
        builtins.__import__ = original_import
        main_local.app.dependency_overrides.pop(main_local.require_auth, None)