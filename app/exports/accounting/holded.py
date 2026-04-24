from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.domain.models import Client


def export_holded_csv(summaries, path: str, client: Client | None = None) -> str:
    rows: list[dict] = []
    for summary in summaries:
        rows.append(
            {
                "externalId": summary.payout_id or "SIN_PAYOUT",
                "date": "" if summary.bank_booked_at is None else summary.bank_booked_at.date().isoformat(),
                "currency": summary.settlement_currency,
                "gross": float(summary.gross_total),
                "fees": float(summary.fees_total),
                "refunds": float(summary.refunds_total),
                "net": float(summary.net_total),
                "clientName": "" if client is None else client.name,
                "notes": summary.explanation_summary,
            }
        )
    output_path = Path(path).with_suffix(".csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")
    return str(output_path)
