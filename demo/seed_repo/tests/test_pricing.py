from app.pricing import apply_discount, average_item_price


def test_average_item_price():
    items = [{"price": 10.0}, {"price": 20.0}]
    assert average_item_price(items) == 15.0


def test_apply_discount():
    items = [{"price": 100.0}]
    assert apply_discount(items, 10) == 90.0
