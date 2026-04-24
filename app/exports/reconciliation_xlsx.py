import pandas as pd

from app.exports.excel_utils import save_as_professional_excel, _to_excel_number
from app.reconciliation.explain import build_payout_explanation


def export_reconciliation_xlsx(summaries, path: str):
    rows = []

    for s in summaries:
        explanation_detail = build_payout_explanation(s)

        rows.append(
            {
                "Payout ID": "" if s.payout_id is None else str(s.payout_id).strip(),
                "Moneda liquidación": "" if s.settlement_currency is None else str(s.settlement_currency).strip(),
                "Ventas brutas": _to_excel_number(s.gross_total),
                "Comisiones": _to_excel_number(s.fees_total),
                "Refunds": _to_excel_number(s.refunds_total),
                "Neto": _to_excel_number(s.net_total),
                "Neto esperado": _to_excel_number(s.expected_net),
                "Neto observado": _to_excel_number(s.observed_net),
                "Diferencia Stripe": _to_excel_number(s.difference),
                "Bank neto esperado": _to_excel_number(getattr(s, "bank_expected_amount", None)),
                "Bank neto observado": _to_excel_number(getattr(s, "bank_observed_amount", None)),
                "Diferencia banco": _to_excel_number(getattr(s, "bank_difference", None)),
                "Estado bancario": str(getattr(s, "bank_match_status", "not_checked")).strip(),
                "Tipo de match bancario": str(getattr(s, "bank_match_type", "not_checked")).strip(),
                "Confianza match bancario": str(getattr(s, "bank_confidence", "none")).strip(),
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
    return save_as_professional_excel(df, path, sheet_name="Resumen_Payouts")