import requests
import time

BASE_URL = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

def log(msg, ok=True):
    print(("✅ " if ok else "❌ ") + msg)

def check(endpoint, method="GET", **kwargs):
    url = BASE_URL + endpoint
    try:
        r = requests.request(method, url, timeout=30, **kwargs)
        return r
    except Exception as e:
        log(f"{endpoint} → {e}", ok=False)
        return None

def main():
    print("=== 🔍 Validando endpoints QA Dashboard ===")

    # 1️⃣ Health
    r = check("/health")
    if r and r.status_code == 200:
        log(f"/health OK → {r.json()}")
    else:
        log(f"/health FAIL ({r.status_code if r else 'error'})", ok=False)

    # 2️⃣ Status (usa token dev)
    tk = check("/internal/dev-token", method="POST")
    token = tk.json().get("access_token") if tk and tk.status_code == 200 else None
    if not token:
        log("/internal/dev-token FAIL (sin token)", ok=False)
        return
    auth = {"Authorization": f"Bearer {token}"}

    r = check("/status", headers=auth)
    if r and r.status_code == 200:
        log(f"/status OK → {r.json()}")
    else:
        log(f"/status FAIL ({r.status_code})", ok=False)

    # 3️⃣ Ejecutar pruebas (pytest)
    print("⏳ Ejecutando pytest (esto tarda unos segundos)...")
    r = check("/qa/run-tests?mode=pytest", method="POST", headers=auth)
    if r and r.status_code == 200:
        js = r.json()
        log(f"/qa/run-tests OK → returncode={js.get('returncode')}, cov={js.get('coverage')}")
    else:
        log(f"/qa/run-tests FAIL ({r.status_code if r else 'error'})", ok=False)

    # Espera a que coverage.xml se genere
    time.sleep(3)

    # 4️⃣ Coverage summary
    r = check("/qa/coverage/summary", headers=auth)
    if r and r.status_code == 200:
        js = r.json()
        log(f"/qa/coverage/summary OK → {js}")
    else:
        log(f"/qa/coverage/summary FAIL ({r.status_code})", ok=False)

    # 5️⃣ Refresh mount htmlcov
    r = check("/qa/coverage/refresh", method="POST", headers=auth)
    if r and r.status_code == 200:
        log(f"/qa/coverage/refresh OK → {r.json()}")
    else:
        log(f"/qa/coverage/refresh FAIL ({r.status_code})", ok=False)

    # 6️⃣ Ver HTML coverage
    r = check("/htmlcov/index.html", headers=auth)
    if r and r.status_code == 200:
        log("/htmlcov/index.html OK (reporte visible)")
    else:
        log(f"/htmlcov/index.html FAIL ({r.status_code})", ok=False)

    print("=== ✅ Validación completa ===")

if __name__ == "__main__":
    main()