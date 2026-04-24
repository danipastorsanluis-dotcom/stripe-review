from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from app.core.config import APP_DB_PATH
from app.domain.enums import ReconciliationStatus
from app.exports.accounting import export_a3_excel, export_accounting_generic_csv
from app.exports.bank_matches_csv import export_bank_matches_csv
from app.exports.bank_matches_xlsx import export_bank_matches_xlsx
from app.exports.generic_csv import export_reconciliation_csv
from app.exports.issues_csv import export_issues_csv
from app.exports.issues_xlsx import export_issues_xlsx
from app.exports.reconciliation_xlsx import export_reconciliation_xlsx
from app.ingestion.bank_mapper import map_bank_dataframe_to_transactions
from app.ingestion.bank_validator import validate_bank_dataframe
from app.ingestion.stripe_mapper import map_dataframe_to_transactions
from app.ingestion.stripe_validator import validate_stripe_dataframe
from app.reconciliation.bank_matching import match_payouts_to_bank
from app.reconciliation.explain import build_payout_explanation
from app.reconciliation.engine import reconcile_payouts
from app.reconciliation.health import build_health_summary
from app.reconciliation.report import build_accounting_summary
from app.services.dataframe_prep import prepare_dataframe
from app.storage.db import connect_db, ensure_tables, insert_artifact, insert_issues, insert_run


BANK_TOLERANCE = Decimal("0.50")


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _display_status_from_status(status: str | None) -> str:
    value = _clean_text(status)

    if value in {
        ReconciliationStatus.READY.value,
        ReconciliationStatus.REVIEW.value,
        ReconciliationStatus.BLOCKED.value,
    }:
        return value

    lowered = value.lower()
    if lowered in {"matched", "ok", "ready"}:
        return ReconciliationStatus.READY.value
    if lowered in {"warning", "review"}:
        return ReconciliationStatus.REVIEW.value
    if lowered in {"issue", "blocked", "error"}:
        return ReconciliationStatus.BLOCKED.value

    return "Desconocido"


def _recommended_action_from_status(status: str | None) -> str:
    display_status = _display_status_from_status(status)

    if display_status == ReconciliationStatus.READY.value:
        return "Se puede exportar."
    if display_status == ReconciliationStatus.REVIEW.value:
        return "Revisar antes de exportar."
    if display_status == ReconciliationStatus.BLOCKED.value:
        return "No exportar todavía."
    return ""


def _build_bank_summary(summaries, bank_used: bool) -> dict[str, Any]:
    if not bank_used:
        return {
            "bank_file_provided": False,
            "bank_check_status": "not_used",
            "bank_matches_count": 0,
            "bank_unmatched_count": 0,
            "bank_review_count": 0,
        }

    matched_count = 0
    unmatched_count = 0
    review_count = 0

    for summary in summaries:
        status = _clean_text(getattr(summary, "bank_match_status", None)).lower()
        if status in {"matched", "ok"}:
            matched_count += 1
        elif status == "review":
            review_count += 1
        else:
            unmatched_count += 1

    if unmatched_count > 0:
        bank_check_status = "missing_matches"
    elif review_count > 0:
        bank_check_status = "partial_review"
    else:
        bank_check_status = "matched_all"

    return {
        "bank_file_provided": True,
        "bank_check_status": bank_check_status,
        "bank_matches_count": matched_count,
        "bank_unmatched_count": unmatched_count,
        "bank_review_count": review_count,
    }


