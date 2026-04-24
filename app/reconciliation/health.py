from typing import Dict


READY_STATUSES = {"Listo", "matched", "ok", "ready", "safe"}
REVIEW_STATUSES = {"Revisar", "warning", "review"}
BLOCKED_STATUSES = {"Bloqueado", "issue", "blocked", "error"}


def _extract_status(summary) -> str:
    status = getattr(summary, "status", None)
    if status is None and isinstance(summary, dict):
        status = summary.get("status")
    return "" if status is None else str(status).strip()


def _extract_code(issue) -> str:
    code = getattr(issue, "code", None)
    if code is None and isinstance(issue, dict):
        code = issue.get("code")
    return "" if code is None else str(code).strip()


def _extract_bool(obj, attr_name: str, default: bool = False) -> bool:
    value = getattr(obj, attr_name, None)
    if value is None and isinstance(obj, dict):
        value = obj.get(attr_name, default)
    return bool(value)


def _summary_is_ready(summary) -> bool:
    if _extract_bool(summary, "is_ready"):
        return True
    return _extract_status(summary) in READY_STATUSES


def _summary_requires_review(summary) -> bool:
    if _extract_bool(summary, "requires_review"):
        return True
    return _extract_status(summary) in REVIEW_STATUSES


def _summary_is_blocked(summary) -> bool:
    if _extract_bool(summary, "is_blocked"):
        return True
    return _extract_status(summary) in BLOCKED_STATUSES


def _summary_safe_to_export(summary) -> bool:
    if _extract_bool(summary, "safe_to_export"):
        return True
    return _summary_is_ready(summary)


def _summary_processable(summary) -> bool:
    if _extract_bool(summary, "processable"):
        return True
    return _summary_is_ready(summary) or _summary_requires_review(summary)


def _issue_identity(issue) -> tuple[str, str, str]:
    code = _extract_code(issue)

    payout_id = getattr(issue, "payout_id", None)
    if payout_id is None and isinstance(issue, dict):
        payout_id = issue.get("payout_id")
    payout_id = "" if payout_id is None else str(payout_id).strip()

    transaction_id = getattr(issue, "transaction_id", None)
    if transaction_id is None and isinstance(issue, dict):
        transaction_id = issue.get("transaction_id")
    transaction_id = "" if transaction_id is None else str(transaction_id).strip()

    return code, payout_id, transaction_id


def build_health_summary(summaries, issues) -> Dict:
    matched_count = 0
    warning_count = 0
    issue_count = 0

    multicurrency_count = 0
    unassigned_count = 0
    negative_net_count = 0
    complex_types_count = 0
    unhandled_types_count = 0
    empty_payout_effect_count = 0
    bank_matched_count = 0
    bank_review_count = 0
    bank_missing_count = 0
    bank_unused_count = 0

    for summary in summaries:
        if _summary_is_ready(summary):
            matched_count += 1
        elif _summary_requires_review(summary):
            warning_count += 1
        elif _summary_is_blocked(summary):
            issue_count += 1

        bank_status = getattr(summary, "bank_match_status", "not_checked")
        if bank_status == "matched":
            bank_matched_count += 1
        elif bank_status == "review":
            bank_review_count += 1
        elif bank_status == "missing":
            bank_missing_count += 1

    seen_issue_keys = set()

    for issue in issues:
        identity = _issue_identity(issue)
        if identity in seen_issue_keys:
            continue
        seen_issue_keys.add(identity)

        code = identity[0]

        if code == "MULTICURRENCY":
            multicurrency_count += 1
        elif code == "NO_PAYOUT":
            unassigned_count += 1
        elif code == "NEGATIVE_NET":
            negative_net_count += 1
        elif code == "COMPLEX_TYPES":
            complex_types_count += 1
        elif code == "UNHANDLED_TYPES":
            unhandled_types_count += 1
        elif code == "EMPTY_PAYOUT_EFFECT":
            empty_payout_effect_count += 1
        elif code == "BANK_UNUSED_TRANSACTION":
            bank_unused_count += 1

    total_payouts = len(summaries)
    processable_count = sum(1 for summary in summaries if _summary_processable(summary))
    safe_to_export_count = sum(1 for summary in summaries if _summary_safe_to_export(summary))
    export_recommended = issue_count == 0 and warning_count == 0

    return {
        "matched_count": matched_count,
        "warning_count": warning_count,
        "issue_count": issue_count,
        "multicurrency_count": multicurrency_count,
        "unassigned_count": unassigned_count,
        "negative_net_count": negative_net_count,
        "complex_types_count": complex_types_count,
        "unhandled_types_count": unhandled_types_count,
        "empty_payout_effect_count": empty_payout_effect_count,
        "bank_matched_count": bank_matched_count,
        "bank_review_count": bank_review_count,
        "bank_missing_count": bank_missing_count,
        "bank_unused_count": bank_unused_count,
        "total_payouts": total_payouts,
        "processable_count": processable_count,
        "safe_to_export_count": safe_to_export_count,
        "export_recommended": export_recommended,
    }
