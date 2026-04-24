import pandas as pd


def export_bank_matches_csv(matches, path: str):
    rows = []
    for m in matches:
        rows.append(
            {
                "Payout ID": "" if m.payout_id is None else str(m.payout_id).strip(),
                "Moneda": str(m.settlement_currency).strip(),
                "Neto Stripe": str(m.stripe_expected_net),
                "Importe banco": "" if m.bank_observed_amount is None else str(m.bank_observed_amount),
                "Diferencia": "" if m.difference is None else str(m.difference),
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
    df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")
