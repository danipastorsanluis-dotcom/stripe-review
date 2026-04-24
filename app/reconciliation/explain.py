from __future__ import annotations

from decimal import Decimal, InvalidOperation


ZERO = Decimal("0.00")


def _to_decimal(value) -> Decimal:
    try:
        if value is None or value == "":
            return ZERO
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    return f"{value:.2f}"


def _join_non_empty(parts: list[str], sep: str = "; ") -> str:
    cleaned = [str(p).strip() for p in parts if p and str(p).strip()]
    return sep.join(cleaned)


def _build_causes(summary, issue_codes: list[str]) -> list[str]:
    causes: list[str] = []

    if "MULTICURRENCY" in issue_codes or bool(getattr(summary, "has_multiple_currencies", False)):
        currencies = _clean_text(getattr(summary, "currencies", ""))
        causes.append(f"mezcla de monedas ({currencies})" if currencies else "mezcla de monedas")

    if "NEGATIVE_NET" in issue_codes:
        causes.append("neto negativo")

    if "NO_PAYOUT" in issue_codes:
        causes.append("transacciones sin payout asignado")

    if "EMPTY_PAYOUT_EFFECT" in issue_codes:
        causes.append("sin líneas reconocidas de negocio")

    complex_types = _clean_text(getattr(summary, "complex_types", ""))
    if "COMPLEX_TYPES" in issue_codes or complex_types:
        causes.append(f"tipos complejos presentes ({complex_types})" if complex_types else "tipos complejos presentes")

    unhandled_types = _clean_text(getattr(summary, "unhandled_types", ""))
    if "UNHANDLED_TYPES" in issue_codes or unhandled_types:
        causes.append(f"tipos no tratados ({unhandled_types})" if unhandled_types else "tipos no tratados")

    if int(getattr(summary, "complex_tx_count", 0) or 0) > 0:
        causes.append(f"{int(getattr(summary, 'complex_tx_count', 0) or 0)} líneas complejas")

    if int(getattr(summary, "unhandled_tx_count", 0) or 0) > 0:
        causes.append(f"{int(getattr(summary, 'unhandled_tx_count', 0) or 0)} líneas no tratadas")

    bank_status = _clean_text(getattr(summary, "bank_match_status", "not_checked")).lower()
    bank_match_type = _clean_text(getattr(summary, "bank_match_type", ""))
    bank_note = _clean_text(getattr(summary, "bank_note", ""))

    if bank_status == "matched":
        causes.append(f"match bancario válido ({bank_match_type})" if bank_match_type else "match bancario válido")
    elif bank_status == "review":
        causes.append(f"match bancario con revisión ({bank_match_type})" if bank_match_type else "match bancario con revisión")
    elif bank_status == "missing":
        causes.append("sin correspondencia bancaria razonable")

    if bank_note:
        causes.append(bank_note)

    unique: list[str] = []
    seen: set[str] = set()
    for cause in causes:
        key = cause.lower()
        if key not in seen:
            seen.add(key)
            unique.append(cause)
    return unique


def _build_action(summary) -> str:
    if bool(getattr(summary, "is_blocked", False)):
        return "No exportar todavía. Corregir el payout, revisar las líneas problemáticas y volver a ejecutar la revisión."

    if bool(getattr(summary, "requires_review", False)):
        action_parts: list[str] = []

        if bool(getattr(summary, "has_multiple_currencies", False)):
            action_parts.append("separar o revisar el payout por moneda")
        if bool(getattr(summary, "has_unhandled_types", False)):
            action_parts.append("revisar manualmente los tipos no tratados")
        if bool(getattr(summary, "has_complex_types", False)):
            action_parts.append("validar los tipos complejos antes de exportar")

        bank_status = _clean_text(getattr(summary, "bank_match_status", "not_checked")).lower()
        bank_match_type = _clean_text(getattr(summary, "bank_match_type", ""))
        if bank_status == "missing":
            action_parts.append("comprobar el extracto bancario, la fecha y la referencia del payout")
        elif bank_status == "review":
            if "aggregate" in bank_match_type:
                action_parts.append("validar que varios movimientos bancarios explican realmente el payout")
            else:
                action_parts.append("validar manualmente el match bancario")

        if not action_parts:
            action_parts.append("revisar manualmente antes de exportar")

        return _join_non_empty(action_parts, sep=". ").strip().capitalize() + "."

    return "Se puede revisar y exportar con más confianza."


