from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from passlib.context import CryptContext

from app.core.config import SESSION_DURATION_HOURS


# Password hashing: bcrypt con salt por defecto.
# passlib gestiona el salt automáticamente y lo almacena dentro del hash.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(path, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def _table_columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_column(con: sqlite3.Connection, table_name: str, column_sql: str, column_name: str) -> None:
    if column_name not in _table_columns(con, table_name):
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def ensure_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT NOT NULL UNIQUE,
            expires_at_utc TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            plan_code TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',
            stripe_customer_id TEXT NOT NULL DEFAULT '',
            stripe_subscription_id TEXT NOT NULL DEFAULT '',
            max_clients INTEGER NOT NULL DEFAULT 1,
            max_runs_per_month INTEGER NOT NULL DEFAULT 3,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            nif TEXT NOT NULL DEFAULT '',
            default_chart TEXT NOT NULL DEFAULT 'pgc_pyme',
            default_account_sales TEXT NOT NULL DEFAULT '700',
            default_account_fees TEXT NOT NULL DEFAULT '626',
            default_account_refunds TEXT NOT NULL DEFAULT '708',
            default_account_bank TEXT NOT NULL DEFAULT '572',
            journal_code TEXT NOT NULL DEFAULT 'STR',
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at_utc TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            client_id INTEGER,
            input_path TEXT NOT NULL,
            detected_format TEXT NOT NULL,
            transactions_count INTEGER NOT NULL,
            payouts_count INTEGER NOT NULL,
            issues_count INTEGER NOT NULL,
            matched_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            issue_count INTEGER NOT NULL,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );
        """
    )
    _ensure_column(con, "runs", "user_id INTEGER", "user_id")
    _ensure_column(con, "runs", "client_id INTEGER", "client_id")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS run_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS run_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            severity TEXT NOT NULL,
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            payout_id TEXT,
            transaction_id TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """
    )
    con.commit()


def hash_password(password: str) -> str:
    """
    Hashea la contraseña con bcrypt. bcrypt genera salt propio y lo guarda
    dentro del hash resultante. No compatible con hashes antiguos sha256.
    """
    if not password:
        raise ValueError("La contraseña no puede estar vacía")
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verifica contraseña contra hash bcrypt. Si falla (p.ej. hash legacy sha256)
    devuelve False sin lanzar excepción.
    """
    if not password or not password_hash:
        return False
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:
        return False


def create_user(con: sqlite3.Connection, *, email: str, password: str, full_name: str = "") -> dict[str, Any]:
    now = utc_now_iso()
    cur = con.execute(
        """
        INSERT INTO users (email, password_hash, full_name, is_active, created_at_utc, updated_at_utc)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (email.strip().lower(), hash_password(password), full_name.strip(), now, now),
    )
    user_id = int(cur.lastrowid)
    con.execute(
        """
        INSERT INTO subscriptions (user_id, plan_code, status, max_clients, max_runs_per_month, created_at_utc, updated_at_utc)
        VALUES (?, 'free', 'active', 1, 3, ?, ?)
        """,
        (user_id, now, now),
    )
    con.commit()
    return get_user_by_id(con, user_id)


