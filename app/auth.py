# app/auth.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.hash import bcrypt
import jwt

from app.settings import settings
from app.schemas import LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(plain, hashed)
    except Exception:
        return False

def authenticate_user(username: str, password: str) -> bool:
    if username != settings.ADMIN_USERNAME:
        return False
    # Prioriza HASH si existe; si no, usa password plano del .env
    if settings.ADMIN_PASSWORD_HASH:
        return verify_password(password, settings.ADMIN_PASSWORD_HASH)
    if settings.ADMIN_PASSWORD_PLAIN is not None:
        return password == settings.ADMIN_PASSWORD_PLAIN
    return False

def require_auth(token: str = Depends(oauth2_scheme)) -> str:
    try:
        decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return decoded["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@router.post("/login", response_model=LoginResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    if not authenticate_user(form.username, form.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(form.username)
    return LoginResponse(access_token=token)