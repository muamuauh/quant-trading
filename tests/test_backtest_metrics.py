"""Tests for backtest metrics (pure functions over synthetic returns)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pytest import approx

from qtf.backtest.metrics import (
    compute_metrics,
    equity_curve,
    information_coefficient,
    max_drawdown,
)


def _dates(n):
    return pd.date_range("2025-01-01", periods=n, freq="B")


def test_equity_curve_compounds():
    r = pd.Series([0.10, -0.10, 0.05], index=_dates(3))
    curve = equity_curve(r)
    # 1.1 * 0.9 * 1.05 = 1.0395
    assert curve.iloc[-1] == approx(1.0395)


def test_max_drawdown_simple():
    # up to 1.2, down to 0.9 -> dd = 0.9/1.2 - 1 = -0.25
    curve = pd.Series([1.0, 1.2, 1.08, 0.9, 1.0])
    assert max_drawdown(curve) == approx(-0.25)


def test_max_drawdown_monotonic_up_is_zero():
    curve = pd.Series([1.0, 1.1, 1.2, 1.3])
    assert max_drawdown(curve) == approx(0.0)


def test_compute_metrics_empty():
    m = compute_metrics(pd.Series([], dtype=float))
    assert m.n_days == 0
    assert m.sharpe == 0.0
    assert m.total_return == 0.0


def test_compute_metrics_positive_drift():
    # steady +0.1%/day for 252 days
    r = pd.Series([0.001] * 252, index=_dates(252))
    m = compute_metrics(r)
    assert m.n_days == 252
    assert m.total_return > 0.25          # ~ (1.001^252 - 1) ≈ 0.286
    assert m.annual_return == approx(m.total_return, rel=0.05)
    assert m.win_rate == 1.0
    assert m.max_drawdown == approx(0.0)
    assert m.sharpe > 0                    # positive, low vol -> very high


def test_compute_metrics_win_rate_excludes_zero_days():
    r = pd.Series([0.01, 0.0, -0.01, 0.02], index=_dates(4))
    m = compute_metrics(r)
    # 2 up, 1 down, 1 flat -> win = 2/3
    assert m.win_rate == approx(2 / 3)


def test_compute_metrics_excess_vs_benchmark():
    strat = pd.Series([0.002] * 252, index=_dates(252))
    bench = pd.Series([0.001] * 252, index=_dates(252))
    m = compute_metrics(strat, bench)
    assert m.excess_annual_return > 0      # strategy beats benchmark


def test_ic_perfect_positive():
    # predictions perfectly rank-correlate with forward returns each day
    idx = pd.MultiIndex.from_product(
        [_dates(2), ["a", "b", "c"]], names=["datetime", "instrument"]
    )
    pred = pd.Series([3, 2, 1, 3, 2, 1], index=idx, dtype=float)
    fwd = pd.Series([0.3, 0.2, 0.1, 0.6, 0.4, 0.2], index=idx, dtype=float)
    ic, rank_ic = information_coefficient(pred, fwd)
    assert rank_ic == approx(1.0)
    assert ic > 0.9


def test_ic_perfect_negative():
    idx = pd.MultiIndex.from_product(
        [_dates(2), ["a", "b", "c"]], names=["datetime", "instrument"]
    )
    pred = pd.Series([3, 2, 1, 3, 2, 1], index=idx, dtype=float)
    fwd = pd.Series([0.1, 0.2, 0.3, 0.2, 0.4, 0.6], index=idx, dtype=float)
    _, rank_ic = information_coefficient(pred, fwd)
    assert rank_ic == approx(-1.0)


def test_ic_empty():
    empty = pd.Series([], dtype=float,
                      index=pd.MultiIndex.from_tuples([], names=["datetime", "instrument"]))
    ic, rank_ic = information_coefficient(empty, empty)
    assert ic == 0.0 and rank_ic == 0.0
