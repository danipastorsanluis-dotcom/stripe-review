from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation


def safe_decimal(value, default: str = "0.00") -> Decimal:
    """
    Convierte valores variados a Decimal de forma tolerante.
    Soporta:
    - None y strings vacíos
    - coma decimal
    - formatos mixtos tipo 1.234,56 o 1,234.56
    - símbolos de moneda
    - negativos con paréntesis: (123,45)
    """
    if value is None:
        return Decimal(default)

    text = str(value).strip()
    if not text:
        return Decimal(default)

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    for symbol in ("€", "$", "£"):
        text = text.replace(symbol, "")

    text = text.replace(" ", "")

    if "," in text and "." not in text:
        text = text.replace(",", ".")
    elif "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")

    try:
        result = Decimal(text)
        return -result if negative else result
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        return Decimal(default)


def parse_date_yyyy_mm_dd(value: str) -> datetime:
    return datetime.strptime(str(value).strip(), "%Y-%m-%d")


def clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def ensure_parent_dir(path: str) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)