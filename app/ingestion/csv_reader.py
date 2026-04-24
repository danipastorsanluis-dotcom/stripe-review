import csv
import os
from pathlib import Path

import pandas as pd

from app.core.errors import ValidationError


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia nombres de columnas:
    - quita BOM
    - quita espacios al inicio/fin
    - colapsa espacios internos
    """
    df.columns = [
        " ".join(str(col).replace("\ufeff", "").strip().split())
        for col in df.columns
    ]
    return df


def _is_bad_single_column(df: pd.DataFrame) -> bool:
    """
    Detecta cuando pandas ha leído toda la cabecera como una sola columna.
    """
    if df is None or df.empty:
        return False

    if len(df.columns) != 1:
        return False

    col = str(df.columns[0])
    return any(sep in col for sep in [",", ";", "\t", "|"])


def _score_bank_header(columns: list[str]) -> int:
    normalized = [
        " ".join(str(col).replace("\ufeff", "").strip().split()).lower()
        for col in columns
    ]

    keywords = {
        "fecha",
        "fecha operación",
        "fecha operacion",
        "fecha valor",
        "importe",
        "saldo",
        "concepto",
        "descripción",
        "descripcion",
        "movimiento",
        "movimientos",
        "referencia",
        "divisa",
        "moneda",
        "booking date",
        "value date",
        "amount",
        "details",
        "description",
    }

    score = 0

    for col in normalized:
        # Penaliza columnas vacías/automáticas
        if col.startswith("unnamed"):
            score -= 2
            continue

        # Suma por keywords bancarias
        for kw in keywords:
            if kw == col:
                score += 4
            elif kw in col:
                score += 2

        # Bonus si parece cabecera útil corta
        if len(col) > 0 and len(col) < 30:
            score += 0.5

    # Penaliza cuando casi todo son unnamed
    unnamed_count = sum(1 for col in normalized if col.startswith("unnamed"))
    if unnamed_count >= max(1, len(normalized) // 2):
        score -= 6

    # Bonus fuerte si aparecen varias columnas esperables juntas
    joined = " | ".join(normalized)
    expected_hits = 0
    for expected in ["fecha", "importe", "saldo"]:
        if expected in joined:
            expected_hits += 1
    if expected_hits >= 2:
        score += 6

    return score


def _try_read_excel(path: str) -> pd.DataFrame | None:
    for engine in ("openpyxl",):
        try:
            xls = pd.ExcelFile(path, engine=engine)

            for sheet_name in xls.sheet_names:
                best_df = None
                best_score = float("-inf")
                best_header_row = None

                for header_row in range(0, 12):
                    try:
                        df = pd.read_excel(
                            path,
                            engine=engine,
                            sheet_name=sheet_name,
                            header=header_row,
                        )
                        df = _normalize_columns(df)

                        if df is None or df.empty:
                            continue

                        score = _score_bank_header(list(df.columns))

                        print(f"HEADER_ROW={header_row} -> SCORE={score} -> COLS={list(df.columns)}")

                        if score > best_score:
                            best_score = score
                            best_df = df
                            best_header_row = header_row
                    except Exception:
                        continue

                if best_df is not None and not best_df.empty:
                    print(f"HEADER SELECCIONADO={best_header_row} -> COLS={list(best_df.columns)}")
                    return best_df

        except Exception:
            continue

    return None


def _try_read_csv_with_pandas(path: str, encoding: str, sep: str) -> pd.DataFrame | None:
    """
    Intenta leer como CSV normal con pandas.
    """
    try:
        df = pd.read_csv(
            path,
            encoding=encoding,
            sep=sep,
            engine="python",
            skip_blank_lines=True,
        )
        df = _normalize_columns(df)

        if df is None or df.empty:
            return None

        if _is_bad_single_column(df):
            return None

        return df
    except Exception:
        return None


def _try_read_csv_manual(path: str, encoding: str, delimiter: str) -> pd.DataFrame | None:
    """
    Fallback manual usando csv.reader.
    Esto arregla casos donde pandas deja todo en una sola columna.
    """
    try:
        with open(path, "r", encoding=encoding, newline="") as f:
            rows = list(csv.reader(f, delimiter=delimiter))

        if not rows:
            return None

        header = rows[0]
        data = rows[1:]

        if len(header) <= 1:
            return None

        df = pd.DataFrame(data, columns=header)
        df = _normalize_columns(df)

        if df.empty:
            return None

        return df
    except Exception:
        return None


def _detect_delimiter_from_text(path: str, encoding: str) -> str | None:
    """
    Intenta detectar delimitador leyendo la primera línea real.
    """
    try:
        with open(path, "r", encoding=encoding, newline="") as f:
            first_line = f.readline()

        if not first_line:
            return None

        candidates = [",", ";", "\t", "|"]
        counts = {sep: first_line.count(sep) for sep in candidates}

        best_sep = max(counts, key=counts.get)
        if counts[best_sep] == 0:
            return None

        return best_sep
    except Exception:
        return None


def read_stripe_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise ValidationError(f"No existe el archivo: {path}")

    ext = Path(path).suffix.lower()

    # 1) Si la extensión es Excel, intentamos Excel primero
    if ext in {".xlsx", ".xls"}:
        df = _try_read_excel(path)
        if df is not None:
            return df
        # NO cortamos aquí, porque el usuario puede haber renombrado un CSV a .xlsx

    # 2) Intento adicional como Excel aunque la extensión no lo diga
    df = _try_read_excel(path)
    if df is not None:
        return df

    # 3) Intento como CSV con pandas
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin1", "iso-8859-1"]
    separators = [",", ";", "\t", "|"]

    for enc in encodings:
        detected_sep = _detect_delimiter_from_text(path, enc)

        ordered_seps = []
        if detected_sep:
            ordered_seps.append(detected_sep)
        ordered_seps.extend([sep for sep in separators if sep != detected_sep])

        for sep in ordered_seps:
            df = _try_read_csv_with_pandas(path, encoding=enc, sep=sep)
            if df is not None:
                return df

    # 4) Fallback manual fuerte para CSV mal parseados por pandas
    for enc in encodings:
        detected_sep = _detect_delimiter_from_text(path, enc)

        ordered_seps = []
        if detected_sep:
            ordered_seps.append(detected_sep)
        ordered_seps.extend([sep for sep in separators if sep != detected_sep])

        for sep in ordered_seps:
            df = _try_read_csv_manual(path, encoding=enc, delimiter=sep)
            if df is not None:
                return df

    raise ValidationError(
        f"No se pudo leer el archivo {path} como CSV ni como Excel válido."
    )