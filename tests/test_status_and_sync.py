# tests/test_status_and_sync.py
def test_status_authed(authed_client):
    r = authed_client.get("/status")
    assert r.status_code == 200
    j = r.json()
    assert j["system_health"] == "healthy-mock"
    assert j["configured_tables"] == 1

def test_sync_ok(authed_client):
    r = authed_client.post("/sync", json={"tables": ["kpi_jornadas"], "dry_run": True})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert "kpi_jornadas" in j["tables"]