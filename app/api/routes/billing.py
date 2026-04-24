from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes.tools import get_current_user
from app.core.config import APP_DB_PATH
from app.storage.db import connect_db, count_runs_in_current_month, ensure_tables, get_subscription

router = APIRouter(prefix="/billing", tags=["billing"])


# Por ahora solo hay un plan: Free.
# Cuando el producto tenga tracción real (20+ usuarios activos con feedback positivo),
# se añadirán planes de pago con Stripe Checkout real y webhooks.
# Hasta entonces, mantener esto simple evita dead code y riesgo de abuso.
PLAN_FREE = {
    "code": "free",
    "name": "Gratis",
    "price_eur": 0,
    "max_clients": 5,
    "max_runs_per_month": 10,
    "description": "Gratis para siempre mientras el producto esté en fase pública inicial.",
}


@router.get("/plan")
def my_plan(current_user=Depends(get_current_user)):
    """Devuelve el plan actual y el uso en el mes."""
    user_id = int(current_user["id"])
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        sub = get_subscription(con, user_id=user_id)
        runs_this_month = count_runs_in_current_month(con, user_id=user_id)
    finally:
        con.close()

    return {
        "ok": True,
        "plan": PLAN_FREE,
        "usage": {
            "runs_this_month": runs_this_month,
            "runs_remaining_this_month": max(0, PLAN_FREE["max_runs_per_month"] - runs_this_month),
        },
        "subscription": sub,
    }
