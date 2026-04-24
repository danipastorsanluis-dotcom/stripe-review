from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.domain.models import Client


def _client_value(client, key: str) -> str:
    if client is None:
        return ""
    if isinstance(client, dict):
        return str(client.get(key, "")).strip()
    return str(getattr(client, key, "")).strip()


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_accounting_rows(summaries, client: Client | None = None) -> tuple[list[dict], list[dict]]:
    summary_rows: list[dict] = []
    asiento_rows: list[dict] = []

    for summary in summaries:
        payout_id = _clean_text(getattr(summary, "payout_id", ""))
        status = _clean_text(getattr(summary, "status", ""))
        settlement_currency = _clean_text(getattr(summary, "settlement_currency", ""))
        unhandled_types = _clean_text(getattr(summary, "unhandled_types", ""))
        recommended_action = _clean_text(getattr(summary, "recommended_action", ""))
        explanation = _clean_text(getattr(summary, "explanation_summary", ""))
        bank_status = _clean_text(getattr(summary, "bank_match_status", "not_checked"))
        bank_reference = _clean_text(getattr(summary, "bank_reference", ""))
        bank_difference = getattr(summary, "bank_difference", None)

        summary_rows.append(
            {
                "Concepto": "Resumen payout Stripe",
                "Cliente": _client_value(client, "name"),
                "NIF": _client_value(client, "nif"),
                "Payout ID": payout_id,
                "Moneda liquidación": settlement_currency,
                "Ventas brutas": str(getattr(summary, "gross_total", "0.00")),
                "Comisiones": str(getattr(summary, "fees_total", "0.00")),
                "Refunds": str(getattr(summary, "refunds_total", "0.00")),
                "Neto": str(getattr(summary, "net_total", "0.00")),
                "Estado": status,
                "Estado bancario": bank_status,
                "Referencia banco": bank_reference,
                "Diferencia banco": "" if bank_difference is None else str(bank_difference),
                "Acción recomendada": recommended_action,
                "Explicación": explanation,
                "Tipos no tratados": unhandled_types,
                "Seguro para exportar": bool(getattr(summary, "safe_to_export", False)),
            }
        )

        for entry in summary.to_accounting_entries(client):
            asiento_rows.append(
                {
                    "Fecha": "" if entry.entry_date is None else entry.entry_date.date().isoformat(),
                    "Cliente": entry.client_name,
                    "NIF": entry.client_nif,
                    "Payout ID": entry.payout_id,
                    "Moneda": entry.currency,
                    "Diario": entry.journal_code,
                    "Cuenta": entry.account_code,
                    "Concepto": entry.concept,
                    "Debe": "" if entry.debit == 0 else float(entry.debit),
                    "Haber": "" if entry.credit == 0 else float(entry.credit),
                    "Estado": entry.status,
                }
            )

    return summary_rows, asiento_rows


def export_accounting_generic_csv(summaries, path: str, client: Client | None = None) -> str:
    summary_rows, asiento_rows = build_accounting_rows(summaries, client=client)
    pd.DataFrame(summary_rows).to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    asiento_path = path.replace(".csv", "_asiento.csv")
    pd.DataFrame(asiento_rows).to_csv(asiento_path, index=False, sep=";", encoding="utf-8-sig")
    return path


def export_accounting_generic_xlsx(summaries, path: str, client: Client | None = None) -> str:
    summary_rows, asiento_rows = build_accounting_rows(summaries, client=client)
    output_path = Path(path).with_suffix(".xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        summary_df = pd.DataFrame(summary_rows)
        asiento_df = pd.DataFrame(asiento_rows)
        summary_df.to_excel(writer, index=False, sheet_name="Resumen_Contable")
        asiento_df.to_excel(writer, index=False, sheet_name="Asiento_Contable")

        workbook = writer.book
        money_format = workbook.add_format({"num_format": "#,##0.00"})
        for sheet_name, df in {"Resumen_Contable": summary_df, "Asiento_Contable": asiento_df}.items():
            ws = writer.sheets[sheet_name]
            for col_idx, column in enumerate(df.columns):
                if column in {"Ventas brutas", "Comisiones", "Refunds", "Neto", "Debe", "Haber", "Diferencia banco"}:
                    ws.set_column(col_idx, col_idx, 14, money_format)
                else:
                    ws.set_column(col_idx, col_idx, max(14, len(str(column)) + 2))
            ws.freeze_panes(1, 0)
    return str(output_path)
