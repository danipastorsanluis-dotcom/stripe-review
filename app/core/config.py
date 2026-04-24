from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
STORAGE_DIR = str(Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "output")))
DEMO_FILES_DIR = Path(os.getenv("DEMO_FILES_DIR", "/app/demo_files"))

APP_DB_PATH = str(DATA_DIR / "app.sqlite3")

APP_NAME = os.getenv("APP_NAME", "StripeReview")
APP_ENV = os.getenv("APP_ENV", "development")
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_DEBUG = os.getenv("APP_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

WEB_DIR = BASE_DIR / "app" / "web"
STATIC_DIR = WEB_DIR / "static"
INDEX_HTML_PATH = WEB_DIR / "index.html"

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "stripe_review_session")
SESSION_DURATION_HOURS = int(os.getenv("SESSION_DURATION_HOURS", "24"))

# AUTH_REQUIRED: siempre True salvo que se desactive explícitamente EN DESARROLLO.
# En producción (APP_ENV != development) se fuerza a True independientemente del env.
_auth_env = os.getenv("AUTH_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTH_REQUIRED = True if APP_ENV != "development" else _auth_env

# Cookie secure: True en producción (requiere HTTPS). En desarrollo, False para facilitar testing local.
SESSION_COOKIE_SECURE = APP_ENV != "development"

# Billing simulado: permitir /billing/simulate-upgrade solo en desarrollo explícito.
# En producción este endpoint debe devolver 404/403 siempre.
BILLING_SIMULATION_ENABLED = (
    APP_ENV == "development"
    and os.getenv("ENABLE_BILLING_SIMULATION", "false").strip().lower() in {"1", "true", "yes", "on"}
)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER", "")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_PLUS = os.getenv("STRIPE_PRICE_PLUS", "")


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEMO_FILES_DIR.mkdir(parents=True, exist_ok=True)
