from datetime import datetime
from decimal import Decimal

from app.domain.enums import TransactionType
from app.domain.models import NormalizedTransaction
from app.reconciliation.engine import reconcile_payouts
from app.reconciliation.explain import build_payout_explanation


def _tx(
    *,
    tx_id: str,
    payout_id: str | None,
    tx_type: str,
    amount: str,
    fee: str,
    net: str,
    currency: str = "EUR",
    description: str = "",
) -> NormalizedTransaction:
    return NormalizedTransaction(
        id=tx_id,
        payout_id=payout_id,
        type=tx_type,
        amount=Decimal(amount),
        fee=Decimal(fee),
        net=Decimal(net),
        currency=currency,
        created=datetime(2026, 1, 1),
        description=description,
    )


def test_reconcile_basic_payout():
    transactions = [
        _tx(tx_id="tx_1", payout_id="po_1", tx_type=TransactionType.CHARGE.value, amount="100.00", fee="0.00", net="100.00"),
        _tx(tx_id="tx_2", payout_id="po_1", tx_type=TransactionType.FEE.value, amount="0.00", fee="-1.50", net="-1.50"),
        _tx(tx_id="tx_3", payout_id="po_1", tx_type=TransactionType.REFUND.value, amount="-10.00", fee="0.00", net="-10.00"),
    ]

    summaries, issues = reconcile_payouts(transactions)

    assert len(summaries) == 1
    summary = summaries[0]

    assert summary.payout_id == "po_1"
    assert summary.gross_total == Decimal("100.00")
    assert summary.fees_total == Decimal("-1.50")
    assert summary.refunds_total == Decimal("-10.00")
    assert summary.net_total == Decimal("88.50")
    assert summary.expected_net == Decimal("88.50")
    assert summary.observed_net == Decimal("88.50")
    assert summary.difference == Decimal("0.00")
    assert summary.status == "Listo"
    assert summary.safe_to_export is True
    assert len(issues) == 0

    explanation = build_payout_explanation(summary)
    assert explanation["difference"] == "0.00"
    assert "cuadra correctamente" in explanation["explanation"].lower()


def test_reconcile_unhandled_types_generates_review():
    transactions = [
        _tx(tx_id="tx_1", payout_id="po_2", tx_type=TransactionType.CHARGE.value, amount="120.00", fee="0.00", net="120.00"),
        _tx(tx_id="tx_2", payout_id="po_2", tx_type=TransactionType.OTHER.value, amount="-20.00", fee="0.00", net="-20.00", description="Adjustment"),
    ]

    summaries, issues = reconcile_payouts(transactions)

    assert len(summaries) == 1
    summary = summaries[0]

    assert summary.status == "Revisar"
    assert summary.has_unhandled_types is True
    assert summary.unhandled_types == "other"
    assert any(issue.code == "UNHANDLED_TYPES" for issue in issues)


def test_reconcile_no_payout_generates_blocked():
    transactions = [
        _tx(tx_id="tx_1", payout_id=None, tx_type=TransactionType.CHARGE.value, amount="50.00", fee="0.00", net="50.00")
    ]

    summaries, issues = reconcile_payouts(transactions)

    assert len(summaries) == 1
    summary = summaries[0]

    assert summary.payout_id == "SIN_PAYOUT"
    assert summary.status == "Bloqueado"
    assert summary.safe_to_export is False
    assert any(issue.code == "NO_PAYOUT" for issue in issues)


def test_reconcile_multicurrency_generates_review_and_issue():
    transactions = [
        _tx(tx_id="tx_1", payout_id="po_3", tx_type=TransactionType.CHARGE.value, amount="80.00", fee="0.00", net="80.00", currency="EUR"),
        _tx(tx_id="tx_2", payout_id="po_3", tx_type=TransactionType.CHARGE.value, amount="20.00", fee="0.00", net="20.00", currency="USD"),
    ]

    summaries, issues = reconcile_payouts(transactions)

    assert len(summaries) == 2
    assert all(summary.status == "Revisar" for summary in summaries)
    assert any(issue.code == "MULTICURRENCY" for issue in issues)