def get_user_by_email(con: sqlite3.Connection, email: str) -> dict[str, Any] | None:
    row = con.execute("SELECT * FROM users WHERE email = ? LIMIT 1", (email.strip().lower(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(con: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = con.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,)).fetchone()
    return dict(row) if row else None


def create_session(con: sqlite3.Connection, *, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS)).isoformat(timespec="seconds")
    con.execute(
        "INSERT INTO sessions (user_id, session_token, expires_at_utc, created_at_utc) VALUES (?, ?, ?, ?)",
        (user_id, token, expires, utc_now_iso()),
    )
    con.commit()
    return token


def get_user_by_session_token(con: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    row = con.execute(
        """
        SELECT u.*
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.session_token = ?
          AND s.expires_at_utc > ?
          AND u.is_active = 1
        LIMIT 1
        """,
        (token, utc_now_iso()),
    ).fetchone()
    return dict(row) if row else None


def delete_session(con: sqlite3.Connection, token: str) -> None:
    if not token:
        return
    con.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
    con.commit()


def delete_expired_sessions(con: sqlite3.Connection) -> int:
    """Limpieza de sesiones caducadas. Útil en tareas de mantenimiento."""
    cur = con.execute("DELETE FROM sessions WHERE expires_at_utc <= ?", (utc_now_iso(),))
    con.commit()
    return cur.rowcount


def list_clients(con: sqlite3.Connection, *, user_id: int) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT * FROM clients WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def create_client(
    con: sqlite3.Connection,
    *,
    user_id: int,
    name: str,
    nif: str = "",
    default_chart: str = "pgc_pyme",
    default_account_sales: str = "700",
    default_account_fees: str = "626",
    default_account_refunds: str = "708",
    default_account_bank: str = "572",
    journal_code: str = "STR",
) -> dict[str, Any]:
    now = utc_now_iso()
    cur = con.execute(
        """
        INSERT INTO clients (
            user_id, name, nif, default_chart,
            default_account_sales, default_account_fees,
            default_account_refunds, default_account_bank,
            journal_code, created_at_utc, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name.strip(),
            nif.strip(),
            default_chart.strip(),
            default_account_sales.strip(),
            default_account_fees.strip(),
            default_account_refunds.strip(),
            default_account_bank.strip(),
            journal_code.strip(),
            now,
            now,
        ),
    )
    con.commit()
    return get_client(con, client_id=int(cur.lastrowid), user_id=user_id)


def get_client(con: sqlite3.Connection, *, client_id: int, user_id: int) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT * FROM clients WHERE id = ? AND user_id = ? LIMIT 1",
        (client_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def update_client(con: sqlite3.Connection, *, client_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    current = get_client(con, client_id=client_id, user_id=user_id)
    if not current:
        return None
    updated = {**current, **payload}
    updated_at = utc_now_iso()
    con.execute(
        """
        UPDATE clients
        SET name = ?, nif = ?, default_chart = ?,
            default_account_sales = ?, default_account_fees = ?,
            default_account_refunds = ?, default_account_bank = ?,
            journal_code = ?, updated_at_utc = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            str(updated.get("name", current["name"])).strip(),
            str(updated.get("nif", current["nif"])).strip(),
            str(updated.get("default_chart", current["default_chart"])).strip(),
            str(updated.get("default_account_sales", current["default_account_sales"])).strip(),
            str(updated.get("default_account_fees", current["default_account_fees"])).strip(),
            str(updated.get("default_account_refunds", current["default_account_refunds"])).strip(),
            str(updated.get("default_account_bank", current["default_account_bank"])).strip(),
            str(updated.get("journal_code", current["journal_code"])).strip(),
            updated_at,
            client_id,
            user_id,
        ),
    )
    con.commit()
    return get_client(con, client_id=client_id, user_id=user_id)


def delete_client(con: sqlite3.Connection, *, client_id: int, user_id: int) -> bool:
    cur = con.execute("DELETE FROM clients WHERE id = ? AND user_id = ?", (client_id, user_id))
    con.commit()
    return cur.rowcount > 0


def get_subscription(con: sqlite3.Connection, *, user_id: int) -> dict[str, Any]:
    row = con.execute("SELECT * FROM subscriptions WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    if row:
        return dict(row)
    now = utc_now_iso()
    con.execute(
        "INSERT INTO subscriptions (user_id, plan_code, status, max_clients, max_runs_per_month, created_at_utc, updated_at_utc) VALUES (?, 'free', 'active', 1, 3, ?, ?)",
        (user_id, now, now),
    )
    con.commit()
    return get_subscription(con, user_id=user_id)


def update_subscription(con: sqlite3.Connection, *, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_subscription(con, user_id=user_id)
    merged = {**current, **payload}
    con.execute(
        """
        UPDATE subscriptions
        SET plan_code = ?, status = ?, stripe_customer_id = ?, stripe_subscription_id = ?,
            max_clients = ?, max_runs_per_month = ?, updated_at_utc = ?
        WHERE user_id = ?
        """,
        (
            merged.get("plan_code", current["plan_code"]),
            merged.get("status", current["status"]),
            merged.get("stripe_customer_id", current["stripe_customer_id"]),
            merged.get("stripe_subscription_id", current["stripe_subscription_id"]),
            int(merged.get("max_clients", current["max_clients"])),
            int(merged.get("max_runs_per_month", current["max_runs_per_month"])),
            utc_now_iso(),
            user_id,
        ),
    )
    con.commit()
    return get_subscription(con, user_id=user_id)


def insert_run(
    con: sqlite3.Connection,
    *,
    user_id: int,
    client_id: int | None,
    input_path: str,
    detected_format: str,
    transactions_count: int,
    payouts_count: int,
    issues_count: int,
    matched_count: int,
    warning_count: int,
    issue_count: int,
    notes: str = "",
) -> int:
    cur = con.execute(
        """
        INSERT INTO runs (
            created_at_utc, user_id, client_id, input_path, detected_format,
            transactions_count, payouts_count, issues_count, matched_count,
            warning_count, issue_count, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now_iso(),
            user_id,
            client_id,
            input_path,
            detected_format,
            transactions_count,
            payouts_count,
            issues_count,
            matched_count,
            warning_count,
            issue_count,
            notes,
        ),
    )
    con.commit()
    return int(cur.lastrowid)


def insert_artifact(con: sqlite3.Connection, *, run_id: int, artifact_type: str, file_path: str) -> None:
    con.execute(
        "INSERT INTO run_artifacts (run_id, artifact_type, file_path, created_at_utc) VALUES (?, ?, ?, ?)",
        (run_id, artifact_type, file_path, utc_now_iso()),
    )
    con.commit()


def insert_issues(con: sqlite3.Connection, *, run_id: int, issues: list[Any]) -> None:
    rows = [
        (
            run_id,
            getattr(issue, "severity", ""),
            getattr(issue, "code", ""),
            getattr(issue, "message", ""),
            getattr(issue, "payout_id", None),
            getattr(issue, "transaction_id", None),
            utc_now_iso(),
        )
        for issue in issues
    ]
    if rows:
        con.executemany(
            "INSERT INTO run_issues (run_id, severity, code, message, payout_id, transaction_id, created_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.commit()


def fetch_artifact_path(con: sqlite3.Connection, *, run_id: int, artifact_type: str, user_id: int) -> str | None:
    """
    Devuelve la ruta del artefacto SOLO si el run pertenece al user_id indicado.
    user_id es obligatorio: no se permiten llamadas sin contexto de usuario.
    Esto evita data leaks entre cuentas.
    """
    if not user_id or int(user_id) <= 0:
        return None

    row = con.execute(
        """
        SELECT ra.file_path
        FROM run_artifacts ra
        JOIN runs r ON r.id = ra.run_id
        WHERE ra.run_id = ?
          AND ra.artifact_type = ?
          AND r.user_id = ?
        ORDER BY ra.id DESC
        LIMIT 1
        """,
        (run_id, artifact_type, int(user_id)),
    ).fetchone()
    return str(row["file_path"]) if row else None


def fetch_recent_runs(con: sqlite3.Connection, *, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT * FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (int(user_id), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_runs_by_client(con: sqlite3.Connection, *, user_id: int, client_id: int, limit: int = 100) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT * FROM runs WHERE user_id = ? AND client_id = ? ORDER BY id DESC LIMIT ?",
        (int(user_id), int(client_id), limit),
    ).fetchall()
    return [dict(row) for row in rows]


def count_runs_in_current_month(con: sqlite3.Connection, *, user_id: int) -> int:
    """Cuenta runs del usuario en el mes UTC actual. Útil para enforcement de planes."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    row = con.execute(
        "SELECT COUNT(*) as c FROM runs WHERE user_id = ? AND created_at_utc >= ?",
        (int(user_id), month_start),
    ).fetchone()
    return int(row["c"]) if row else 0
