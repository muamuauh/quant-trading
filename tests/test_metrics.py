"""Tests for the report metrics (pure functions over a synthesised history)."""

from __future__ import annotations

import pandas as pd
from pytest import approx

from qtf.report.metrics import compute_metrics


def _history(rows):
    """Build a 5-column history frame from (date, total_assets, today_pnl) triples."""
    df = pd.DataFrame(rows, columns=["date", "total_assets", "today_pnl"])
    df["cash"] = 0.0
    df["market_val"] = df["total_assets"]
    df["positions"] = "[]"
    return df


def test_empty_history():
    m = compute_metrics(pd.DataFrame())
    assert m.days_recorded == 0
    assert m.inception_pnl_abs == 0.0
    assert m.win_rate == 0.0


def test_single_day_metrics():
    df = _history([("2026-05-20", 100_000.0, 0.0)])
    m = compute_metrics(df)
    assert m.days_recorded == 1
    assert m.first_equity == 100_000.0
    assert m.last_equity == 100_000.0
    assert m.inception_pnl_abs == 0.0
    assert m.max_drawdown_pct == 0.0
    assert m.peak_equity == 100_000.0


def test_growing_then_dropping_inception_pnl_and_drawdown():
    df = _history([
        ("2026-05-20", 100_000.0,    0.0),
        ("2026-05-21", 110_000.0, 10_000.0),  # peak
        ("2026-05-22", 105_000.0, -5_000.0),
        ("2026-05-23",  99_000.0, -6_000.0),  # max drawdown trough
        ("2026-05-24", 102_000.0,  3_000.0),
    ])
    m = compute_metrics(df)
    assert m.days_recorded == 5
    assert m.first_equity == 100_000.0
    assert m.last_equity == 102_000.0
    assert m.inception_pnl_abs == 2_000.0
    assert m.inception_pnl_pct == approx(0.02)
    assert m.peak_equity == 110_000.0
    assert m.peak_date == "2026-05-21"
    # max drawdown from 110k → 99k = -11k / 110k ≈ -0.10
    assert m.max_drawdown_date == "2026-05-23"
    assert m.max_drawdown_pct == approx(-0.10)
    assert m.positive_days == 2
    assert m.negative_days == 2
    assert m.win_rate == 0.5
    assert m.best_day_date == "2026-05-21"
    assert m.worst_day_date == "2026-05-23"


def test_current_drawdown_zero_at_peak():
    df = _history([
        ("2026-05-20", 100_000.0, 0.0),
        ("2026-05-21", 105_000.0, 5_000.0),
    ])
    m = compute_metrics(df)
    assert m.current_drawdown_pct == 0.0


def test_win_rate_skips_zero_pnl_days():
    df = _history([
        ("2026-05-20", 100_000.0,    0.0),  # zero — excluded from win rate
        ("2026-05-21", 102_000.0, 2_000.0),
        ("2026-05-22", 102_500.0,   500.0),
        ("2026-05-23", 101_500.0,-1_000.0),
    ])
    m = compute_metrics(df)
    assert m.positive_days == 2
    assert m.negative_days == 1
    assert m.win_rate == approx(2 / 3)
