from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

import pandas as pd

from app.core.utils import safe_decimal
from app.domain.enums import TransactionType
from app.domain.models import NormalizedTransaction


ZERO = Decimal("0.00")


def _normalize_column_name(value: str) -> str:
    return (
        str(value)
        .replace("\ufeff", "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        renamed[col] = _normalize_column_name(col)
    return df.rename(columns=renamed)


def _normalize_optional_text(value) -> Optional[str]:
    text = str(value).strip()
    if text in ("", "nan", "None", "NONE", "NULL"):
        return None
    return text


def _normalize_currency(value) -> str:
    text = _normalize_optional_text(value)
    if not text:
        return "EUR"
    return text.upper()


def _normalize_payout_id(value) -> Optional[str]:
    return _normalize_optional_text(value)


def _pick_first_present(row, candidates):
    for name in candidates:
        if name in row.index:
            value = row.get(name)
            if _normalize_optional_text(value) is not None:
                return value
    return None


def _parse_date(value) -> datetime:
    text = str(value).strip()

    if text in ("", "nan", "None", "NONE", "NULL"):
        raise ValueError(f"Fecha inválida: {value}")

    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    raise ValueError(f"Fecha inválida: {value}")


def _normalize_stripe_type(raw_type: str) -> str:
    t = (raw_type or "").strip().lower()

    if t in ("charge", "payment", "payment_intent", "payment_capture", "charges"):
        return TransactionType.CHARGE.value

    if t in ("refund", "payment_refund", "refund_failure", "refunds"):
        return TransactionType.REFUND.value

    if t in ("fee", "stripe_fee", "application_fee", "application_fee_refund", "fees"):
        return TransactionType.FEE.value

    if t in ("payout", "payout_cancel", "payouts"):
        return TransactionType.PAYOUT.value

    fine_map = {
        "adjustment": "adjustment",
        "advance": "advance",
        "advance_funding": "advance_funding",
        "anticipation_repayment": "anticipation_repayment",
        "authorization_hold": "authorization_hold",
        "authorization_release": "authorization_release",
        "balance_payment_debit": "balance_payment_debit",
        "balance_payment_debit_reversal": "balance_payment_debit_reversal",
        "charge_failure": "charge_failure",
        "chargeback": "chargeback",
        "connect_collection_transfer": "connect_collection_transfer",
        "dispute": "dispute",
        "network_cost": "network_fee",
        "network_fee": "network_fee",
        "obligation_outbound": "obligation_outbound",
        "obligation_reversal_inbound": "obligation_reversal_inbound",
        "payout_failure": "payout_failure",
        "reserve_hold": "reserve_hold",
        "reserve_release": "reserve_release",
        "reserve_transaction": "reserve_transaction",
        "reserved_funds": "reserved_funds",
        "risk_reserved_funds": "risk_reserved_funds",
        "risk_reserved_funds_release": "risk_reserved_funds_release",
        "tax_fee": "tax_fee",
        "topup": "topup",
        "topup_reversal": "topup_reversal",
        "transfer": "transfer",
        "transfer_cancel": "transfer_cancel",
        "transfer_failure": "transfer_failure",
        "transfer_refund": "transfer_refund",
        "other": TransactionType.OTHER.value,
        "unknown": "unknown",
    }

    return fine_map.get(t, t or "unknown")


def _normalize_reporting_category(category: str) -> str:
    c = (category or "").strip().lower()

    if c in ("charge", "charges", "charge_failure", "payment", "payments"):
        return TransactionType.CHARGE.value

    if c in ("refund", "refunds", "dispute_reversal"):
        return TransactionType.REFUND.value

    if c in ("fee", "fees", "stripe_fee", "application_fee"):
        return TransactionType.FEE.value

    if c in ("payout", "payouts"):
        return TransactionType.PAYOUT.value

    fine_map = {
        "adjustment": "adjustment",
        "chargeback": "chargeback",
        "dispute": "dispute",
        "network_cost": "network_fee",
        "network_fee": "network_fee",
        "other": TransactionType.OTHER.value,
        "reserve_transaction": "reserve_transaction",
        "reserved_funds": "reserved_funds",
        "risk_reserved_funds": "risk_reserved_funds",
        "risk_reserved_funds_release": "risk_reserved_funds_release",
        "tax_fee": "tax_fee",
        "topup": "topup",
        "topup_reversal": "topup_reversal",
        "transfer": "transfer",
        "unknown": "unknown",
    }

    return fine_map.get(c, c or "unknown")


def _infer_type_from_description(description: str, amount: Decimal, fee: Decimal) -> str:
    desc = (description or "").strip().lower()

    if any(x in desc for x in ["refund", "refunded", "devol", "reembolso"]):
        return TransactionType.REFUND.value

    if any(
        x in desc
        for x in [
            "fee",
            "fees",
            "stripe fee",
            "comisión",
            "comision",
            "commission",
            "network fee",
        ]
    ):
        return TransactionType.FEE.value

    if any(x in desc for x in ["payout", "transfer to bank", "bank transfer"]):
        return TransactionType.PAYOUT.value

    if any(x in desc for x in ["adjustment", "dispute", "chargeback"]):
        if "chargeback" in desc:
            return "chargeback"
        if "dispute" in desc:
            return "dispute"
        return "adjustment"

    if amount < ZERO and fee == ZERO:
        return TransactionType.REFUND.value

    if amount == ZERO and fee < ZERO:
        return TransactionType.FEE.value

    if amount > ZERO:
        return TransactionType.CHARGE.value

    return "unknown"


def _map_legacy_row(row) -> NormalizedTransaction:
    amount = safe_decimal(row["amount"])
    fee = safe_decimal(row["fee"])
    net = safe_decimal(row["net"])
    description = str(row["description"]).strip()

    return NormalizedTransaction(
        id=str(row["id"]).strip(),
        payout_id=_normalize_payout_id(row["payout_id"]) if "payout_id" in row.index else None,
        type=_infer_type_from_description(description=description, amount=amount, fee=fee),
        amount=amount,
        fee=fee,
        net=net,
        currency="EUR",
        created=_parse_date(row["created"]),
        description=description,
    )


def _map_realistic_row(row) -> NormalizedTransaction:
    amount = safe_decimal(row["amount"])
    fee = safe_decimal(row["fee"])
    net = safe_decimal(row["net"])
    description = str(row["description"]).strip()
    raw_type = str(row["type"]).strip()

    return NormalizedTransaction(
        id=str(row["id"]).strip(),
        payout_id=_normalize_payout_id(row["payout_id"]) if "payout_id" in row.index else None,
        type=_normalize_stripe_type(raw_type),
        amount=amount,
        fee=fee,
        net=net,
        currency=_normalize_currency(row["currency"]),
        created=_parse_date(row["created"]),
        description=description,
    )


def _map_docs_payout_row(row) -> NormalizedTransaction:
    amount = safe_decimal(row["gross"])
    fee = safe_decimal(row["fee"])
    net = safe_decimal(row["net"])
    description = str(row["description"]).strip()
    reporting_category = str(row["reporting_category"]).strip()

    tx_id = _normalize_optional_text(row.get("balance_transaction_id"))
    if not tx_id:
        tx_id = _normalize_optional_text(row.get("source_id"))
    if not tx_id:
        tx_id = "UNKNOWN_TX"

    created_value = _pick_first_present(
        row,
        ["created", "created_utc", "available_on_utc", "available_on"],
    )

    return NormalizedTransaction(
        id=tx_id,
        payout_id=_normalize_payout_id(row["automatic_payout_id"]),
        type=_normalize_reporting_category(reporting_category),
        amount=amount,
        fee=fee,
        net=net,
        currency=_normalize_currency(row["currency"]),
        created=_parse_date(created_value),
        description=description,
    )


def _map_docs_balance_row(row) -> NormalizedTransaction:
    amount = safe_decimal(row["gross"])
    fee = safe_decimal(row["fee"])
    net = safe_decimal(row["net"])
    description = str(row["description"]).strip()
    reporting_category = str(row["reporting_category"]).strip()

    tx_id = _normalize_optional_text(row.get("balance_transaction_id"))
    if not tx_id:
        tx_id = _normalize_optional_text(row.get("charge_id"))
    if not tx_id:
        tx_id = _normalize_optional_text(row.get("source_id"))
    if not tx_id:
        tx_id = "UNKNOWN_TX"

    created_value = _pick_first_present(
        row,
        ["charge_created_utc", "created_utc", "created", "available_on_utc", "available_on"],
    )

    return NormalizedTransaction(
        id=tx_id,
        payout_id=_normalize_payout_id(row["automatic_payout_id"]),
        type=_normalize_reporting_category(reporting_category),
        amount=amount,
        fee=fee,
        net=net,
        currency=_normalize_currency(row["currency"]),
        created=_parse_date(created_value),
        description=description,
    )


def _looks_like_docs_payout(df: pd.DataFrame) -> bool:
    required = {
        "automatic_payout_id",
        "balance_transaction_id",
        "gross",
        "fee",
        "net",
        "reporting_category",
        "created",
        "currency",
        "description",
    }
    return required.issubset(set(df.columns))


def _looks_like_docs_balance(df: pd.DataFrame) -> bool:
    required = {
        "automatic_payout_id",
        "balance_transaction_id",
        "gross",
        "fee",
        "net",
        "reporting_category",
        "currency",
        "description",
    }
    if not required.issubset(set(df.columns)):
        return False

    created_candidates = {"charge_created_utc", "created_utc", "created"}
    return len(created_candidates.intersection(set(df.columns))) > 0


def _looks_like_realistic(df: pd.DataFrame) -> bool:
    required = {
        "id",
        "type",
        "amount",
        "fee",
        "net",
        "currency",
        "created",
        "description",
    }
    return required.issubset(set(df.columns))


def _looks_like_legacy(df: pd.DataFrame) -> bool:
    required = {"id", "amount", "fee", "net", "description", "created"}
    return required.issubset(set(df.columns))


def _apply_aliases(df: pd.DataFrame) -> pd.DataFrame:
    alias_groups = {
        "id": ["id", "transaction_id", "balance_transaction_id", "source_id"],
        "payout_id": ["payout_id", "automatic_payout_id", "payout"],
        "type": ["type", "reporting_category", "transaction_type"],
        "amount": ["amount", "gross"],
        "fee": ["fee", "stripe_fee"],
        "net": ["net"],
        "currency": ["currency", "settlement_currency"],
        "created": ["created", "created_utc", "charge_created_utc", "available_on_utc", "available_on"],
        "description": ["description", "memo", "details"],
    }

    out = df.copy()

    for canonical, aliases in alias_groups.items():
        if canonical in out.columns:
            continue
        for alias in aliases:
            if alias in out.columns:
                out[canonical] = out[alias]
                break

    return out


def map_dataframe_to_transactions(df: pd.DataFrame) -> list[NormalizedTransaction]:
    if df is None or df.empty:
        return []

    df = _normalize_dataframe_columns(df)
    df = _apply_aliases(df)

    transactions: list[NormalizedTransaction] = []

    if _looks_like_docs_balance(df):
        for _, row in df.iterrows():
            transactions.append(_map_docs_balance_row(row))
        return transactions

    if _looks_like_docs_payout(df):
        for _, row in df.iterrows():
            transactions.append(_map_docs_payout_row(row))
        return transactions

    if _looks_like_realistic(df):
        for _, row in df.iterrows():
            transactions.append(_map_realistic_row(row))
        return transactions

    if _looks_like_legacy(df):
        for _, row in df.iterrows():
            transactions.append(_map_legacy_row(row))
        return transactions

    raise ValueError(
        "No se ha podido mapear el DataFrame a transacciones normalizadas. "
        f"Columnas detectadas: {list(df.columns)}"
    )