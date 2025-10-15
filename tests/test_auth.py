# tests->test_auth.py

def test_login_ok(client):
    r = client.post("/auth/login", data={"username": "admin", "password": "adminadmin"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert "access_token" in j and j["token_type"] == "bearer"

def test_status_requires_token(client):
    r = client.get("/status")  # sin token
    assert r.status_code == 401
