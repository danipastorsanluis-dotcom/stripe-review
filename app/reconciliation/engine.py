from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from app.domain.enums import IssueSeverity, ReconciliationStatus, TransactionType
from app.domain.models import NormalizedTransaction, PayoutSummary, ReconciliationIssue
from app.reconciliation.actions import get_recommended_action


ZERO = Decimal("0.00")
MISSING_PAYOUT_ID = "SIN_PAYOUT"


COMPLEX_REVIEW_TYPES = {
    "adjustment",
    "dispute",
    "chargeback",
    "network_fee",
    "reserve_hold",
    "reserve_release",
    "reserve_transaction",
    "reserved_funds",
    "risk_reserved_funds",
    "risk_reserved_funds_release",
    "transfer",
    "transfer_cancel",
    "transfer_failure",
    "transfer_refund",
    "tax_fee",
    "advance",
    "advance_funding",
    "anticipation_repayment",
    "charge_failure",
    "connect_collection_transfer",
    "authorization_hold",
    "authorization_release",
    "obligation_outbound",
    "obligation_reversal_inbound",
    "balance_payment_debit",
    "balance_payment_debit_reversal",
    "payout_failure",
}

UNHANDLED_LABELS = {
    "topup": "topup",
    "topup_reversal": "topup_reversal",
    "other": "other",
    "unknown": "unknown",
}


def _clean_currency(value: str) -> str:
    text = (value or "").strip().upper()
    return text or "UNKNOWN"


def _clean_payout_id(value: str | None) -> str:
    text = (value or "").strip()
    return text or MISSING_PAYOUT_ID


def _display_types(items: set[str]) -> str:
    return ", ".join(sorted(items))


def _currency_list(rows: list[NormalizedTransaction]) -> list[str]:
    return sorted({_clean_currency(tx.currency) for tx in rows})


def _issue_dedupe_key(issue: ReconciliationIssue) -> tuple:
    return (
        issue.severity or "",
        issue.code or "",
        issue.message or "",
        issue.payout_id or "",
        issue.transaction_id or "",
    )


def _dedupe_issues(issues: list[ReconciliationIssue]) -> list[ReconciliationIssue]:
    seen = set()
    deduped = []

    for issue in issues:
        key = _issue_dedupe_key(issue)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)

    return deduped


def _recommended_action_from_status(status: ReconciliationStatus) -> str:
    if status == ReconciliationStatus.READY:
        return "Se puede exportar."
    if status == ReconciliationStatus.REVIEW:
        return "Revisar antes de exportar."
    if status == ReconciliationStatus.BLOCKED:
        return "No exportar todavía."
    return ""


def _append_issue(
    issues: list[ReconciliationIssue],
    *,
    severity: str,
    code: str,
    message: str,
    payout_id: str | None,
    transaction_id: str | None,
    suggested_action: str,
) -> None:
    issues.append(
        ReconciliationIssue(
            severity=severity,
            code=code,
            message=message,
            payout_id=payout_id,
            transaction_id=transaction_id,
            suggested_action=suggested_action,
        )
    )


def _is_timing_like_case(raw_type: str) -> bool:
    return raw_type in {
        "payout",
        "payout_failure",
        "adjustment",
        "advance",
        "advance_funding",
        "anticipation_repayment",
        "transfer",
        "transfer_failure",
        "transfer_cancel",
        "transfer_refund",
        "reserve_hold",
        "reserve_release",
        "reserve_transaction",
        "reserved_funds",
        "risk_reserved_funds",
        "risk_reserved_funds_release",
    }


