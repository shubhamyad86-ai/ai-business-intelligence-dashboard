"""Optional local authentication with PBKDF2 password hashing and signed tokens."""
from __future__ import annotations
import base64, hashlib, hmac, os, secrets, time
from dotenv import load_dotenv
load_dotenv()
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from db.database import get_user

TOKEN_TTL = int(os.getenv("TOKEN_TTL_SECONDS", "28800"))
SECRET = os.getenv("AUTH_SECRET", "change-this-local-secret")
bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return base64.urlsafe_b64encode(salt + digest).decode()

def verify_password(password: str, encoded: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        salt, expected = raw[:16], raw[16:]
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def create_token(username: str, role: str) -> str:
    exp = int(time.time()) + TOKEN_TTL
    payload = f"{username}|{role}|{exp}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()

def decode_token(token: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        username, role, exp, sig = raw.split("|", 3)
        payload = f"{username}|{role}|{exp}"
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected) or int(exp) < int(time.time()):
            raise ValueError("invalid token")
        if not get_user(username):
            raise ValueError("unknown user")
        return {"username": username, "role": role}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(credentials.credentials)

def require_role(*roles: str):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dependency
