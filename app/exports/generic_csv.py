import pandas as pd

from app.reconciliation.explain import build_payout_explanation


def export_reconciliation_csv(summaries, path: str):
    rows = []

    for s in summaries:
        explanation_detail = build_payout_explanation(s)

        rows.append(
            {
                "Payout ID": "" if s.payout_id is None else str(s.payout_id).strip(),
                "Moneda liquidación": "" if s.settlement_currency is None else str(s.settlement_currency).strip(),
                "Ventas brutas": str(s.gross_total),
                "Comisiones": str(s.fees_total),
                "Refunds": str(s.refunds_total),
                "Neto": str(s.net_total),
                "Neto esperado": str(s.expected_net),
                "Neto observado": str(s.observed_net),
                "Diferencia Stripe": str(s.difference),
                "Bank neto esperado": str(getattr(s, "bank_expected_amount", "0.00")),
                "Bank neto observado": "" if getattr(s, "bank_observed_amount", None) is None else str(s.bank_observed_amount),
                "Diferencia banco": "" if getattr(s, "bank_difference", None) is None else str(s.bank_difference),
                "Estado bancario": str(getattr(s, "bank_match_status", "not_checked")),
                "Tipo de match bancario": str(getattr(s, "bank_match_type", "not_checked")),
                "Confianza match bancario": str(getattr(s, "bank_confidence", "none")),
                "Bank Tx ID": str(getattr(s, "bank_transaction_id", "")).strip(),
                "Referencia banco": str(getattr(s, "bank_reference", "")).strip(),
                "Descripción banco": str(getattr(s, "bank_description", "")).strip(),
                "Transacciones": int(s.tx_count),
                "Líneas reconocidas": int(getattr(s, "recognized_tx_count", 0)),
                "Líneas complejas": int(getattr(s, "complex_tx_count", 0)),
                "Líneas no tratadas": int(getattr(s, "unhandled_tx_count", 0)),
                "Estado": "" if s.status is None else str(s.status).strip(),
                "Motivo principal": getattr(s, "primary_reason", ""),
                "Motivo revisión": getattr(s, "review_reason", ""),
                "Motivo bloqueo": getattr(s, "blocking_reason", ""),
                "Monedas": "" if s.currencies is None else str(s.currencies).strip(),
                "Tiene múltiples monedas": bool(s.has_multiple_currencies),
                "Tiene tipos complejos": bool(getattr(s, "has_complex_types", False)),
                "Tipos complejos": "" if getattr(s, "complex_types", None) is None else str(s.complex_types).strip(),
                "Tiene tipos no tratados": bool(s.has_unhandled_types),
                "Tipos no tratados": "" if s.unhandled_types is None else str(s.unhandled_types).strip(),
                "Acción recomendada": explanation_detail.get("action") or ("" if s.recommended_action is None else str(s.recommended_action).strip()),
                "Explicación": explanation_detail.get("explanation") or getattr(s, "explanation_summary", ""),
                "Seguro para exportar": bool(s.safe_to_export),
                "Procesable": bool(s.processable),
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")