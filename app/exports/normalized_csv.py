import pandas as pd


def export_normalized_csv(transactions, path: str):
    rows = []

    for tx in transactions:
        rows.append(
            {
                "ID Transacción": "" if tx.id is None else str(tx.id).strip(),
                "Payout ID": "" if tx.payout_id is None else str(tx.payout_id).strip(),
                "Tipo": "" if tx.type is None else str(tx.type).strip(),
                "Bruto": str(tx.amount),
                "Comisión": str(tx.fee),
                "Neto": str(tx.net),
                "Moneda": "" if tx.currency is None else str(tx.currency).strip().upper(),
                "Fecha": tx.created.isoformat() if tx.created is not None else "",
                "Descripción": "" if tx.description is None else str(tx.description).strip(),
            }
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "ID Transacción",
            "Payout ID",
            "Tipo",
            "Bruto",
            "Comisión",
            "Neto",
            "Moneda",
            "Fecha",
            "Descripción",
        ],
    )
    df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")