def _build_export_flags(
    summaries,
    issues,
    health: dict[str, Any],
    bank_used: bool,
    bank_summary: dict[str, Any],
) -> dict[str, Any]:
    issue_codes = set()
    has_blocking_issue = False

    for issue in issues:
        code = getattr(issue, "code", None)
        if code is None and isinstance(issue, dict):
            code = issue.get("code")
        if code:
            issue_codes.add(str(code).strip())

        is_blocking = getattr(issue, "is_blocking", None)
        if is_blocking is None and isinstance(issue, dict):
            is_blocking = issue.get("is_blocking", False)
        if bool(is_blocking):
            has_blocking_issue = True

    safe_to_export_count = sum(1 for summary in summaries if bool(getattr(summary, "safe_to_export", False)))
    processable_count = sum(1 for summary in summaries if bool(getattr(summary, "processable", False)))
    total_payouts = len(summaries)

    has_blocked_summary = any(bool(getattr(summary, "is_blocked", False)) for summary in summaries)
    requires_review = any(bool(getattr(summary, "requires_review", False)) for summary in summaries)
    has_blocking_issues = has_blocking_issue or has_blocked_summary

    bank_ready = True
    if bank_used:
        bank_ready = bank_summary["bank_check_status"] == "matched_all"
        if bank_summary["bank_check_status"] == "missing_matches":
            has_blocking_issues = True
        if bank_summary["bank_check_status"] == "partial_review":
            requires_review = True

    can_export_accounting = (
        total_payouts > 0
        and safe_to_export_count == total_payouts
        and not has_blocking_issues
        and not requires_review
        and bank_ready
    )

    return {
        "can_export_accounting": can_export_accounting,
        "requires_review": requires_review,
        "has_blocking_issues": has_blocking_issues,
        "issue_codes": sorted(issue_codes),
        "safe_to_export_count": safe_to_export_count,
        "processable_count": processable_count,
        "total_payouts": total_payouts,
        "accounting_summary_text": build_accounting_summary(health),
    }


def _serialize_summary(summary) -> dict[str, Any]:
    raw_status = getattr(summary, "status", None)
    display_status = getattr(summary, "display_status", None) or _display_status_from_status(raw_status)
    recommended_action = getattr(summary, "recommended_action", None) or _recommended_action_from_status(raw_status)
    explanation_detail = build_payout_explanation(summary)

    return {
        "payout_id": None if summary.payout_id is None else str(summary.payout_id),
        "settlement_currency": None if getattr(summary, "settlement_currency", None) is None else str(summary.settlement_currency),
        "gross_total": str(summary.gross_total),
        "fees_total": str(summary.fees_total),
        "refunds_total": str(summary.refunds_total),
        "net_total": str(summary.net_total),
        "expected_net": str(getattr(summary, "expected_net", "0.00")),
        "observed_net": str(getattr(summary, "observed_net", "0.00")),
        "difference": str(getattr(summary, "difference", "0.00")),
        "bank_expected_amount": str(getattr(summary, "bank_expected_amount", "0.00")),
        "bank_observed_amount": "" if getattr(summary, "bank_observed_amount", None) is None else str(summary.bank_observed_amount),
        "bank_difference": "" if getattr(summary, "bank_difference", None) is None else str(summary.bank_difference),
        "bank_match_status": str(getattr(summary, "bank_match_status", "not_checked")),
        "bank_match_type": str(getattr(summary, "bank_match_type", "not_checked")),
        "bank_confidence": str(getattr(summary, "bank_confidence", "none")),
        "bank_transaction_id": str(getattr(summary, "bank_transaction_id", "")).strip(),
        "bank_reference": str(getattr(summary, "bank_reference", "")).strip(),
        "bank_description": str(getattr(summary, "bank_description", "")).strip(),
        "bank_booked_at": "" if getattr(summary, "bank_booked_at", None) is None else str(summary.bank_booked_at),
        "bank_note": getattr(summary, "bank_note", ""),
        "tx_count": int(summary.tx_count),
        "recognized_tx_count": int(getattr(summary, "recognized_tx_count", 0)),
        "complex_tx_count": int(getattr(summary, "complex_tx_count", 0)),
        "unhandled_tx_count": int(getattr(summary, "unhandled_tx_count", 0)),
        "evidence_lines_count": int(getattr(summary, "evidence_lines_count", 0)),
        "status": None if raw_status is None else str(raw_status),
        "display_status": display_status,
        "recommended_action": recommended_action,
        "currencies": None if summary.currencies is None else str(summary.currencies),
        "has_unhandled_types": bool(getattr(summary, "has_unhandled_types", False)),
        "has_complex_types": bool(getattr(summary, "has_complex_types", False)),
        "complex_types": None if getattr(summary, "complex_types", None) is None else str(summary.complex_types),
        "unhandled_types": None if summary.unhandled_types is None else str(summary.unhandled_types),
        "safe_to_export": bool(getattr(summary, "safe_to_export", False)),
        "processable": bool(getattr(summary, "processable", False)),
        "status_reason": getattr(summary, "status_reason", ""),
        "review_reason": getattr(summary, "review_reason", ""),
        "blocking_reason": getattr(summary, "blocking_reason", ""),
        "primary_reason": getattr(summary, "primary_reason", ""),
        "explanation_summary": getattr(summary, "explanation_summary", ""),
        "issue_codes": list(getattr(summary, "issue_codes", []) or []),
        "explanation_detail": explanation_detail,
    }


