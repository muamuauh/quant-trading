"""Tests for individual risk gates (no IO)."""

from __future__ import annotations

from qtf.execution.order_planner import Order
from qtf.risk.gates import (
    daily_loss_kill_switch,
    max_position_guard,
    min_cash_guard,
)


def test_max_position_guard_pass():
    res = max_position_guard({"US.AAPL": 0.3, "US.MSFT": 0.3}, {"max_position_pct": 0.4})
    assert res.passed


def test_max_position_guard_fail():
    res = max_position_guard({"US.AAPL": 0.7}, {"max_position_pct": 0.4})
    assert not res.passed
    assert "US.AAPL" in res.reason


def test_min_cash_guard_pass():
    orders = [Order(code="US.AAPL", side="BUY", quantity=10, price=100.0, reason="x")]
    # buying 10 * 100 = 1000; cash 5000 - 1000 = 4000; equity 10000; floor 500
    res = min_cash_guard(orders, current_cash=5000.0, total_equity=10000.0,
                          limits={"min_cash_buffer_pct": 0.05})
    assert res.passed


def test_min_cash_guard_fail():
    orders = [Order(code="US.AAPL", side="BUY", quantity=50, price=100.0, reason="x")]
    # buying 50 * 100 = 5000; cash 5000 - 5000 = 0; floor 500
    res = min_cash_guard(orders, current_cash=5000.0, total_equity=10000.0,
                          limits={"min_cash_buffer_pct": 0.05})
    assert not res.passed


def test_daily_loss_blocks_buys():
    orders = [Order(code="US.AAPL", side="BUY", quantity=10, price=100.0, reason="x")]
    res = daily_loss_kill_switch(orders, today_pnl=-300.0, total_equity=10000.0,
                                  limits={"max_daily_loss_pct": 0.02})
    # loss 3% > cap 2% → fail
    assert not res.passed


def test_daily_loss_allows_sells():
    orders = [Order(code="US.AAPL", side="SELL", quantity=10, price=100.0, reason="x")]
    res = daily_loss_kill_switch(orders, today_pnl=-300.0, total_equity=10000.0,
                                  limits={"max_daily_loss_pct": 0.02})
    assert res.passed  # no BUYs → no block


def test_daily_loss_within_limit():
    orders = [Order(code="US.AAPL", side="BUY", quantity=10, price=100.0, reason="x")]
    res = daily_loss_kill_switch(orders, today_pnl=-100.0, total_equity=10000.0,
                                  limits={"max_daily_loss_pct": 0.02})
    assert res.passed  # 1% loss < 2% cap
