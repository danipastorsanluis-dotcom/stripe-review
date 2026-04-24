from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.domain.models import Client


def export_contasol_csv(summaries, path: str, client: Client | None = None) -> str:
    rows: list[dict] = []
    for summary in summaries:
        for entry in summary.to_accounting_entries(client):
            rows.append(
                {
                    "Fecha": "" if entry.entry_date is None else entry.entry_date.date().isoformat(),
                    "Asiento": entry.external_id,
                    "Cuenta": entry.account_code,
                    "Concepto": entry.concept,
                    "Debe": float(entry.debit),
                    "Haber": float(entry.credit),
                    "Diario": entry.journal_code,
                    "Documento": entry.payout_id,
                }
            )
    output_path = Path(path).with_suffix(".csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False, sep=";", encoding="utf-8-sig")
    return str(output_path)
