from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from xlsxwriter.utility import xl_col_to_name


MONEY_KEYWORDS = (
    "importe",
    "amount",
    "gross",
    "net",
    "neto",
    "fee",
    "fees",
    "refund",
    "refunds",
    "brutas",
    "bruto",
    "comisiones",
    "comisión",
    "debe",
    "haber",
    "difference",
)

INTEGER_KEYWORDS = (
    "count",
    "transacciones",
    "tx",
)

DATE_KEYWORDS = (
    "fecha",
    "created",
    "available",
    "_utc",
    "date",
)

WRAP_KEYWORDS = (
    "mensaje",
    "descripción",
    "descripcion",
    "qué hacer",
    "que hacer",
    "acción",
    "accion",
    "tipos no tratados",
    "monedas",
    "concepto",
    "observaciones",
    "explicación",
    "explicacion",
)


def _to_excel_number(value):
    if value is None or value == "":
        return None

    if isinstance(value, Decimal):
        value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return float(value)

    try:
        text = str(value).strip()
        if text == "":
            return None
        text = text.replace(",", ".")
        return float(text)
    except Exception:
        return value


def _is_money_column(column_name: str) -> bool:
    name = str(column_name).strip().lower()
    return any(keyword in name for keyword in MONEY_KEYWORDS)


def _is_integer_column(column_name: str) -> bool:
    name = str(column_name).strip().lower()
    return any(keyword in name for keyword in INTEGER_KEYWORDS)


def _is_date_column(column_name: str) -> bool:
    name = str(column_name).strip().lower()
    return any(keyword in name for keyword in DATE_KEYWORDS)


def _is_wrap_column(column_name: str) -> bool:
    name = str(column_name).strip().lower()
    return any(keyword in name for keyword in WRAP_KEYWORDS)


def _column_width(series: pd.Series, header: str, max_width: int = 50) -> int:
    if series.empty:
        return min(len(str(header)) + 2, max_width)

    max_len = max(
        len(str(header)),
        series.astype(str).map(len).max(),
    )
    return min(max_len + 2, max_width)


def _make_excel_safe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    safe_df = df.copy()

    for col in safe_df.columns:
        series = safe_df[col]

        if pd.api.types.is_datetime64tz_dtype(series):
            safe_df[col] = series.dt.tz_localize(None)
            continue

        if series.dtype == "object":
            def _strip_tz(value):
                if value is None:
                    return value

                if isinstance(value, pd.Timestamp):
                    if value.tzinfo is not None:
                        return value.tz_localize(None)
                    return value

                if isinstance(value, datetime):
                    if value.tzinfo is not None:
                        return value.replace(tzinfo=None)
                    return value

                return value

            safe_df[col] = series.map(_strip_tz)

    return safe_df


def save_as_professional_excel(
    df: pd.DataFrame,
    path: str,
    sheet_name: str = "Report",
):
    output_path = Path(path).with_suffix(".xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    safe_df = _make_excel_safe_dataframe(df)

    with pd.ExcelWriter(
        output_path,
        engine="xlsxwriter",
        datetime_format="yyyy-mm-dd hh:mm",
        date_format="yyyy-mm-dd",
    ) as writer:
        safe_df.to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        money_format = workbook.add_format(
            {
                "num_format": "#,##0.00",
                "align": "right",
                "valign": "vcenter",
            }
        )
        integer_format = workbook.add_format(
            {
                "num_format": "0",
                "align": "right",
                "valign": "vcenter",
            }
        )
        date_format = workbook.add_format(
            {
                "num_format": "yyyy-mm-dd hh:mm",
                "align": "left",
                "valign": "vcenter",
            }
        )
        wrap_format = workbook.add_format(
            {
                "text_wrap": True,
                "valign": "top",
            }
        )

        ready_format = workbook.add_format({"bg_color": "#DCFCE7", "font_color": "#166534"})
        review_format = workbook.add_format({"bg_color": "#FEF3C7", "font_color": "#92400E"})
        blocked_format = workbook.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B"})
        medium_severity_format = workbook.add_format({"bg_color": "#FEF3C7", "font_color": "#92400E"})
        high_severity_format = workbook.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B"})
        multicurrency_format = workbook.add_format({"bg_color": "#E0E7FF", "font_color": "#3730A3"})
        unhandled_types_format = workbook.add_format({"bg_color": "#FCE7F3", "font_color": "#9D174D"})

        max_row, max_col = safe_df.shape

        if max_col > 0:
            if max_row > 0:
                column_settings = []
                for col in safe_df.columns:
                    setting = {"header": col}
                    if _is_money_column(col) or _is_integer_column(col):
                        setting["total_function"] = "sum"
                    column_settings.append(setting)

                worksheet.add_table(
                    0,
                    0,
                    max_row,
                    max_col - 1,
                    {
                        "columns": column_settings,
                        "style": "Table Style Medium 9",
                        "total_row": True,
                    },
                )

            for col_idx, col_name in enumerate(safe_df.columns):
                width = _column_width(safe_df[col_name], col_name)

                if _is_money_column(col_name):
                    worksheet.set_column(col_idx, col_idx, width, money_format)
                elif _is_integer_column(col_name):
                    worksheet.set_column(col_idx, col_idx, width, integer_format)
                elif _is_date_column(col_name):
                    worksheet.set_column(col_idx, col_idx, max(width, 18), date_format)
                elif _is_wrap_column(col_name):
                    worksheet.set_column(col_idx, col_idx, min(max(width, 18), 60), wrap_format)
                else:
                    worksheet.set_column(col_idx, col_idx, width)

            lowered_columns = [str(c).strip().lower() for c in safe_df.columns]

            if "estado" in lowered_columns and max_row > 0:
                estado_idx = lowered_columns.index("estado")
                worksheet.conditional_format(
                    1, estado_idx, max_row, estado_idx,
                    {"type": "cell", "criteria": "equal to", "value": '"Listo"', "format": ready_format},
                )
                worksheet.conditional_format(
                    1, estado_idx, max_row, estado_idx,
                    {"type": "cell", "criteria": "equal to", "value": '"Revisar"', "format": review_format},
                )
                worksheet.conditional_format(
                    1, estado_idx, max_row, estado_idx,
                    {"type": "cell", "criteria": "equal to", "value": '"Bloqueado"', "format": blocked_format},
                )

            if "severidad" in lowered_columns and max_row > 0:
                sev_idx = lowered_columns.index("severidad")
                worksheet.conditional_format(
                    1, sev_idx, max_row, sev_idx,
                    {"type": "cell", "criteria": "equal to", "value": '"medium"', "format": medium_severity_format},
                )
                worksheet.conditional_format(
                    1, sev_idx, max_row, sev_idx,
                    {"type": "cell", "criteria": "equal to", "value": '"high"', "format": high_severity_format},
                )

            if "monedas" in lowered_columns and max_row > 0:
                monedas_idx = lowered_columns.index("monedas")
                worksheet.conditional_format(
                    1, monedas_idx, max_row, monedas_idx,
                    {"type": "text", "criteria": "containing", "value": ",", "format": multicurrency_format},
                )

            if "tipos no tratados" in lowered_columns and max_row > 0:
                unhandled_idx = lowered_columns.index("tipos no tratados")
                col_letter = xl_col_to_name(unhandled_idx)
                worksheet.conditional_format(
                    1, unhandled_idx, max_row, unhandled_idx,
                    {
                        "type": "formula",
                        "criteria": f'=LEN(TRIM({col_letter}2))>0',
                        "format": unhandled_types_format,
                    },
                )

        worksheet.freeze_panes(1, 0)

    return str(output_path)