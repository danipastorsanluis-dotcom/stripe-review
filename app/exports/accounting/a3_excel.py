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


def export_a3_excel(summaries, path: str, client: Client | None = None) -> str:
    """
    Exportación honesta: plantilla tipo importación Excel para asesoría.
    No pretende ser SUENLACE.DAT de 256 bytes.
    La hoja deja campos explícitos para mapeo/import posterior en A3 o revisión manual.
    """
    rows: list[dict] = []
    for summary in summaries:
        for line_no, entry in enumerate(summary.to_accounting_entries(client), start=1):
            rows.append(
                {
                    "empresa": _client_value(client, "name"),
                    "nif": _client_value(client, "nif"),
                    "diario": entry.journal_code,
                    "fecha": "" if entry.entry_date is None else entry.entry_date.date().isoformat(),
                    "asiento_externo": entry.external_id,
                    "linea": line_no,
                    "cuenta": entry.account_code,
                    "concepto": entry.concept,
                    "debe": float(entry.debit),
                    "haber": float(entry.credit),
                    "moneda": entry.currency,
                    "documento": entry.payout_id,
                    "origen": entry.source,
                    "estado": entry.status,
                }
            )

    output_path = Path(path).with_suffix(".xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df = pd.DataFrame(rows)
        df.to_excel(writer, index=False, sheet_name="A3_Import")
        ws = writer.sheets["A3_Import"]
        money_format = writer.book.add_format({"num_format": "#,##0.00"})
        for idx, col in enumerate(df.columns):
            if col in {"debe", "haber"}:
                ws.set_column(idx, idx, 14, money_format)
            else:
                ws.set_column(idx, idx, max(14, len(col) + 2))
        ws.freeze_panes(1, 0)
    return str(output_path)
