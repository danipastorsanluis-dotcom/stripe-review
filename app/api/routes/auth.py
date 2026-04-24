from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.core.config import APP_DB_PATH, SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE, SESSION_DURATION_HOURS
from app.storage.db import (
    connect_db,
    create_session,
    create_user,
    delete_session,
    ensure_tables,
    get_user_by_email,
    get_user_by_session_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ==================== Rate limiting en memoria ====================
# Para MVP es suficiente. Si escalas a multi-worker o múltiples instancias,
# migrar a Redis. 5 intentos por IP/email en ventana de 5 minutos.

_RATE_WINDOW_SECONDS = 300
_RATE_MAX_ATTEMPTS = 5
_rate_lock = Lock()
_login_attempts: dict[str, list[float]] = defaultdict(list)

def _is_test_env() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("APP_ENV") == "testing"


def _check_and_record_attempt(key: str) -> bool:
    """
    Devuelve True si el intento puede continuar (no ha excedido el límite).
    Devuelve False si ha excedido el límite en la ventana.
    """
    now = time.time()
    with _rate_lock:
        attempts = _login_attempts[key]
        # purgar antiguos
        attempts[:] = [t for t in attempts if now - t < _RATE_WINDOW_SECONDS]
        if len(attempts) >= _RATE_MAX_ATTEMPTS:
            return False
        attempts.append(now)
        return True


def _clear_attempts(key: str) -> None:
    with _rate_lock:
        _login_attempts.pop(key, None)


# ==================== Modelos ====================

class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=128)


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        max_age=SESSION_DURATION_HOURS * 3600,
        path="/",
    )


# ==================== Endpoints ====================

@router.post("/register")
def register(payload: RegisterPayload, response: Response, request: Request):
    # Rate limit también en registro (evitar bots)
    client_ip = request.client.host if request.client else "unknown"
    if not _is_test_env():
        if not _check_and_record_attempt(f"register:{client_ip}"):
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos. Espera unos minutos antes de reintentar.",
            )

    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        if get_user_by_email(con, payload.email):
            raise HTTPException(status_code=409, detail="Ese email ya existe")
        try:
            user = create_user(
                con,
                email=payload.email,
                password=payload.password,
                full_name=payload.full_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        token = create_session(con, user_id=int(user["id"]))
    finally:
        con.close()

    _set_session_cookie(response, token)
    return {
        "ok": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
        },
    }


@router.post("/login")
def login(payload: LoginPayload, response: Response, request: Request):
    # Rate limit por IP + por email. Cualquiera de los dos bloquea.
    client_ip = request.client.host if request.client else "unknown"
    ip_key = f"login-ip:{client_ip}"
    email_key = f"login-email:{payload.email.lower()}"

    if not _is_test_env():
        if not _check_and_record_attempt(ip_key):
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos desde esta IP. Espera unos minutos.",
            )
        if not _check_and_record_attempt(email_key):
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos con este email. Espera unos minutos.",
            )

    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        user = get_user_by_email(con, payload.email)
        if not user or not verify_password(payload.password, str(user["password_hash"])):
            # Mismo mensaje siempre, para no filtrar si el email existe.
            raise HTTPException(status_code=401, detail="Credenciales inválidas")
        if not int(user.get("is_active", 1)):
            raise HTTPException(status_code=403, detail="Usuario desactivado")
        token = create_session(con, user_id=int(user["id"]))
    finally:
        con.close()

    # Login ok → limpiar contador de intentos
    if not _is_test_env():
        _clear_attempts(ip_key)
        _clear_attempts(email_key)

    _set_session_cookie(response, token)
    return {
        "ok": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
        },
    }


@router.post("/logout")
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    if session_token:
        con = connect_db(APP_DB_PATH)
        try:
            ensure_tables(con)
            delete_session(con, session_token)
        finally:
            con.close()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
    if not session_token:
        raise HTTPException(status_code=401, detail="No autenticado")
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        user = get_user_by_session_token(con, session_token)
    finally:
        con.close()
    if not user:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    return {
        "ok": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
        },
    }
