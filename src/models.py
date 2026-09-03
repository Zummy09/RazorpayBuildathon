from enum import Enum
from datetime import datetime
from datetime import date
from pydantic import BaseModel, Field

# Payments


class Method(str, Enum):
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"


class PaymentStatus(str, Enum):
    CAPTURED = "captured"
    AUTHORIZED = "authorized"
    FAILED = "failed"


class Payment(BaseModel):
    payment_id: str
    order_id: str
    amount_paise: int = Field(gt=0)
    method: Method
    status: PaymentStatus
    captured_at: datetime


# Refunds


class Refund(BaseModel):
    refund_id: str
    payment_id: str
    amount_paise: int = Field(gt=0)
    created_at: datetime


# Chargebacks -- bank-initiated reversals. never written to the merchant's
# data files, which is what makes them unexplainable from those records.


class Chargeback(BaseModel):
    chargeback_id: str
    payment_id: str
    amount_paise: int = Field(gt=0)
    raised_at: datetime


# Settlements


class Settlement(BaseModel):
    settlement_id: str
    utr: str
    net_amount_paise: int
    settled_at: datetime


# Reconciliation


class ReconStatus(str, Enum):
    MATCHED = "matched"
    EXCEPTION = "exception"


class ReconResult(BaseModel):
    settlement_id: str
    settled_on: date
    expected_paise: int
    actual_paise: int
    gap_paise: int
    status: ReconStatus
    payment_ids: list[str]
    refund_ids: list[str]


# Classification


class Cause(str, Enum):
    OLD_CYCLE_REFUND = "old_cycle_refund"
    CHARGEBACK = "chargeback"
    ROUNDING = "rounding"
    UNKNOWN = "unknown"


class CauseAttribution(BaseModel):
    """One cause, and how much of the gap it accounts for."""

    cause: Cause
    amount_paise: int
    evidence_refund_ids: list[str] = []


class ExceptionVerdict(BaseModel):
    causes: list[CauseAttribution]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    suggested_action: str

    @property
    def primary_cause(self) -> Cause:
        """The cause accounting for the largest share of the gap."""
        if not self.causes:
            return Cause.UNKNOWN
        return max(self.causes, key=lambda c: c.amount_paise).cause

    @property
    def attributed_paise(self) -> int:
        """Only causes that actually explain something count. An unknown
        remainder is the opposite of an explanation."""
        return sum(
            c.amount_paise for c in self.causes if c.cause != Cause.UNKNOWN
        )
    
    @property
    def all_evidence_ids(self) -> list[str]:
        ids = []
        for c in self.causes:
            ids.extend(c.evidence_refund_ids)
        return ids

# Routing


class Route(str, Enum):
    AUTO_RESOLVED = "auto_resolved"
    ESCALATED = "escalated"
    UNRESOLVABLE = "unresolvable"


class ExceptionRecord(BaseModel):
    settlement_id: str
    settled_on: date
    gap_paise: int
    route: Route
    cause: Cause
    causes: list[CauseAttribution] = []
    coverage: float = 0.0
    confidence: float
    evidence_refund_ids: list[str]
    reasoning: str
    resolved_by: str