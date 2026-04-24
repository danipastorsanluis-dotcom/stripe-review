from __future__ import annotations

import pandas as pd

from app.core.errors import ValidationError
from app.core.utils import safe_decimal


SUPPORTED_CURRENCY = None


def _normalize_column_name(value: str) -> str:
    return (
        str(value)
        .replace("\ufeff", "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        renamed[col] = _normalize_column_name(col)
    return df.rename(columns=renamed)


def _apply_aliases(df: pd.DataFrame) -> pd.DataFrame:
    alias_groups = {
        "id": ["id", "transaction_id", "balance_transaction_id", "source_id"],
        "payout_id": ["payout_id", "automatic_payout_id", "payout"],
        "type": ["type", "reporting_category", "transaction_type"],
        "amount": ["amount", "gross"],
        "fee": ["fee", "stripe_fee"],
        "net": ["net"],
        "currency": ["currency", "settlement_currency"],
        "created": ["created", "created_utc", "charge_created_utc", "available_on_utc", "available_on"],
        "description": ["description", "memo", "details"],
    }

    out = df.copy()

    for canonical, aliases in alias_groups.items():
        if canonical in out.columns:
            continue
        for alias in aliases:
            if alias in out.columns:
                out[canonical] = out[alias]
                break

    return out


def _is_blank(value) -> bool:
    text = str(value).strip()
    return text in ("", "nan", "None", "NONE", "NULL")


def _validate_decimal_field(value, field_name: str, row_idx: int) -> None:
    text = str(value).strip()
    if text in ("", "nan", "None", "NONE", "NULL"):
        raise ValidationError(f"Fila {row_idx}: {field_name} vacío")
    try:
        safe_decimal(value)
    except Exception as exc:
        raise ValidationError(f"Fila {row_idx}: {field_name} inválido ({value})") from exc


def _pick_first_present(row, candidates):
    for name in candidates:
        if name in row.index and not _is_blank(row[name]):
            return row[name]
    return None


def _has_columns(df: pd.DataFrame, required: set[str]) -> bool:
    return required.issubset(set(df.columns))


def _is_docs_payout_format(df: pd.DataFrame) -> bool:
    required = {
        "automatic_payout_id",
        "balance_transaction_id",
        "gross",
        "fee",
        "net",
        "reporting_category",
        "created",
        "currency",
        "description",
    }
    return _has_columns(df, required)


def _is_docs_balance_format(df: pd.DataFrame) -> bool:
    required = {
        "automatic_payout_id",
        "balance_transaction_id",
        "gross",
        "fee",
        "net",
        "reporting_category",
        "currency",
        "description",
    }
    if not _has_columns(df, required):
        return False

    created_candidates = {"charge_created_utc", "created_utc", "created"}
    return len(created_candidates.intersection(set(df.columns))) > 0


def _is_realistic_format(df: pd.DataFrame) -> bool:
    required = {
        "id",
        "type",
        "amount",
        "fee",
        "net",
        "currency",
        "created",
        "description",
    }
    return _has_columns(df, required)


def _is_legacy_format(df: pd.DataFrame) -> bool:
    required = {"id", "amount", "fee", "net", "description", "created"}
    return _has_columns(df, required)


def _validate_currency(row, idx: int, field_name: str = "currency") -> None:
    currency = str(row[field_name]).strip().upper()
    if currency in ("", "NAN", "NONE", "NULL"):
        raise ValidationError(f"Fila {idx}: {field_name} vacía")

    if SUPPORTED_CURRENCY and currency != SUPPORTED_CURRENCY:
        raise ValidationError(
            f"Fila {idx}: moneda no soportada ({currency}). Se esperaba {SUPPORTED_CURRENCY}"
        )


def _validate_legacy(df) -> None:
    for idx, row in df.iterrows():
        if _is_blank(row["id"]):
            raise ValidationError(f"Fila {idx}: id vacío")

        if _is_blank(row["description"]):
            raise ValidationError(f"Fila {idx}: description vacía")

        if _is_blank(row["created"]):
            raise ValidationError(f"Fila {idx}: created vacío")

        _validate_decimal_field(row["amount"], "amount", idx)
        _validate_decimal_field(row["fee"], "fee", idx)
        _validate_decimal_field(row["net"], "net", idx)


def _validate_realistic(df) -> None:
    for idx, row in df.iterrows():
        if _is_blank(row["id"]):
            raise ValidationError(f"Fila {idx}: id vacío")

        if _is_blank(row["type"]):
            raise ValidationError(f"Fila {idx}: type vacío")

        if _is_blank(row["created"]):
            raise ValidationError(f"Fila {idx}: created vacío")

        if _is_blank(row["description"]):
            raise ValidationError(f"Fila {idx}: description vacía")

        _validate_decimal_field(row["amount"], "amount", idx)
        _validate_decimal_field(row["fee"], "fee", idx)
        _validate_decimal_field(row["net"], "net", idx)

        _validate_currency(row, idx, "currency")


def _validate_docs_payout(df) -> None:
    for idx, row in df.iterrows():
        if _is_blank(row["balance_transaction_id"]):
            raise ValidationError(f"Fila {idx}: balance_transaction_id vacío")

        if _is_blank(row["automatic_payout_id"]):
            raise ValidationError(f"Fila {idx}: automatic_payout_id vacío")

        if _is_blank(row["created"]):
            raise ValidationError(f"Fila {idx}: created vacío")

        if _is_blank(row["description"]):
            raise ValidationError(f"Fila {idx}: description vacía")

        if _is_blank(row["reporting_category"]):
            raise ValidationError(f"Fila {idx}: reporting_category vacío")

        _validate_decimal_field(row["gross"], "gross", idx)
        _validate_decimal_field(row["fee"], "fee", idx)
        _validate_decimal_field(row["net"], "net", idx)

        _validate_currency(row, idx, "currency")


def _validate_docs_balance(df) -> None:
    for idx, row in df.iterrows():
        if _is_blank(row["balance_transaction_id"]):
            raise ValidationError(f"Fila {idx}: balance_transaction_id vacío")

        if _is_blank(row["automatic_payout_id"]):
            raise ValidationError(f"Fila {idx}: automatic_payout_id vacío")

        created_value = _pick_first_present(
            row,
            ["charge_created_utc", "created_utc", "created"],
        )
        if created_value is None:
            raise ValidationError(f"Fila {idx}: falta charge_created_utc/created_utc/created")

        if _is_blank(row["description"]):
            raise ValidationError(f"Fila {idx}: description vacía")

        if _is_blank(row["reporting_category"]):
            raise ValidationError(f"Fila {idx}: reporting_category vacío")

        _validate_decimal_field(row["gross"], "gross", idx)
        _validate_decimal_field(row["fee"], "fee", idx)
        _validate_decimal_field(row["net"], "net", idx)

        _validate_currency(row, idx, "currency")


def validate_stripe_dataframe(df) -> str:
    if df is None or df.empty:
        raise ValidationError("El CSV está vacío o no es válido")

    df = _normalize_dataframe_columns(df)
    df = _apply_aliases(df)

    if _is_docs_balance_format(df):
        _validate_docs_balance(df)
        return "docs_balance_change"

    if _is_docs_payout_format(df):
        _validate_docs_payout(df)
        return "docs_payout_reconciliation"

    if _is_realistic_format(df):
        _validate_realistic(df)
        return "realistic"

    if _is_legacy_format(df):
        _validate_legacy(df)
        return "legacy"

    raise ValidationError(
        "Formato CSV no soportado. "
        "No coincide con legacy, realistic, docs_payout_reconciliation ni docs_balance_change. "
        f"Columnas detectadas: {list(df.columns)}"
    )