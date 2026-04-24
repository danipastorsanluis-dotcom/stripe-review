from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Iterable

from app.domain.enums import IssueSeverity, ReconciliationStatus
from app.domain.models import BankMatch, BankTransaction, PayoutSummary, ReconciliationIssue


ZERO = Decimal("0.00")
DEFAULT_TOLERANCE = Decimal("0.50")
DEFAULT_DATE_WINDOW_DAYS = 3
MAX_COMBINATION_SIZE = 2


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_decimal(value) -> Decimal:
    try:
        if value is None or value == "":
            return ZERO
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def _abs_decimal(value) -> Decimal:
    return abs(_to_decimal(value))


def _same_currency(summary: PayoutSummary, tx: BankTransaction) -> bool:
    return _clean_text(getattr(summary, "settlement_currency", "")).upper() == _clean_text(getattr(tx, "currency", "")).upper()


def _normalize_reference(value: str) -> str:
    raw = _clean_text(value).lower()
    if not raw:
        return ""
    return "".join(ch for ch in raw if ch.isalnum())


def _parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = _clean_text(value)
    if not text:
        return None

    candidates = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _extract_summary_date(summary: PayoutSummary) -> date | None:
    for attr in ("arrival_date", "payout_date", "available_on", "booked_at", "created_at", "bank_booked_at"):
        parsed = _parse_date(getattr(summary, attr, None))
        if parsed is not None:
            return parsed
    return None


def _date_distance_days(summary: PayoutSummary, tx: BankTransaction) -> int | None:
    summary_date = _extract_summary_date(summary)
    tx_date = _parse_date(getattr(tx, "booked_at", None))
    if summary_date is None or tx_date is None:
        return None
    return abs((tx_date - summary_date).days)


def _compute_reference_strength(summary: PayoutSummary, tx: BankTransaction) -> str:
    payout_id = _normalize_reference(_clean_text(getattr(summary, "payout_id", "")))
    if not payout_id:
        return "none"

    hint = _normalize_reference(_clean_text(getattr(tx, "payout_id_hint", "")))
    reference = _normalize_reference(_clean_text(getattr(tx, "reference", "")))
    description = _normalize_reference(_clean_text(getattr(tx, "description", "")))

    if hint == payout_id:
        return "hint_exact"
    if payout_id and payout_id in hint:
        return "hint_contains"
    if reference == payout_id:
        return "reference_exact"
    if payout_id and payout_id in reference:
        return "reference_contains"
    if payout_id and payout_id in description:
        return "description_contains"
    return "none"


def _candidate_score(
    summary: PayoutSummary,
    tx: BankTransaction,
    *,
    tolerance: Decimal,
    date_window_days: int,
) -> tuple[int, str, str]:
    score = 0
    reasons: list[str] = []

    expected = _to_decimal(getattr(summary, "net_total", ZERO))
    amount = _to_decimal(getattr(tx, "amount", ZERO))
    amount_diff = _abs_decimal(amount - expected)

    reference_strength = _compute_reference_strength(summary, tx)
    if reference_strength == "hint_exact":
        score += 70
        reasons.append("hint exacto")
    elif reference_strength == "hint_contains":
        score += 60
        reasons.append("hint parcial")
    elif reference_strength == "reference_exact":
        score += 50
        reasons.append("referencia exacta")
    elif reference_strength == "reference_contains":
        score += 40
        reasons.append("referencia parcial")
    elif reference_strength == "description_contains":
        score += 25
        reasons.append("descripción contiene payout_id")

    if amount_diff == ZERO:
        score += 40
        reasons.append("importe exacto")
    elif amount_diff <= tolerance:
        score += 20
        reasons.append("importe dentro de tolerancia")
    elif amount_diff <= Decimal("5.00"):
        score += 5
        reasons.append("importe cercano")

    date_distance = _date_distance_days(summary, tx)
    if date_distance is not None:
        if date_distance == 0:
            score += 20
            reasons.append("misma fecha")
        elif date_distance <= 1:
            score += 15
            reasons.append("fecha muy cercana")
        elif date_distance <= date_window_days:
            score += 10
            reasons.append("fecha cercana")

    if _same_currency(summary, tx):
        score += 10
        reasons.append("misma moneda")

    if reference_strength in {"hint_exact", "hint_contains"} and amount_diff == ZERO:
        score += 20
        reasons.append("coincidencia fuerte")

    if reference_strength == "none" and amount_diff > tolerance and (date_distance is None or date_distance > date_window_days):
        score -= 20

    if score >= 90:
        confidence = "high"
    elif score >= 55:
        confidence = "medium"
    elif score >= 30:
        confidence = "low"
    else:
        confidence = "none"

    return score, confidence, ", ".join(reasons)


