# app/main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import os
import sys
import jwt

# ==== Instancia de la aplicación ====
app = FastAPI(title="DataSync QA Adapter")

# ==== Rutas para evitar 404 ruidosos ====
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return JSONResponse(status_code=204, content=None)

# ==== Salud ====
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

# ==== Auth (JWT) ====
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET", "dev_secret_change_me")

def _create_token(username: str) -> str:
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(hours=8)}
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")

def _require_auth(token: str = Depends(oauth2_scheme)) -> str:
    try:
        decoded = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        return decoded["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()) -> Dict[str, str]:
    # Credenciales demo (ajusta a tu gusto)
    if not (form.username == "admin" and form.password == "adminadmin"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _create_token(form.username)
    return {"access_token": token, "token_type": "bearer"}

# ==== Carga del motor (mock o real) ====
def _load_sync_engine():
    """
    Intenta cargar sync_engine desde DATASYNC_HOME/src.
    Por defecto usa ./datasync-mock/src/sync_engine.py (modo Mock).
    """
    home = os.environ.get("DATASYNC_HOME", "./datasync-mock")
    src = os.path.join(home, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import sync_engine  # type: ignore
        return sync_engine
    except Exception as e:
        # Fallback: evita que el servicio truene si no hay motor disponible
        class _Fallback:
            @staticmethod
            def get_sync_status():
                return {
                    "sqlserver": False,
                    "mysql": False,
                    "configured_tables": 0,
                    "enabled_tables": 0,
                    "system_health": f"fallback: {e.__class__.__name__}",
                }

            @staticmethod
            def sync_all_tables(specific_tables=None, dry_run=False):
                return None
        return _Fallback

# ==== Endpoints protegidos ====
@app.get("/status")
def status(_: str = Depends(_require_auth)) -> Dict[str, Any]:
    engine = _load_sync_engine()
    return engine.get_sync_status()

@app.post("/sync")
def sync(
    tables: Optional[List[str]] = None,
    dry_run: bool = True,
    _: str = Depends(_require_auth),
) -> Dict[str, Any]:
    # Validación simple de nombres de tabla
    if tables:
        bad = [t for t in tables if (";" in t or " " in t)]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid table names: {bad}")

    engine = _load_sync_engine()
    engine.sync_all_tables(specific_tables=tables, dry_run=dry_run)
    return {"ok": True, "tables": tables or [], "message": None}