def _serialize_issue(issue) -> dict[str, Any]:
    return {
        "severity": None if issue.severity is None else str(issue.severity),
        "code": None if issue.code is None else str(issue.code),
        "message": None if issue.message is None else str(issue.message),
        "payout_id": None if issue.payout_id is None else str(issue.payout_id),
        "transaction_id": None if getattr(issue, "transaction_id", None) is None else str(issue.transaction_id),
        "suggested_action": "" if issue.suggested_action is None else str(issue.suggested_action),
        "is_blocking": bool(getattr(issue, "is_blocking", False)),
    }


def _serialize_bank_match(match) -> dict[str, Any]:
    return {
        "payout_id": None if match.payout_id is None else str(match.payout_id),
        "settlement_currency": str(match.settlement_currency),
        "stripe_expected_net": str(match.stripe_expected_net),
        "bank_observed_amount": "" if match.bank_observed_amount is None else str(match.bank_observed_amount),
        "difference": "" if match.difference is None else str(match.difference),
        "status": str(match.status),
        "match_type": str(match.match_type),
        "confidence": str(match.confidence),
        "bank_transaction_id": "" if match.bank_transaction_id is None else str(match.bank_transaction_id),
        "bank_date": "" if match.bank_date is None else str(match.bank_date),
        "bank_reference": str(match.bank_reference),
        "bank_description": str(match.bank_description),
        "note": str(match.note),
    }


