"""Tests for MoomooExecutor's snapshot pricing + stale-order cancellation.

run_skill is mocked so these never touch OpenD.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qtf.execution.moomoo_executor import MoomooExecutor


@pytest.fixture
def executor():
    # acc_id passed explicitly so it doesn't depend on .env
    return MoomooExecutor(acc_id=999, trd_env="SIMULATE")


def test_snapshot_prices_parses_last_price(executor):
    payload = {"data": [
        {"code": "US.ORCL", "last_price": 225.78},
        {"code": "US.CRM", "last_price": 191.1},
    ]}
    with patch("qtf.execution.moomoo_executor.run_skill", return_value=payload):
        prices = executor.snapshot_prices(["US.ORCL", "US.CRM"])
    assert prices == {"US.ORCL": 225.78, "US.CRM": 191.1}


def test_snapshot_prices_skips_zero_and_missing(executor):
    payload = {"data": [
        {"code": "US.AAA", "last_price": 0},      # zero -> skip
        {"code": "US.BBB", "last_price": 10.5},
        {"code": None, "last_price": 5.0},          # no code -> skip
    ]}
    with patch("qtf.execution.moomoo_executor.run_skill", return_value=payload):
        prices = executor.snapshot_prices(["US.AAA", "US.BBB"])
    assert prices == {"US.BBB": 10.5}


def test_snapshot_prices_empty_codes(executor):
    # no codes -> no skill call, empty dict
    with patch("qtf.execution.moomoo_executor.run_skill") as m:
        prices = executor.snapshot_prices([])
    assert prices == {}
    m.assert_not_called()


def test_cancel_open_orders_only_cancels_non_terminal(executor):
    orders_payload = {"orders": [
        {"order_id": "1", "code": "US.ORCL", "status": "SUBMITTED"},      # cancel
        {"order_id": "2", "code": "US.CRM", "status": "FILLED_ALL"},      # skip
        {"order_id": "3", "code": "US.V", "status": "WAITING_SUBMIT"},    # cancel
        {"order_id": "4", "code": "US.X", "status": "CANCELLED_ALL"},     # skip
    ]}
    calls = []

    def fake_run_skill(category, name, *args):
        if name == "get_orders":
            return orders_payload
        if name == "cancel_order":
            # args = ("--order-id", "1", "--acc-id", "999", "--trd-env", "SIMULATE")
            calls.append(args[1])
            return {"ok": True}
        raise AssertionError(f"unexpected call {name}")

    with patch("qtf.execution.moomoo_executor.run_skill", side_effect=fake_run_skill):
        cancelled = executor.cancel_open_orders()

    assert set(cancelled) == {"1", "3"}
    assert set(calls) == {"1", "3"}  # only non-terminal got cancel_order


def test_cancel_open_orders_none_open(executor):
    orders_payload = {"orders": [
        {"order_id": "1", "code": "US.CRM", "status": "FILLED_ALL"},
    ]}
    with patch("qtf.execution.moomoo_executor.run_skill", return_value=orders_payload):
        cancelled = executor.cancel_open_orders()
    assert cancelled == []
