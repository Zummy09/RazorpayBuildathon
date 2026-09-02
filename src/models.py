from enum import Enum
from datetime import datetime
from datetime import date
from pydantic import BaseModel, Field

#Payments

class Method(str, Enum):
    UPI ="upi"
    CARD = "card"
    NETBANKING ="netbanking"


class PaymentStatus(str, Enum):
    CAPTURED ="captured"
    AUTHORIZED ="authorized"
    FAILED ="failed"


class Payment(BaseModel):
    payment_id:str
    order_id:str
    amount_paise:int = Field(gt=0)
    method:Method
    status:PaymentStatus
    captured_at:datetime

#Refunds


class Refund(BaseModel):
    refund_id:str
    payment_id:str
    amount_paise: int =Field(gt=0)
    created_at:datetime


#Settlements
class Settlement(BaseModel):
    settlement_id: str
    utr: str
    net_amount_paise: int
    settled_at: datetime


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


class Cause(str, Enum):
    OLD_CYCLE_REFUND = "old_cycle_refund"
    ROUNDING = "rounding"
    UNKNOWN = "unknown"


class ExceptionVerdict(BaseModel):
    cause: Cause
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_refund_ids: list[str] = []
    suggested_action: str

class Cause(str, Enum):
    OLD_CYCLE_REFUND = "old_cycle_refund"
    ROUNDING = "rounding"
    UNKNOWN = "unknown"


class ExceptionVerdict(BaseModel):
    cause: Cause
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_refund_ids: list[str] = []
    suggested_action: str

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
    confidence: float
    evidence_refund_ids: list[str]
    reasoning: str
    resolved_by: str


class Cause(str, Enum):
    OLD_CYCLE_REFUND = "old_cycle_refund"
    CHARGEBACK = "chargeback"          # new
    ROUNDING = "rounding"
    UNKNOWN = "unknown"

class Chargeback(BaseModel):
    chargeback_id: str
    payment_id: str
    amount_paise: int = Field(gt=0)
    raised_at: datetime