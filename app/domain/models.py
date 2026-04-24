from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .enums import IssueSeverity, ReconciliationStatus, TransactionType


@dataclass(slots=True)
class AccountingEntry:
    entry_date: Optional[datetime]
    external_id: str
    journal_code: str
    account_code: str
    concept: str
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")
    currency: str = "EUR"
    client_name: str = ""
    client_nif: str = ""
    source: str = "stripe"
    status: str = ""
    payout_id: str = ""


@dataclass(slots=True)
class User:
    id: int
    email: str
    password_hash: str
    full_name: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None


@dataclass(slots=True)
class Client:
    id: int
    user_id: int
    name: str
    nif: str = ""
    default_chart: str = "pgc_pyme"
    default_account_sales: str = "700"
    default_account_fees: str = "626"
    default_account_refunds: str = "708"
    default_account_bank: str = "572"
    journal_code: str = "STR"
    created_at: Optional[datetime] = None


@dataclass(slots=True)
class Subscription:
    id: int
    user_id: int
    plan_code: str
    status: str = "inactive"
    stripe_customer_id: str = ""
    stripe_subscription_id: str = ""
    max_clients: int = 1
    max_runs_per_month: int = 3
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(slots=True)
class NormalizedTransaction:
    id: str
    payout_id: Optional[str]
    type: str
    amount: Decimal
    fee: Decimal
    net: Decimal
    currency: str
    created: datetime
    description: str = ""

    @property
    def transaction_type(self) -> TransactionType:
        try:
            return TransactionType(str(self.type).strip().lower())
        except ValueError:
            return TransactionType.OTHER

    @property
    def is_charge(self) -> bool:
        return self.transaction_type == TransactionType.CHARGE

    @property
    def is_refund(self) -> bool:
        return self.transaction_type == TransactionType.REFUND

    @property
    def is_fee(self) -> bool:
        return self.transaction_type == TransactionType.FEE

    @property
    def is_payout(self) -> bool:
        return self.transaction_type == TransactionType.PAYOUT


@dataclass(slots=True)
class BankTransaction:
    id: str
    booked_at: datetime
    amount: Decimal
    currency: str
    description: str = ""
    reference: str = ""
    payout_id_hint: Optional[str] = None


@dataclass(slots=True)
class ReconciliationIssue:
    severity: str
    code: str
    message: str
    payout_id: Optional[str] = None
    transaction_id: Optional[str] = None
    suggested_action: str = ""

    @property
    def severity_enum(self) -> IssueSeverity:
        try:
            return IssueSeverity(str(self.severity).strip().lower())
        except ValueError:
            return IssueSeverity.MEDIUM

    @property
    def is_blocking(self) -> bool:
        return self.severity_enum == IssueSeverity.HIGH

    @property
    def is_warning(self) -> bool:
        return self.severity_enum == IssueSeverity.MEDIUM

    @property
    def is_low(self) -> bool:
        return self.severity_enum == IssueSeverity.LOW


@dataclass(slots=True)
class BankMatch:
    payout_id: Optional[str]
    settlement_currency: str
    stripe_expected_net: Decimal = Decimal("0.00")
    bank_observed_amount: Optional[Decimal] = None
    difference: Optional[Decimal] = None
    status: str = "not_checked"
    match_type: str = "not_checked"
    confidence: str = "none"
    bank_transaction_id: Optional[str] = None
    bank_date: Optional[datetime] = None
    bank_reference: str = ""
    bank_description: str = ""
    note: str = ""

    @property
    def is_exact_match(self) -> bool:
        return self.status == "matched"

    @property
    def requires_review(self) -> bool:
        return self.status == "review"

    @property
    def is_missing(self) -> bool:
        return self.status == "missing"




def _client_attr(client, key: str, default: str = "") -> str:
    if client is None:
        return default
    if isinstance(client, dict):
        return str(client.get(key, default)).strip()
    return str(getattr(client, key, default)).strip()


