from __future__ import annotations

import unicodedata
import pandas as pd


BANK_REQUIRED_GROUPS = {
    "date": {
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
    },
    "amount": {
        "amount",
        "importe",
        "importe_eur",
        "net",
        "monto",
        "cargo_abono",
        "importe_movimiento",
    },
}


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


def validate_bank_dataframe(df: pd.DataFrame) -> str:
    print("BANK_VALIDATOR -> COLUMNAS:", list(df.columns))
    if df is None or df.empty:
        raise ValueError("El archivo bancario está vacío.")

    normalized_columns = {_normalize_column_name(col) for col in df.columns}

    for group_name, group_columns in BANK_REQUIRED_GROUPS.items():
        if not normalized_columns.intersection(group_columns):
            raise ValueError(
                f"El archivo bancario no contiene una columna válida para {group_name}."
            )

    reference_columns = {
        "reference",
        "referencia",
        "memo",
        "movement_reference",
        "bank_reference",
        "concepto",
        "descripcion",
        "descripción",
        "detalle",
        "details",
        "movimiento",
        "mas_datos",
        "más_datos",
        "observaciones",
    }

    normalized_reference_columns = {_normalize_column_name(c) for c in reference_columns}

    if normalized_columns.intersection(normalized_reference_columns):
        return "bank_statement_with_reference"

    return "bank_statement_basic"