def reconcile_payouts(
    transactions: Iterable[NormalizedTransaction],
) -> tuple[list[PayoutSummary], list[ReconciliationIssue]]:
    payout_groups: dict[str, list[NormalizedTransaction]] = defaultdict(list)
    issues: list[ReconciliationIssue] = []

    tx_list = list(transactions)

    for tx in tx_list:
        payout_id = _clean_payout_id(tx.payout_id)
        payout_groups[payout_id].append(tx)

        if payout_id == MISSING_PAYOUT_ID:
            _append_issue(
                issues,
                severity=IssueSeverity.HIGH.value,
                code="NO_PAYOUT",
                message="Transacción sin payout_id.",
                payout_id=None,
                transaction_id=tx.id,
                suggested_action=get_recommended_action("NO_PAYOUT"),
            )

    summaries: list[PayoutSummary] = []

    for payout_id, payout_rows in payout_groups.items():
        currencies = _currency_list(payout_rows)
        currencies_text = ", ".join(currencies)
        has_multiple_currencies = len(currencies) > 1

        currency_groups: dict[str, list[NormalizedTransaction]] = defaultdict(list)
        for tx in payout_rows:
            currency_groups[_clean_currency(tx.currency)].append(tx)

        if payout_id == MISSING_PAYOUT_ID:
            _append_issue(
                issues,
                severity=IssueSeverity.HIGH.value,
                code="NO_PAYOUT",
                message="Grupo sin payout_id. No se puede conciliar correctamente.",
                payout_id=payout_id,
                transaction_id=None,
                suggested_action=get_recommended_action("NO_PAYOUT"),
            )
        elif has_multiple_currencies:
            _append_issue(
                issues,
                severity=IssueSeverity.MEDIUM.value,
                code="MULTICURRENCY",
                message=f"Payout con múltiples monedas: {currencies_text}",
                payout_id=payout_id,
                transaction_id=None,
                suggested_action=get_recommended_action("MULTICURRENCY"),
            )

        for settlement_currency, rows in sorted(currency_groups.items()):
            gross_total = ZERO
            fees_total = ZERO
            refunds_total = ZERO
            net_total = ZERO

            tx_count = len(rows)
            recognized_effect = False
            recognized_tx_count = 0
            complex_tx_count = 0
            unhandled_tx_count = 0
            timing_like_tx_count = 0

            complex_types_set: set[str] = set()
            unhandled_types_set: set[str] = set()
            issue_codes: list[str] = []

            review_reason = ""
            blocking_reason = ""
            latest_transaction_at = None  # para fecha por defecto del asiento

            for tx in rows:
                tx_type = tx.transaction_type
                raw_type = (tx.type or "").strip().lower() or "unknown"

                if tx_type == TransactionType.CHARGE:
                    gross_total += tx.amount
                    # Formato clásico de Stripe: la fee viene embebida en cada
                    # línea charge (columna Fee por transacción). Si no la
                    # sumamos aquí, los netos no cuadran y los asientos
                    # contables salen descuadrados.
                    if tx.fee != ZERO:
                        fees_total += tx.fee
                    recognized_effect = True
                    recognized_tx_count += 1

                elif tx_type == TransactionType.REFUND:
                    refunds_total += tx.amount
                    # Los refunds también pueden traer su propia fee
                    # (por ejemplo, fee del refund o reversal fee).
                    if tx.fee != ZERO:
                        fees_total += tx.fee
                    recognized_effect = True
                    recognized_tx_count += 1

                elif tx_type == TransactionType.FEE:
                    # Línea FEE explícita: la fee está en tx.fee o en tx.net.
                    fees_total += tx.fee if tx.fee != ZERO else tx.net
                    recognized_effect = True
                    recognized_tx_count += 1

                elif tx_type == TransactionType.PAYOUT:
                    # Línea útil para timing / conciliación, pero no para bruto/fees/refunds.
                    timing_like_tx_count += 1

                elif raw_type in COMPLEX_REVIEW_TYPES:
                    complex_types_set.add(raw_type)
                    complex_tx_count += 1
                    if _is_timing_like_case(raw_type):
                        timing_like_tx_count += 1

                else:
                    normalized_label = UNHANDLED_LABELS.get(raw_type, raw_type)
                    unhandled_types_set.add(normalized_label)
                    unhandled_tx_count += 1

                if tx.created is not None:
                    if latest_transaction_at is None or tx.created > latest_transaction_at:
                        latest_transaction_at = tx.created

                net_total += tx.net

            expected_net = gross_total + fees_total + refunds_total
            observed_net = net_total
            difference = observed_net - expected_net

            status = ReconciliationStatus.READY

            if payout_id == MISSING_PAYOUT_ID:
                status = ReconciliationStatus.BLOCKED
                issue_codes.append("NO_PAYOUT")
                blocking_reason = "sin payout_id"

            if has_multiple_currencies and status != ReconciliationStatus.BLOCKED:
                status = ReconciliationStatus.REVIEW
                issue_codes.append("MULTICURRENCY")
                review_reason = review_reason or "mezcla de monedas"

            if net_total < ZERO and status != ReconciliationStatus.BLOCKED:
                status = ReconciliationStatus.REVIEW
                issue_codes.append("NEGATIVE_NET")
                review_reason = review_reason or "neto negativo"

                _append_issue(
                    issues,
                    severity=IssueSeverity.MEDIUM.value,
                    code="NEGATIVE_NET",
                    message="Payout con neto negativo.",
                    payout_id=f"{payout_id} [{settlement_currency}]",
                    transaction_id=None,
                    suggested_action=get_recommended_action("NEGATIVE_NET"),
                )

            if complex_types_set:
                if status != ReconciliationStatus.BLOCKED:
                    status = ReconciliationStatus.REVIEW
                issue_codes.append("COMPLEX_TYPES")
                review_reason = review_reason or "tipos complejos"

                _append_issue(
                    issues,
                    severity=IssueSeverity.MEDIUM.value,
                    code="COMPLEX_TYPES",
                    message=f"Tipos complejos que afectan al neto y requieren explicación: {_display_types(complex_types_set)}",
                    payout_id=f"{payout_id} [{settlement_currency}]",
                    transaction_id=None,
                    suggested_action=get_recommended_action("COMPLEX_TYPES"),
                )

            if unhandled_types_set:
                if status != ReconciliationStatus.BLOCKED:
                    status = ReconciliationStatus.REVIEW
                issue_codes.append("UNHANDLED_TYPES")
                review_reason = review_reason or "tipos no tratados"

                _append_issue(
                    issues,
                    severity=IssueSeverity.MEDIUM.value,
                    code="UNHANDLED_TYPES",
                    message=f"Tipos no tratados explícitamente: {_display_types(unhandled_types_set)}",
                    payout_id=f"{payout_id} [{settlement_currency}]",
                    transaction_id=None,
                    suggested_action=get_recommended_action("UNHANDLED_TYPES"),
                )

            if not recognized_effect and tx_count > 0:
                if status != ReconciliationStatus.BLOCKED:
                    status = ReconciliationStatus.REVIEW
                issue_codes.append("EMPTY_PAYOUT_EFFECT")
                review_reason = review_reason or "sin líneas reconocidas"

                _append_issue(
                    issues,
                    severity=IssueSeverity.LOW.value,
                    code="EMPTY_PAYOUT_EFFECT",
                    message="El payout no tiene líneas reconocidas de ventas, refunds o fees.",
                    payout_id=f"{payout_id} [{settlement_currency}]",
                    transaction_id=None,
                    suggested_action=get_recommended_action("EMPTY_PAYOUT_EFFECT"),
                )

            # Señal adicional de timing/desfase: hay neto observado distinto del esperado
            # y además aparecen líneas típicas de liquidación/ajuste/payout.
            if (
                difference != ZERO
                and timing_like_tx_count > 0
                and status != ReconciliationStatus.BLOCKED
            ):
                if "TIMING_DIFFERENCE" not in issue_codes:
                    issue_codes.append("TIMING_DIFFERENCE")
                review_reason = review_reason or "posible desfase temporal"

                _append_issue(
                    issues,
                    severity=IssueSeverity.LOW.value,
                    code="TIMING_DIFFERENCE",
                    message="Se detectan líneas compatibles con desfase temporal o liquidación no lineal del payout.",
                    payout_id=f"{payout_id} [{settlement_currency}]",
                    transaction_id=None,
                    suggested_action="Revisar fechas de disponibilidad, payout y extracto bancario antes de exportar.",
                )

                if status == ReconciliationStatus.READY:
                    status = ReconciliationStatus.REVIEW

            status_reason = blocking_reason or review_reason or "listo para revisión final"

            summary = PayoutSummary(
                payout_id=payout_id,
                settlement_currency=settlement_currency,
                gross_total=gross_total,
                fees_total=fees_total,
                refunds_total=refunds_total,
                net_total=net_total,
                tx_count=tx_count,
                status=status.value,
                currencies=currencies_text,
                complex_types=_display_types(complex_types_set),
                unhandled_types=_display_types(unhandled_types_set),
                recommended_action=_recommended_action_from_status(status),
                issue_codes=sorted(set(issue_codes)),
                expected_net=expected_net,
                observed_net=observed_net,
                difference=difference,
                recognized_tx_count=recognized_tx_count,
                complex_tx_count=complex_tx_count,
                unhandled_tx_count=unhandled_tx_count,
                evidence_lines_count=recognized_tx_count + complex_tx_count + unhandled_tx_count,
                status_reason=status_reason,
                review_reason=review_reason,
                blocking_reason=blocking_reason,
                latest_transaction_at=latest_transaction_at,
            )
            summaries.append(summary)

    summaries.sort(key=lambda s: ((s.payout_id or ""), s.settlement_currency))
    return summaries, _dedupe_issues(issues)