def _classify_candidate(
    summary: PayoutSummary,
    tx: BankTransaction,
    *,
    tolerance: Decimal,
    date_window_days: int,
) -> tuple[str, str, str, str]:
    expected = _to_decimal(getattr(summary, "net_total", ZERO))
    amount = _to_decimal(getattr(tx, "amount", ZERO))
    amount_diff = _abs_decimal(amount - expected)

    score, confidence, _ = _candidate_score(
        summary,
        tx,
        tolerance=tolerance,
        date_window_days=date_window_days,
    )

    reference_strength = _compute_reference_strength(summary, tx)

    if reference_strength in {"hint_exact", "reference_exact"} and amount_diff == ZERO:
        return "matched", "payout_id_exact", confidence, "Movimiento bancario encontrado por payout_id y mismo importe."

    if reference_strength in {"hint_exact", "hint_contains", "reference_exact", "reference_contains"} and amount_diff <= tolerance:
        return "matched", "payout_id_with_tolerance", confidence, (
            "Movimiento bancario encontrado por payout_id o referencia parecida, con importe dentro de tolerancia."
        )

    if amount_diff == ZERO and score >= 45:
        return "matched", "amount_exact", confidence, (
            "Movimiento bancario encontrado por importe exacto y criterios compatibles."
        )

    if amount_diff <= tolerance and score >= 30:
        return "review", "amount_with_tolerance", confidence, (
            "Se encontró un movimiento bancario cercano, pero conviene revisarlo manualmente."
        )

    if reference_strength != "none" and score >= 30:
        return "review", "reference_based_review", confidence, (
            "La referencia bancaria apunta a este payout, pero no hay coincidencia suficiente para darlo por cerrado."
        )

    return "missing", "none", "none", "No se encontró movimiento bancario que explique este payout."


def _update_summary_from_match(summary: PayoutSummary, match: BankMatch) -> None:
    summary.bank_match_status = match.status
    summary.bank_expected_amount = match.stripe_expected_net
    summary.bank_observed_amount = match.bank_observed_amount
    summary.bank_difference = match.difference
    summary.bank_match_type = match.match_type
    summary.bank_confidence = match.confidence
    summary.bank_transaction_id = match.bank_transaction_id or ""
    summary.bank_reference = match.bank_reference
    summary.bank_description = match.bank_description
    summary.bank_booked_at = match.bank_date
    summary.bank_note = match.note


def _append_unique_issue(summary: PayoutSummary, issues: list[ReconciliationIssue], issue: ReconciliationIssue) -> None:
    if issue.code not in summary.issue_codes:
        summary.issue_codes.append(issue.code)
    issues.append(issue)


def _tighten_status(summary: PayoutSummary, new_status: str, reason: str) -> None:
    current = _clean_text(getattr(summary, "status", ""))
    order = {
        ReconciliationStatus.READY.value: 0,
        ReconciliationStatus.REVIEW.value: 1,
        ReconciliationStatus.BLOCKED.value: 2,
    }

    if order.get(new_status, 99) >= order.get(current, 99):
        summary.status = new_status

    if new_status == ReconciliationStatus.REVIEW.value and not _clean_text(getattr(summary, "review_reason", "")):
        summary.review_reason = reason

    if new_status == ReconciliationStatus.BLOCKED.value and not _clean_text(getattr(summary, "blocking_reason", "")):
        summary.blocking_reason = reason

    if not _clean_text(getattr(summary, "status_reason", "")) or new_status == ReconciliationStatus.BLOCKED.value:
        summary.status_reason = reason


def _make_virtual_transaction(summary: PayoutSummary, txs: tuple[BankTransaction, ...]) -> BankTransaction:
    booked_dates = [_parse_date(tx.booked_at) for tx in txs if _parse_date(tx.booked_at) is not None]
    best_date = txs[0].booked_at
    if booked_dates:
        best_date = min(tx.booked_at for tx in txs)

    description = " | ".join(filter(None, [_clean_text(tx.description) for tx in txs]))
    reference = " | ".join(filter(None, [_clean_text(tx.reference) for tx in txs]))
    payout_hints = " | ".join(filter(None, [_clean_text(tx.payout_id_hint) for tx in txs])) or None

    return BankTransaction(
        id=" + ".join(tx.id for tx in txs),
        booked_at=best_date,
        amount=sum((_to_decimal(tx.amount) for tx in txs), ZERO),
        currency=_clean_text(getattr(summary, "settlement_currency", "")) or _clean_text(txs[0].currency),
        description=description,
        reference=reference,
        payout_id_hint=payout_hints,
    )


