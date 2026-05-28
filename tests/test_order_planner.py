"""Tests for the target-weight → orders diff."""

from __future__ import annotations

from qtf.execution.order_planner import plan_orders


def test_open_new_position():
    orders = plan_orders(
        target_weights={"US.AAPL": 0.5},
        current_qty={},
        last_close={"US.AAPL": 100.0},
        total_equity=10_000.0,
    )
    assert len(orders) == 1
    o = orders[0]
    assert o.code == "US.AAPL"
    assert o.side == "BUY"
    assert o.quantity == 50  # 0.5 * 10000 / 100 = 50
    assert o.price == round(100.0 * 1.002, 2)  # >=$1 -> 2 decimals (NMS Rule 612)


def test_close_existing_position():
    orders = plan_orders(
        target_weights={},
        current_qty={"US.AAPL": 50},
        last_close={"US.AAPL": 110.0},
        total_equity=10_000.0,
    )
    assert len(orders) == 1
    o = orders[0]
    assert o.side == "SELL"
    assert o.quantity == 50
    assert o.price == round(110.0 * 0.998, 2)


def test_penny_stock_uses_4_decimals():
    orders = plan_orders(
        target_weights={"US.PENNY": 1.0},
        current_qty={},
        last_close={"US.PENNY": 0.5},
        total_equity=100.0,
    )
    # 0.5 * 1.002 = 0.501 -> round to 4 decimals = 0.501
    assert orders[0].price == round(0.5 * 1.002, 4)


def test_regular_stock_strips_extra_decimals():
    orders = plan_orders(
        target_weights={"US.X": 0.5},
        current_qty={},
        last_close={"US.X": 311.7124},  # last_close already has 4-decimal noise
        total_equity=10_000.0,
    )
    # 311.7124 * 1.002 = 312.336... → 2 decimals = 312.34
    assert orders[0].price == 312.34


def test_rebalance_partial():
    orders = plan_orders(
        target_weights={"US.AAPL": 0.3, "US.MSFT": 0.3},
        current_qty={"US.AAPL": 50, "US.MSFT": 0},
        last_close={"US.AAPL": 100.0, "US.MSFT": 200.0},
        total_equity=10_000.0,
    )
    # AAPL target = floor(0.3 * 10000 / 100) = 30; need to SELL 20
    # MSFT target = floor(0.3 * 10000 / 200) = 15; need to BUY 15
    by_code = {o.code: o for o in orders}
    assert by_code["US.AAPL"].side == "SELL" and by_code["US.AAPL"].quantity == 20
    assert by_code["US.MSFT"].side == "BUY" and by_code["US.MSFT"].quantity == 15


def test_already_balanced_no_orders():
    orders = plan_orders(
        target_weights={"US.AAPL": 0.5},
        current_qty={"US.AAPL": 50},
        last_close={"US.AAPL": 100.0},
        total_equity=10_000.0,
    )
    assert orders == []


def test_missing_price_skipped():
    orders = plan_orders(
        target_weights={"US.UNKNOWN": 0.5},
        current_qty={},
        last_close={},
        total_equity=10_000.0,
    )
    assert orders == []
