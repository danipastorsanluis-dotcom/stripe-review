from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.errors import ValidationError
from app.ingestion.csv_reader import read_stripe_csv


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def _read_csv_with_fallbacks(path: str) -> pd.DataFrame:
    last_error = None

    for encoding in CSV_ENCODINGS:
        try:
            df = pd.read_csv(path, encoding=encoding)
            if len(df.columns) == 1 and any(sep in str(df.columns[0]) for sep in [";", "\t", "|"]):
                continue
            return df
        except Exception as exc:
            last_error = exc

    try:
        return read_stripe_csv(path)
    except Exception as exc:
        last_error = exc

    raise ValidationError(
        f"No se ha podido leer el CSV con las codificaciones soportadas: {last_error}"
    )


def _read_excel(path: str) -> pd.DataFrame:
    """
    Reutiliza el lector robusto del proyecto, que:
    - detecta Excel y CSV
    - prueba distintas filas de cabecera
    - normaliza columnas
    """
    try:
        return read_stripe_csv(path)
    except Exception as exc:
        raise ValidationError(f"No se ha podido leer el archivo Excel: {exc}") from exc


def _drop_fully_empty_rows_and_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return df

    cleaned = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    return cleaned


def _strip_column_names(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        renamed[col] = str(col).replace("\ufeff", "").strip()
    return df.rename(columns=renamed)


def prepare_dataframe(path: str) -> pd.DataFrame:
    if not path:
        raise ValidationError("No se ha proporcionado ruta de archivo")

    file_path = Path(path)
    if not file_path.exists():
        raise ValidationError(f"El archivo no existe: {path}")

    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        df = _read_csv_with_fallbacks(str(file_path))
    elif suffix in {".xlsx", ".xls"}:
        df = _read_excel(str(file_path))
    else:
        raise ValidationError("Formato no soportado. Usa CSV, XLSX o XLS")

    if df is None or df.empty:
        raise ValidationError("El archivo está vacío o no contiene datos válidos")

    df = _drop_fully_empty_rows_and_columns(df)
    df = _strip_column_names(df)

    if df.empty:
        raise ValidationError("El archivo solo contiene filas o columnas vacías")

    return df