def _select_best_single_candidate(
    summary: PayoutSummary,
    candidates: list[BankTransaction],
    *,
    tolerance: Decimal,
    date_window_days: int,
) -> tuple[BankTransaction | None, str, str, str, str, int]:
    if not candidates:
        return None, "missing", "none", "none", "No se encontró movimiento bancario que explique este payout.", 0

    ranked: list[tuple[int, BankTransaction, str, str, str]] = []
    for tx in candidates:
        score, _confidence, reasons = _candidate_score(
            summary,
            tx,
            tolerance=tolerance,
            date_window_days=date_window_days,
        )
        status, match_type, confidence, note = _classify_candidate(
            summary,
            tx,
            tolerance=tolerance,
            date_window_days=date_window_days,
        )
        ranked.append((score, tx, status, match_type, note or reasons))

    ranked.sort(
        key=lambda item: (
            item[0],
            -int(_date_distance_days(summary, item[1]) or 9999),
        ),
        reverse=True,
    )

    best_score, best_tx, best_status, best_match_type, best_note = ranked[0]
    if best_score < 30:
        return None, "missing", "none", "none", "No se encontró movimiento bancario que explique este payout.", best_score

    _, best_confidence, _ = _candidate_score(
        summary,
        best_tx,
        tolerance=tolerance,
        date_window_days=date_window_days,
    )
    return best_tx, best_status, best_match_type, best_confidence, best_note, best_score


def _select_best_combination(
    summary: PayoutSummary,
    candidates: list[BankTransaction],
    *,
    tolerance: Decimal,
    date_window_days: int,
) -> tuple[tuple[BankTransaction, ...] | None, int]:
    expected = _to_decimal(getattr(summary, "net_total", ZERO))
    best_combo: tuple[BankTransaction, ...] | None = None
    best_score = -1

    if len(candidates) < 2:
        return None, best_score

    for size in range(2, min(MAX_COMBINATION_SIZE, len(candidates)) + 1):
        for combo in combinations(candidates, size):
            virtual_tx = _make_virtual_transaction(summary, combo)
            amount_diff = _abs_decimal(_to_decimal(virtual_tx.amount) - expected)
            if amount_diff > max(tolerance, Decimal("5.00")):
                continue

            score, _confidence, _reasons = _candidate_score(
                summary,
                virtual_tx,
                tolerance=tolerance,
                date_window_days=date_window_days,
            )
            score += 8 * (size - 1)
            if amount_diff == ZERO:
                score += 15
            if score > best_score:
                best_score = score
                best_combo = combo

    return best_combo, best_score


