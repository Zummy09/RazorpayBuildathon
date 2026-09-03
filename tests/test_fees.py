from src.fees import calculate_fee_paise, calculate_gst_paise, total_deduction_paise
from src.models import Method


def test_upi_is_free():
    """UPI carries no platform fee in India. ~70% of transactions."""
    assert calculate_fee_paise(500000, Method.UPI) == 0
    assert total_deduction_paise(500000, Method.UPI) == 0


def test_card_fee_is_two_percent():
    # Rs 1000 -> Rs 20
    assert calculate_fee_paise(100000, Method.CARD) == 2000


def test_gst_is_charged_on_the_fee_not_the_amount():
    fee = calculate_fee_paise(100000, Method.CARD)   # 2000 paise
    assert calculate_gst_paise(fee) == 360           # 18% of 2000


def test_fee_and_gst_round_independently():
    """Each is a separate line item on the merchant's invoice, so each
    must be a whole number of paise. Rounding once at the end would
    give a cleaner number that matches no real document."""
    amount = 183300                                   # Rs 1833
    fee = calculate_fee_paise(amount, Method.NETBANKING)
    gst = calculate_gst_paise(fee)

    assert fee == round(amount * 0.0175)
    assert gst == round(fee * 0.18)
    assert total_deduction_paise(amount, Method.NETBANKING) == fee + gst


def test_all_returns_are_whole_paise():
    for method in Method:
        assert isinstance(calculate_fee_paise(123456, method), int)
        assert isinstance(total_deduction_paise(123456, method), int)