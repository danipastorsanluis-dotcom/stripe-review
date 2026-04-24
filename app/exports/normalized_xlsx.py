import pandas as pd

from app.exports.excel_utils import save_as_professional_excel, _to_excel_number


def export_normalized_xlsx(transactions, path: str):
    rows = []

    for tx in transactions:
        rows.append(
            {
                "ID Transacción": "" if tx.id is None else str(tx.id).strip(),
                "Payout ID": "" if tx.payout_id is None else str(tx.payout_id).strip(),
                "Tipo": "" if tx.type is None else str(tx.type).strip(),
                "Bruto": _to_excel_number(tx.amount),
                "Comisión": _to_excel_number(tx.fee),
                "Neto": _to_excel_number(tx.net),
                "Moneda": "" if tx.currency is None else str(tx.currency).strip().upper(),
                "Fecha": tx.created,
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

    return save_as_professional_excel(df, path, sheet_name="Detalle_Stripe")