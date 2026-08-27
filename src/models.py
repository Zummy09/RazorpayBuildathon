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