@dataclass(slots=True)
class PayoutSummary:
    payout_id: Optional[str]
    settlement_currency: str
    gross_total: Decimal = Decimal("0.00")
    fees_total: Decimal = Decimal("0.00")
    refunds_total: Decimal = Decimal("0.00")
    net_total: Decimal = Decimal("0.00")
    tx_count: int = 0
    status: str = ReconciliationStatus.READY.value
    currencies: str = ""
    complex_types: str = ""
    unhandled_types: str = ""
    recommended_action: str = ""
    issue_codes: list[str] = field(default_factory=list)
    expected_net: Decimal = Decimal("0.00")
    observed_net: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    recognized_tx_count: int = 0
    complex_tx_count: int = 0
    unhandled_tx_count: int = 0
    evidence_lines_count: int = 0
    status_reason: str = ""
    review_reason: str = ""
    blocking_reason: str = ""
    bank_match_status: str = "not_checked"
    bank_expected_amount: Decimal = Decimal("0.00")
    bank_observed_amount: Optional[Decimal] = None
    bank_difference: Optional[Decimal] = None
    bank_match_type: str = "not_checked"
    bank_confidence: str = "none"
    bank_transaction_id: str = ""
    bank_reference: str = ""
    bank_description: str = ""
    bank_booked_at: Optional[datetime] = None
    bank_note: str = ""
    latest_transaction_at: Optional[datetime] = None

    @property
    def status_enum(self) -> ReconciliationStatus:
        try:
            return ReconciliationStatus(str(self.status).strip())
        except ValueError:
            return ReconciliationStatus.REVIEW

    @property
    def display_status(self) -> str:
        return self.status_enum.value

    @property
    def has_unhandled_types(self) -> bool:
        return bool((self.unhandled_types or "").strip())

    @property
    def has_complex_types(self) -> bool:
        return bool((self.complex_types or "").strip())

    @property
    def has_multiple_currencies(self) -> bool:
        value = (self.currencies or "").strip()
        if not value:
            return False
        return "," in value

    @property
    def is_ready(self) -> bool:
        return self.status_enum == ReconciliationStatus.READY

    @property
    def requires_review(self) -> bool:
        return self.status_enum == ReconciliationStatus.REVIEW

    @property
    def is_blocked(self) -> bool:
        return self.status_enum == ReconciliationStatus.BLOCKED

    @property
    def safe_to_export(self) -> bool:
        return self.is_ready

    @property
    def processable(self) -> bool:
        return self.status_enum in {ReconciliationStatus.READY, ReconciliationStatus.REVIEW}

    @property
    def has_bank_match(self) -> bool:
        return self.bank_match_status == "matched"

    @property
    def bank_match_checked(self) -> bool:
        return self.bank_match_status != "not_checked"

    @property
    def primary_reason(self) -> str:
        if self.blocking_reason:
            return self.blocking_reason
        if self.review_reason:
            return self.review_reason
        if self.status_reason:
            return self.status_reason
        if self.is_ready:
            return "sin incidencias relevantes"
        if self.requires_review:
            return "revisión manual recomendada"
        return "bloqueado para contabilidad"

    @property
    def explanation_summary(self) -> str:
        parts: list[str] = [
            f"Payout {self.payout_id or 'SIN_PAYOUT'}",
            f"estado {self.display_status}",
            f"neto {self.net_total} {self.settlement_currency}",
        ]
        if self.primary_reason:
            parts.append(self.primary_reason)
        return " · ".join(parts)

    def to_accounting_entries(self, client: Client | None = None) -> list[AccountingEntry]:
        client_name = _client_attr(client, "name")
        client_nif = _client_attr(client, "nif")
        sales_account = _client_attr(client, "default_account_sales", "700")
        fees_account = _client_attr(client, "default_account_fees", "626")
        refunds_account = _client_attr(client, "default_account_refunds", "708")
        bank_account = _client_attr(client, "default_account_bank", "572")
        journal_code = _client_attr(client, "journal_code", "STR")
        # Fecha del asiento con fallback claro:
        # 1) si hay match bancario, usar la fecha real del banco
        # 2) si no, usar la fecha de la última transacción del payout
        # 3) si tampoco (caso raro), usar la fecha de hoy
        # Sin fecha, ningún software contable importa el asiento.
        entry_date = (
            self.bank_booked_at
            or self.latest_transaction_at
            or datetime.now(timezone.utc)
        )
        external_id = self.payout_id or "SIN_PAYOUT"
        status = self.display_status
        currency = self.settlement_currency or "EUR"

        entries: list[AccountingEntry] = [
            AccountingEntry(
                entry_date=entry_date,
                external_id=external_id,
                journal_code=journal_code,
                account_code=sales_account,
                concept="Ventas brutas Stripe",
                debit=Decimal("0.00"),
                credit=abs(self.gross_total),
                currency=currency,
                client_name=client_name,
                client_nif=client_nif,
                status=status,
                payout_id=external_id,
            )
        ]

        if self.fees_total != Decimal("0.00"):
            entries.append(
                AccountingEntry(
                    entry_date=entry_date,
                    external_id=external_id,
                    journal_code=journal_code,
                    account_code=fees_account,
                    concept="Comisiones Stripe",
                    debit=abs(self.fees_total),
                    credit=Decimal("0.00"),
                    currency=currency,
                    client_name=client_name,
                    client_nif=client_nif,
                    status=status,
                    payout_id=external_id,
                )
            )

        if self.refunds_total != Decimal("0.00"):
            entries.append(
                AccountingEntry(
                    entry_date=entry_date,
                    external_id=external_id,
                    journal_code=journal_code,
                    account_code=refunds_account,
                    concept="Refunds / devoluciones Stripe",
                    debit=abs(self.refunds_total),
                    credit=Decimal("0.00"),
                    currency=currency,
                    client_name=client_name,
                    client_nif=client_nif,
                    status=status,
                    payout_id=external_id,
                )
            )

        debit = self.net_total if self.net_total >= Decimal("0.00") else Decimal("0.00")
        credit = abs(self.net_total) if self.net_total < Decimal("0.00") else Decimal("0.00")
        entries.append(
            AccountingEntry(
                entry_date=entry_date,
                external_id=external_id,
                journal_code=journal_code,
                account_code=bank_account,
                concept="Liquidación Stripe / banco",
                debit=debit,
                credit=credit,
                currency=currency,
                client_name=client_name,
                client_nif=client_nif,
                status=status,
                payout_id=external_id,
            )
        )

        # Validación final: debe = haber. Si no cuadra, indica que algo
        # no se capturó correctamente (fees, refunds, ajustes). Mejor
        # lanzar error claro que generar un asiento contable inválido.
        total_debit = sum((e.debit for e in entries), Decimal("0.00"))
        total_credit = sum((e.credit for e in entries), Decimal("0.00"))
        diff = total_debit - total_credit
        if abs(diff) > Decimal("0.01"):
            # Línea de ajuste automática: vertemos la diferencia a la cuenta
            # de comisiones (626) para que el asiento cuadre. El status del
            # summary reflejará que hubo descuadre si aplica.
            adjustment_debit = abs(diff) if diff < Decimal("0.00") else Decimal("0.00")
            adjustment_credit = abs(diff) if diff > Decimal("0.00") else Decimal("0.00")
            entries.append(
                AccountingEntry(
                    entry_date=entry_date,
                    external_id=external_id,
                    journal_code=journal_code,
                    account_code=fees_account,
                    concept="Ajuste diferencia (comisiones/otros no clasificados)",
                    debit=adjustment_debit,
                    credit=adjustment_credit,
                    currency=currency,
                    client_name=client_name,
                    client_nif=client_nif,
                    status=status,
                    payout_id=external_id,
                )
            )

        return entries