def build_payout_explanation(summary) -> dict:
    gross = _to_decimal(getattr(summary, "gross_total", 0))
    fees = _to_decimal(getattr(summary, "fees_total", 0))
    refunds = _to_decimal(getattr(summary, "refunds_total", 0))
    expected = _to_decimal(getattr(summary, "expected_net", getattr(summary, "net_total", 0)))
    observed = _to_decimal(getattr(summary, "observed_net", getattr(summary, "net_total", 0)))
    difference = _to_decimal(getattr(summary, "difference", observed - expected))

    bank_expected = _to_decimal(getattr(summary, "bank_expected_amount", expected))
    bank_observed_raw = getattr(summary, "bank_observed_amount", None)
    bank_observed = _to_decimal(bank_observed_raw) if bank_observed_raw is not None else None
    bank_difference_raw = getattr(summary, "bank_difference", None)
    bank_difference = _to_decimal(bank_difference_raw) if bank_difference_raw is not None else None

    bank_status = _clean_text(getattr(summary, "bank_match_status", "not_checked"))
    bank_match_type = _clean_text(getattr(summary, "bank_match_type", ""))
    bank_note = _clean_text(getattr(summary, "bank_note", ""))

    issue_codes = list(getattr(summary, "issue_codes", []) or [])
    review_reason = _clean_text(getattr(summary, "review_reason", ""))
    blocking_reason = _clean_text(getattr(summary, "blocking_reason", ""))
    status_reason = _clean_text(getattr(summary, "status_reason", ""))

    tx_count = int(getattr(summary, "tx_count", 0) or 0)
    recognized_tx_count = int(getattr(summary, "recognized_tx_count", 0) or 0)
    complex_tx_count = int(getattr(summary, "complex_tx_count", 0) or 0)
    unhandled_tx_count = int(getattr(summary, "unhandled_tx_count", 0) or 0)
    evidence_lines_count = int(getattr(summary, "evidence_lines_count", 0) or 0)

    causes = _build_causes(summary, issue_codes)
    causes_text = _join_non_empty(causes) if causes else "sin causa específica detectada"
    action_text = _build_action(summary)
    is_ready = bool(getattr(summary, "is_ready", False)) or _clean_text(getattr(summary, "status", "")) == "Listo"

    if is_ready:
        has_difference = abs(difference) > Decimal("0.01")
        if has_difference:
            executive_summary = (
                f"Payout listo con diferencia {_format_decimal(difference)}. "
                f"Neto esperado {_format_decimal(expected)}, neto observado {_format_decimal(observed)}. "
                f"Revisa fees/refunds antes del cierre."
            )
            explanation = (
                f"Este payout está en estado Listo pero presenta una diferencia de "
                f"{_format_decimal(difference)} entre neto esperado ({_format_decimal(expected)}) "
                f"y neto observado ({_format_decimal(observed)}). "
                f"Ventas brutas {_format_decimal(gross)}, fees {_format_decimal(fees)}, refunds {_format_decimal(refunds)}. "
                f"Transacciones {tx_count}, líneas reconocidas {recognized_tx_count}. "
                f"Suele deberse a fees no clasificadas, ajustes o conversiones FX. "
                f"Revisa el Excel detallado antes de pasarlo a contabilidad."
            )
        else:
            executive_summary = (
                f"Payout listo: cuadra correctamente. Neto esperado {_format_decimal(expected)}, "
                f"neto observado {_format_decimal(observed)}, diferencia Stripe {_format_decimal(difference)}."
            )
            explanation = (
                f"Este payout cuadra correctamente y está listo para exportar. "
                f"Neto esperado {_format_decimal(expected)}, neto observado {_format_decimal(observed)}, "
                f"diferencia Stripe {_format_decimal(difference)}. "
                f"Ventas brutas {_format_decimal(gross)}, fees {_format_decimal(fees)}, refunds {_format_decimal(refunds)}. "
                f"Transacciones {tx_count}, líneas reconocidas {recognized_tx_count}."
            )
    elif bool(getattr(summary, "is_blocked", False)):
        main_reason = blocking_reason or status_reason or "incidencias graves"
        executive_summary = (
            f"Payout bloqueado: no está listo para contabilidad. Diferencia Stripe {_format_decimal(difference)}. "
            f"Motivo principal: {main_reason}."
        )
        explanation = (
            f"Este payout está bloqueado por {main_reason}. "
            f"Neto esperado {_format_decimal(expected)}, neto observado {_format_decimal(observed)}, "
            f"diferencia Stripe {_format_decimal(difference)}. "
            f"Ventas brutas {_format_decimal(gross)}, fees {_format_decimal(fees)}, refunds {_format_decimal(refunds)}. "
            f"Transacciones {tx_count}, líneas reconocidas {recognized_tx_count}, "
            f"líneas complejas {complex_tx_count}, líneas no tratadas {unhandled_tx_count}. "
            f"Causas detectadas: {causes_text}. Acción recomendada: {action_text}"
        )
    else:
        main_reason = review_reason or status_reason or "revisión manual"
        executive_summary = (
            f"Payout en revisión: no conviene exportarlo todavía sin validar. "
            f"Diferencia Stripe {_format_decimal(difference)}. Motivo principal: {main_reason}."
        )
        explanation = (
            f"Este payout requiere revisión por {main_reason}. "
            f"Neto esperado {_format_decimal(expected)}, neto observado {_format_decimal(observed)}, "
            f"diferencia Stripe {_format_decimal(difference)}. "
            f"Ventas brutas {_format_decimal(gross)}, fees {_format_decimal(fees)}, refunds {_format_decimal(refunds)}. "
            f"Transacciones {tx_count}, líneas reconocidas {recognized_tx_count}, líneas complejas {complex_tx_count}, "
            f"líneas no tratadas {unhandled_tx_count}, líneas de evidencia {evidence_lines_count}. "
            f"Causas detectadas: {causes_text}. Acción recomendada: {action_text}"
        )

    if bank_status != "not_checked":
        explanation += (
            f" Banco: esperado {_format_decimal(bank_expected)}, "
            f"observado {_format_decimal(bank_observed) if bank_observed is not None else 'sin match'}, "
            f"diferencia {_format_decimal(bank_difference) if bank_difference is not None else 'sin calcular'}, "
            f"estado {bank_status}"
        )
        if bank_match_type:
            explanation += f" ({bank_match_type})"
        explanation += "."
        if bank_note:
            explanation += f" Nota banco: {bank_note}."
        executive_summary += f" Situación bancaria: {bank_status}."

    if causes and is_ready:
        explanation += f" Observaciones: {causes_text}."

    return {
        "gross_total": str(gross),
        "fees_total": str(fees),
        "refunds_total": str(refunds),
        "expected_net": str(expected),
        "observed_net": str(observed),
        "difference": str(difference),
        "bank_expected_amount": str(bank_expected),
        "bank_observed_amount": "" if bank_observed is None else str(bank_observed),
        "bank_difference": "" if bank_difference is None else str(bank_difference),
        "bank_match_status": bank_status,
        "bank_match_type": bank_match_type,
        "bank_note": bank_note,
        "status_reason": status_reason,
        "review_reason": review_reason,
        "blocking_reason": blocking_reason,
        "causes": causes,
        "action": action_text,
        "executive_summary": executive_summary,
        "explanation": explanation,
    }