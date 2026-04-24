from enum import Enum


class TransactionType(str, Enum):
    CHARGE = "charge"
    REFUND = "refund"
    FEE = "fee"
    PAYOUT = "payout"
    OTHER = "other"


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReconciliationStatus(str, Enum):
    READY = "Listo"
    REVIEW = "Revisar"
    BLOCKED = "Bloqueado"