def process_file(
    input_path: str,
    output_dir: str,
    bank_input_path: str | None = None,
    *,
    user_id: int,
    client_id: int | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    # user_id es obligatorio y debe ser > 0. No se permite procesar sin usuario
    # autenticado, para evitar runs huérfanos descargables por cualquiera.
    if not user_id or int(user_id) <= 0:
        raise ValueError("user_id es obligatorio y debe ser un id válido")

    if not input_path or not os.path.exists(input_path):
        raise FileNotFoundError(f"No existe el archivo de entrada: {input_path}")
    if bank_input_path and not os.path.exists(bank_input_path):
        raise FileNotFoundError(f"No existe el archivo bancario: {bank_input_path}")

    os.makedirs(output_dir, exist_ok=True)

    stripe_df = prepare_dataframe(input_path)
    detected_format = validate_stripe_dataframe(stripe_df)
    transactions = map_dataframe_to_transactions(stripe_df)
    if not transactions:
        raise ValueError("No se han podido mapear transacciones válidas desde el archivo")

    summaries, issues = reconcile_payouts(transactions)
    bank_matches = []
    bank_detected_format = None
    bank_transactions = []
    bank_used = bool(bank_input_path)

    if bank_used:
        bank_df = prepare_dataframe(bank_input_path)
        bank_detected_format = validate_bank_dataframe(bank_df)
        bank_transactions = map_bank_dataframe_to_transactions(bank_df)
        summaries, bank_matches, bank_issues = match_payouts_to_bank(
            summaries,
            bank_transactions,
            tolerance=BANK_TOLERANCE,
        )
        issues.extend(bank_issues)

    health = build_health_summary(summaries, issues)
    bank_summary = _build_bank_summary(summaries, bank_used=bank_used)
    export_flags = _build_export_flags(
        summaries,
        issues,
        health,
        bank_used=bank_used,
        bank_summary=bank_summary,
    )

    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)

        notes = "Revisión del archivo de Stripe previa a contabilidad."
        if bank_used:
            notes += " Incluye matching bancario por referencia, importe, moneda y combinaciones simples de movimientos."
        else:
            notes += " No incluye matching bancario real."

        run_id = insert_run(
            con,
            user_id=user_id,
            client_id=client_id,
            input_path=input_path,
            detected_format=detected_format,
            transactions_count=len(transactions),
            payouts_count=len(summaries),
            issues_count=len(issues),
            matched_count=health["matched_count"],
            warning_count=health["warning_count"],
            issue_count=health["issue_count"],
            notes=notes,
        )

        reconciliation_csv_path = os.path.join(output_dir, f"run_{run_id}_reconciliation.csv")
        issues_csv_path = os.path.join(output_dir, f"run_{run_id}_issues.csv")
        reconciliation_xlsx_path = os.path.join(output_dir, f"run_{run_id}_reconciliation.xlsx")
        issues_xlsx_path = os.path.join(output_dir, f"run_{run_id}_issues.xlsx")
        accounting_csv_path = None
        accounting_xlsx_path = None
        bank_matches_csv_path = None
        bank_matches_xlsx_path = None

        export_reconciliation_csv(summaries, reconciliation_csv_path)
        export_issues_csv(issues, issues_csv_path)
        reconciliation_xlsx_path = export_reconciliation_xlsx(summaries, reconciliation_xlsx_path)
        issues_xlsx_path = export_issues_xlsx(issues, issues_xlsx_path)

        insert_artifact(con, run_id=run_id, artifact_type="reconciliation_csv", file_path=reconciliation_csv_path)
        insert_artifact(con, run_id=run_id, artifact_type="issues_csv", file_path=issues_csv_path)
        insert_artifact(con, run_id=run_id, artifact_type="reconciliation_xlsx", file_path=reconciliation_xlsx_path)
        insert_artifact(con, run_id=run_id, artifact_type="issues_xlsx", file_path=issues_xlsx_path)

        if bank_matches:
            bank_matches_csv_path = os.path.join(output_dir, f"run_{run_id}_bank_matches.csv")
            bank_matches_xlsx_path = os.path.join(output_dir, f"run_{run_id}_bank_matches.xlsx")
            export_bank_matches_csv(bank_matches, bank_matches_csv_path)
            bank_matches_xlsx_path = export_bank_matches_xlsx(bank_matches, bank_matches_xlsx_path)
            insert_artifact(con, run_id=run_id, artifact_type="bank_matches_csv", file_path=bank_matches_csv_path)
            insert_artifact(con, run_id=run_id, artifact_type="bank_matches_xlsx", file_path=bank_matches_xlsx_path)

        if export_flags["can_export_accounting"]:
            accounting_csv_path = os.path.join(output_dir, f"run_{run_id}_accounting_generic.csv")
            accounting_xlsx_path = os.path.join(output_dir, f"run_{run_id}_a3_excel.xlsx")
            export_accounting_generic_csv(summaries, accounting_csv_path, client=client)
            accounting_xlsx_path = export_a3_excel(summaries, accounting_xlsx_path, client=client)
            insert_artifact(con, run_id=run_id, artifact_type="accounting_csv", file_path=accounting_csv_path)
            insert_artifact(con, run_id=run_id, artifact_type="accounting_xlsx", file_path=accounting_xlsx_path)

        insert_issues(con, run_id=run_id, issues=issues)
    finally:
        con.close()

    return {
        "run_id": run_id,
        "detected_format": detected_format,
        "bank_detected_format": bank_detected_format,
        "transactions_count": len(transactions),
        "bank_transactions_count": len(bank_transactions),
        "payouts_count": len(summaries),
        "issues_count": len(issues),
        "health": health,
        "bank_used": bank_used,
        "bank_file_provided": bank_summary["bank_file_provided"],
        "bank_check_status": bank_summary["bank_check_status"],
        "bank_matches_count": bank_summary["bank_matches_count"],
        "bank_unmatched_count": bank_summary["bank_unmatched_count"],
        "bank_review_count": bank_summary["bank_review_count"],
        "can_export_accounting": export_flags["can_export_accounting"],
        "requires_review": export_flags["requires_review"],
        "has_blocking_issues": export_flags["has_blocking_issues"],
        "issue_codes": export_flags["issue_codes"],
        "safe_to_export_count": export_flags["safe_to_export_count"],
        "processable_count": export_flags["processable_count"],
        "total_payouts": export_flags["total_payouts"],
        "accounting_summary_text": export_flags["accounting_summary_text"],
        "preview": {
            "summaries": [_serialize_summary(summary) for summary in summaries],
            "issues": [_serialize_issue(issue) for issue in issues],
            "bank_matches": [_serialize_bank_match(match) for match in bank_matches],
        },
    }