from typing import Dict


def build_accounting_summary(health: Dict) -> str:
    total = int(health.get("total_payouts", 0))
    matched = int(health.get("matched_count", 0))
    warnings = int(health.get("warning_count", 0))
    issues = int(health.get("issue_count", 0))

    multicurrency = int(health.get("multicurrency_count", 0))
    unassigned = int(health.get("unassigned_count", 0))
    negative_net = int(health.get("negative_net_count", 0))
    complex_types = int(health.get("complex_types_count", 0))
    unhandled_types = int(health.get("unhandled_types_count", 0))
    empty_effect = int(health.get("empty_payout_effect_count", 0))
    bank_matched = int(health.get("bank_matched_count", 0))
    bank_review = int(health.get("bank_review_count", 0))
    bank_missing = int(health.get("bank_missing_count", 0))
    bank_unused = int(health.get("bank_unused_count", 0))

    if issues > 0:
        decision = "❌ No se recomienda exportar contabilidad todavía."
    elif warnings > 0:
        decision = "⚠️ Hay payouts revisables. Conviene revisar antes de exportar."
    else:
        decision = "✅ Puedes exportar contabilidad."

    bank_block = ""
    if bank_matched or bank_review or bank_missing or bank_unused:
        bank_block = f"""
Chequeo bancario:
- Match bancario exacto: {bank_matched}
- Match bancario con revisión: {bank_review}
- Sin match bancario: {bank_missing}
- Movimientos bancarios sin usar: {bank_unused}
"""

    return f"""RESUMEN DE CIERRE

✔ {matched} payouts listos
⚠ {warnings} payouts requieren revisión
❌ {issues} payouts bloqueados

Total payouts: {total}

Causas principales de revisión o bloqueo:
- Multimoneda: {multicurrency}
- Sin payout: {unassigned}
- Neto negativo: {negative_net}
- Tipos complejos: {complex_types}
- Tipos no tratados: {unhandled_types}
- Sin efecto reconocible: {empty_effect}
{bank_block}
Lectura honesta:
- Este resultado explica el archivo de Stripe y ayuda a decidir si exportar.
- Si además has subido banco, también valida si aparece un movimiento que soporte el payout.
- Sigue sin sustituir una validación contable final.

Decisión:
{decision}
"""