def match_payouts_to_bank(
    summaries: Iterable[PayoutSummary],
    bank_transactions: Iterable[BankTransaction],
    *,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
) -> tuple[list[PayoutSummary], list[BankMatch], list[ReconciliationIssue]]:
    summaries_list = list(summaries)
    bank_rows = list(bank_transactions)
    used_bank_ids: set[str] = set()
    matches: list[BankMatch] = []
    issues: list[ReconciliationIssue] = []

    for summary in summaries_list:
        expected = _to_decimal(getattr(summary, "net_total", ZERO))
        summary.bank_expected_amount = expected

        eligible_candidates = [
            tx
            for tx in bank_rows
            if _clean_text(getattr(tx, "id", "")) not in used_bank_ids and _same_currency(summary, tx)
        ]

        chosen, status, match_type, confidence, note, best_score = _select_best_single_candidate(
            summary,
            eligible_candidates,
            tolerance=tolerance,
            date_window_days=date_window_days,
        )

        combo, combo_score = _select_best_combination(
            summary,
            eligible_candidates,
            tolerance=tolerance,
            date_window_days=date_window_days,
        )

        selected_ids: list[str] = []
        if combo is not None and combo_score > best_score:
            virtual_tx = _make_virtual_transaction(summary, combo)
            combo_amount = _to_decimal(virtual_tx.amount)
            combo_diff = _abs_decimal(combo_amount - expected)

            chosen = virtual_tx
            selected_ids = [tx.id for tx in combo]
            if combo_diff == ZERO:
                status = "review"
                match_type = "aggregate_amount_exact"
                confidence = "medium"
                note = "La suma de varios movimientos bancarios explica el payout, pero conviene revisarlo manualmente."
            else:
                status = "review"
                match_type = "aggregate_amount_with_tolerance"
                confidence = "low"
                note = "La suma de varios movimientos bancarios se acerca al payout, pero requiere revisión manual."
        elif chosen is not None:
            selected_ids = [_clean_text(getattr(chosen, "id", ""))]

        bank_amount = _to_decimal(getattr(chosen, "amount", ZERO)) if chosen is not None else None
        difference = None if chosen is None else bank_amount - expected

        bank_tx_id = None
        bank_date = None
        bank_reference = ""
        bank_description = ""

        if chosen is not None:
            bank_tx_id = _clean_text(getattr(chosen, "id", "")) or None
            bank_date = getattr(chosen, "booked_at", None)
            bank_reference = _clean_text(getattr(chosen, "reference", ""))
            bank_description = _clean_text(getattr(chosen, "description", ""))

        match = BankMatch(
            payout_id=_clean_text(getattr(summary, "payout_id", "")),
            settlement_currency=_clean_text(getattr(summary, "settlement_currency", "")),
            stripe_expected_net=expected,
            bank_observed_amount=bank_amount,
            difference=difference,
            status=status,
            match_type=match_type,
            confidence=confidence,
            bank_transaction_id=bank_tx_id,
            bank_date=bank_date,
            bank_reference=bank_reference,
            bank_description=bank_description,
            note=note,
        )
        matches.append(match)
        _update_summary_from_match(summary, match)

        for tx_id in selected_ids:
            if tx_id:
                used_bank_ids.add(tx_id)

        if status == "missing":
            _tighten_status(summary, ReconciliationStatus.REVIEW.value, "sin match bancario")
            _append_unique_issue(
                summary,
                issues,
                ReconciliationIssue(
                    severity=IssueSeverity.MEDIUM.value,
                    code="BANK_MISSING_MATCH",
                    message="No se ha encontrado un movimiento bancario que explique este payout.",
                    payout_id=_clean_text(getattr(summary, "payout_id", "")),
                    suggested_action="Revisar extracto bancario, fecha, importe, moneda y referencia del payout.",
                ),
            )

        elif status == "review":
            _tighten_status(summary, ReconciliationStatus.REVIEW.value, "match bancario con revisión")
            _append_unique_issue(
                summary,
                issues,
                ReconciliationIssue(
                    severity=IssueSeverity.MEDIUM.value,
                    code="BANK_AMOUNT_MISMATCH",
                    message="El movimiento bancario encontrado no coincide de forma suficientemente sólida con el neto esperado del payout.",
                    payout_id=_clean_text(getattr(summary, "payout_id", "")),
                    transaction_id=bank_tx_id,
                    suggested_action="Comprobar timing, ajustes, referencia bancaria y posibles diferencias menores de importe.",
                ),
            )

        elif status == "matched":
            reference_strength = _compute_reference_strength(summary, chosen) if chosen is not None else "none"
            if match_type == "amount_exact" and reference_strength == "none":
                _append_unique_issue(
                    summary,
                    issues,
                    ReconciliationIssue(
                        severity=IssueSeverity.LOW.value,
                        code="BANK_MATCH_BY_AMOUNT",
                        message="El payout cuadra con el banco por importe, pero sin referencia explícita de payout_id.",
                        payout_id=_clean_text(getattr(summary, "payout_id", "")),
                        transaction_id=bank_tx_id,
                        suggested_action="Mantener la referencia bancaria cuando sea posible para una auditoría más clara.",
                    ),
                )

    unmatched_bank_rows = [tx for tx in bank_rows if _clean_text(getattr(tx, "id", "")) not in used_bank_ids]
    for tx in unmatched_bank_rows:
        issues.append(
            ReconciliationIssue(
                severity=IssueSeverity.LOW.value,
                code="BANK_UNUSED_TRANSACTION",
                message="Movimiento bancario no asignado a ningún payout de Stripe en este análisis.",
                payout_id=None,
                transaction_id=_clean_text(getattr(tx, "id", "")),
                suggested_action="Comprobar si pertenece a otro cierre, otra moneda o un payout fuera de este archivo.",
            )
        )

    return summaries_list, matches, issues