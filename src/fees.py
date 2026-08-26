from src.models import Method

# Razorpay published rates, as decimals
FEE_RATES = {
    Method.UPI: 0.0,
    Method.CARD: 0.02,
    Method.NETBANKING: 0.0175,
}

GST_RATE = 0.18


def calculate_fee_paise(amount_paise: int, method: Method) -> int:
    """Platform fee for one payment, in whole paise."""
    rate = FEE_RATES[method]
    return round(amount_paise * rate)


def calculate_gst_paise(fee_paise: int) -> int:
    """GST charged on the platform fee, in whole paise."""
    return round(fee_paise * GST_RATE)


def total_deduction_paise(amount_paise: int, method: Method) -> int:
    """Fee plus GST for one payment, in whole paise."""
    fee = calculate_fee_paise(amount_paise, method)
    gst = calculate_gst_paise(fee)
    return fee + gst