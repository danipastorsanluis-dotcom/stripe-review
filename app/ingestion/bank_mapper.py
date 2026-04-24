from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional

import pandas as pd

from app.core.utils import safe_decimal
from app.domain.models import BankTransaction


PAYOUT_REGEX = re.compile(
    r"\b(po_[A-Za-z0-9_\-]+|payout[_\-]?[A-Za-z0-9_\-]+)\b",
    re.IGNORECASE,
)


def _strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(c)
    )


def _normalize_column_name(value: str) -> str:
    return (
        _strip_accents(str(value))
        .replace("\ufeff", "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace(".", "")
        .replace("(", "")
        .replace(")", "")
        .replace("__", "_")
    )


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={col: _normalize_column_name(col) for col in df.columns})


def _pick_first_present(row, candidates):
    for name in candidates:
        if name in row.index:
            value = row.get(name)
            if pd.notna(value) and str(value).strip() not in {"", "nan", "None", "NULL"}:
                return value
    return None


def _parse_date(value) -> datetime:
    if value is None or str(value).strip() == "":
        raise ValueError("Fecha bancaria vacía")

    if isinstance(value, datetime):
        return value

    try:
        ts = pd.to_datetime(value, dayfirst=True, errors="raise")
        if pd.isna(ts):
            raise ValueError
        return ts.to_pydatetime()
    except Exception:
        pass

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    raise ValueError(f"Fecha bancaria inválida: {value}")


def _normalize_currency(value) -> str:
    if value is None or str(value).strip() == "":
        return "EUR"
    return str(value).strip().upper()


def _extract_payout_hint(reference: str, description: str) -> Optional[str]:
    haystack = f"{reference} {description}".strip()
    if not haystack:
        return None
    match = PAYOUT_REGEX.search(haystack)
    if not match:
        return None
    return match.group(1)


BANK_DATE_COLUMNS = [
    "booked_at",
    "date",
    "booking_date",
    "fecha",
    "fecha_operacion",
    "fecha_operación",
    "fecha_valor",
    "fecha_contable",
    "f_operacion",
    "f_operación",
    "f_valor",
    "operation_date",
    "transaction_date",
    "posting_date",
    "value_date",
]

BANK_AMOUNT_COLUMNS = [
    "amount",
    "importe",
    "importe_eur",
    "net",
    "monto",
    "cargo_abono",
    "importe_movimiento",
]

BANK_CURRENCY_COLUMNS = [
    "currency",
    "moneda",
    "divisa",
]

BANK_DESC_COLUMNS = [
    "description",
    "concepto",
    "descripcion",
    "descripción",
    "details",
    "detalle",
    "movimiento",
    "mas_datos",
    "más_datos",
    "observaciones",
]

BANK_REF_COLUMNS = [
    "reference",
    "referencia",
    "memo",
    "movement_reference",
    "bank_reference",
    "n_ref",
    "n_referencia",
    "referencia_bancaria",
]

BANK_ID_COLUMNS = [
    "id",
    "transaction_id",
    "movement_id",
    "bank_transaction_id",
    "numero_movimiento",
    "num_movimiento",
]

BANK_PAYOUT_COLUMNS = [
    "payout_id",
    "stripe_payout_id",
    "automatic_payout_id",
]


def map_bank_dataframe_to_transactions(df: pd.DataFrame) -> list[BankTransaction]:
    normalized = _normalize_dataframe_columns(df.copy())
    transactions: list[BankTransaction] = []

    for idx, row in normalized.iterrows():
        booked_raw = _pick_first_present(row, BANK_DATE_COLUMNS)
        if booked_raw is None:
            continue

        amount_raw = _pick_first_present(row, BANK_AMOUNT_COLUMNS)
        if amount_raw is None:
            continue

        booked_at = _parse_date(booked_raw)
        amount = safe_decimal(amount_raw)
        currency = _normalize_currency(_pick_first_present(row, BANK_CURRENCY_COLUMNS))

        description_parts = []
        desc1 = _pick_first_present(row, BANK_DESC_COLUMNS)
        if desc1:
            description_parts.append(str(desc1).strip())

        reference = str(_pick_first_present(row, BANK_REF_COLUMNS) or "").strip()

        description = " | ".join(part for part in description_parts if part)
        payout_hint = _pick_first_present(row, BANK_PAYOUT_COLUMNS)
        payout_id_hint = (
            str(payout_hint).strip()
            if payout_hint is not None
            else _extract_payout_hint(reference, description)
        )

        tx_id = str(_pick_first_present(row, BANK_ID_COLUMNS) or f"bank_{idx + 1}").strip()

        transactions.append(
            BankTransaction(
                id=tx_id,
                booked_at=booked_at,
                amount=amount,
                currency=currency,
                description=description,
                reference=reference,
                payout_id_hint=payout_id_hint or None,
            )
        )

    return transactions