import pandas as pd

from app.exports.excel_utils import save_as_professional_excel, _to_excel_number


def export_bank_matches_xlsx(matches, path: str):
    rows = []
    for m in matches:
        rows.append(
            {
                "Payout ID": "" if m.payout_id is None else str(m.payout_id).strip(),
                "Moneda": str(m.settlement_currency).strip(),
                "Neto Stripe": _to_excel_number(m.stripe_expected_net),
                "Importe banco": _to_excel_number(m.bank_observed_amount),
                "Diferencia": _to_excel_number(m.difference),
                "Estado bancario": str(m.status).strip(),
                "Tipo de match": str(m.match_type).strip(),
                "Confianza": str(m.confidence).strip(),
                "Bank Tx ID": "" if m.bank_transaction_id is None else str(m.bank_transaction_id).strip(),
                "Fecha banco": "" if m.bank_date is None else str(m.bank_date),
                "Referencia banco": str(m.bank_reference).strip(),
                "Descripción banco": str(m.bank_description).strip(),
                "Nota": str(m.note).strip(),
            }
        )

    df = pd.DataFrame(rows)
    return save_as_professional_excel(df, path, sheet_name="Bank_Matching")
