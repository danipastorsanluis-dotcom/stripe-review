"""
Tests críticos: los asientos contables SIEMPRE deben cuadrar debe = haber.
Si alguno falla, el Excel A3 es inválido y ningún software contable lo importa.
"""
from decimal import Decimal

import pytest

from app.domain.models import Client, PayoutSummary


def _client_fixture(nif="B12345678"):
    return Client(id=1, user_id=1, name="Panadería López SL", nif=nif)


def _make_summary(gross, fees, refunds, net):
    """Construye un PayoutSummary con las cifras dadas."""
    from datetime import datetime, timezone
    return PayoutSummary(
        payout_id="po_test_1",
        settlement_currency="EUR",
        gross_total=Decimal(str(gross)),
        fees_total=Decimal(str(fees)),
        refunds_total=Decimal(str(refunds)),
        net_total=Decimal(str(net)),
        tx_count=3,
        status="Listo",
        latest_transaction_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )


def _assert_accounting_entries_balanced(entries, payout_id):
    """Assert que debe = haber al céntimo."""
    total_debit = sum((e.debit for e in entries), Decimal("0.00"))
    total_credit = sum((e.credit for e in entries), Decimal("0.00"))
    diff = abs(total_debit - total_credit)
    assert diff <= Decimal("0.01"), (
        f"Asiento del payout {payout_id} NO cuadra: "
        f"debe={total_debit} haber={total_credit} diff={diff}"
    )


def test_accounting_entries_balance_simple_charge():
    """Payout simple: 100€ venta - 2.50€ fee = 97.50€ neto."""
    s = _make_summary(gross=100, fees=-2.50, refunds=0, net=97.50)
    entries = s.to_accounting_entries(client=_client_fixture())
    _assert_accounting_entries_balanced(entries, s.payout_id)


def test_accounting_entries_balance_with_refund():
    """Payout con refund."""
    s = _make_summary(gross=1000, fees=-20, refunds=-50, net=930)
    entries = s.to_accounting_entries(client=_client_fixture())
    _assert_accounting_entries_balanced(entries, s.payout_id)


def test_accounting_entries_balance_with_zero_fees_and_diff():
    """
    Regresión del bug reportado: cuando fees_total=0 pero el neto
    no cuadra con gross-refunds, to_accounting_entries debe generar
    una línea de ajuste para que debe=haber.
    Ejemplo real: gross=1949, fees=0, refunds=-50, net=1842.37.
    Diferencia de 56.63€ es ajuste automático.
    """
    s = _make_summary(gross=1949, fees=0, refunds=-50, net=1842.37)
    entries = s.to_accounting_entries(client=_client_fixture())
    _assert_accounting_entries_balanced(entries, s.payout_id)


def test_accounting_entries_balance_negative_net():
    """Payout neto negativo (refunds o disputes grandes)."""
    s = _make_summary(gross=100, fees=-5, refunds=-200, net=-105)
    entries = s.to_accounting_entries(client=_client_fixture())
    _assert_accounting_entries_balanced(entries, s.payout_id)


def test_accounting_entries_have_date():
    """Todos los asientos deben tener fecha. Sin fecha no se importan."""
    s = _make_summary(gross=100, fees=-2.50, refunds=0, net=97.50)
    entries = s.to_accounting_entries(client=_client_fixture())
    for e in entries:
        assert e.entry_date is not None, (
            f"Línea del asiento {s.payout_id} sin fecha. "
            f"No se puede importar en ningún software contable."
        )


def test_accounting_entries_use_client_accounts():
    """Los asientos deben usar las cuentas configuradas en el Client."""
    client = Client(
        id=1, user_id=1, name="Test",
        default_account_sales="705",
        default_account_fees="629",
        default_account_refunds="709",
        default_account_bank="572",
    )
    s = _make_summary(gross=100, fees=-2.50, refunds=0, net=97.50)
    entries = s.to_accounting_entries(client=client)
    accounts = {e.account_code for e in entries}
    assert "705" in accounts, "Debería usar cuenta de ventas del cliente (705)"
    assert "629" in accounts, "Debería usar cuenta de fees del cliente (629)"
    assert "572" in accounts, "Debería usar cuenta de banco del cliente (572)"


def test_accounting_entries_no_client_uses_default_pgc_accounts():
    """Sin cliente, debe usar cuentas PGC por defecto."""
    s = _make_summary(gross=100, fees=-2.50, refunds=0, net=97.50)
    entries = s.to_accounting_entries(client=None)
    accounts = {e.account_code for e in entries}
    assert "700" in accounts or "705" in accounts, "Debería usar cuenta de ventas por defecto"
    assert "626" in accounts or "629" in accounts, "Debería usar cuenta de fees por defecto"
    assert "572" in accounts, "Debería usar cuenta de banco 572"
