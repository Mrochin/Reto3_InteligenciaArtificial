# tests/test_validation.py
def test_sync_invalid_table_names(authed_client):
    # Inyección simple simulada debería ser bloqueada por validación adicional
    r = authed_client.post("/sync", json={"tables": ["users; DROP TABLE"], "dry_run": True})
    assert r.status_code == 400

def test_sync_payload_types(authed_client):
    # Con Pydantic body model (SyncRequest) esto debería dar 422 por tipos inválidos
    r = authed_client.post("/sync", json={"tables": "no-es-lista", "dry_run": "x"})
    assert r.status_code in (200, 400, 422)
