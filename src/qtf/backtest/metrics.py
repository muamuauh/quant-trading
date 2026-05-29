"""Pure-function backtest metrics. No IO, fully unit-testable.

All return series are *daily simple returns* (e.g. 0.012 = +1.2% that day),
indexed by date.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


TRADING_DAYS = 252


@dataclass
class BacktestMetrics:
    n_days: int
    total_return: float          # cumulative, decimal (0.25 = +25%)
    annual_return: float         # annualized (CAGR), decimal
    annual_vol: float            # annualized volatility, decimal
    sharpe: float                # annualized, rf=0
    max_drawdown: float          # worst peak-to-trough, decimal (negative)
    calmar: float                # annual_return / |max_drawdown|
    win_rate: float              # fraction of up days
    best_day: float
    worst_day: float
    # vs benchmark (optional; 0 / NaN-safe when no benchmark)
    excess_annual_return: float  # strategy annual - benchmark annual

    def as_dict(self) -> dict:
        return asdict(self)


def equity_curve(daily_returns: pd.Series) -> pd.Series:
    """Compound daily returns into an equity curve starting at 1.0."""
    return (1.0 + daily_returns.fillna(0.0)).cumprod()


def max_drawdown(curve: pd.Series) -> float:
    """Worst peak-to-trough decline of an equity curve. Returns <= 0."""
    if curve.empty:
        return 0.0
    running_peak = curve.cummax()
    dd = curve / running_peak - 1.0
    return float(dd.min())


def compute_metrics(
    daily_returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
) -> BacktestMetrics:
    """Compute the standard backtest metric set from a daily-return series."""
    r = daily_returns.dropna()
    n = len(r)
    if n == 0:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    curve = equity_curve(r)
    total = float(curve.iloc[-1] - 1.0)
    # CAGR from per-period compounding
    years = n / TRADING_DAYS
    annual = float(curve.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0
    vol = float(r.std(ddof=1) * np.sqrt(TRADING_DAYS)) if n > 1 else 0.0
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS)) if (n > 1 and r.std(ddof=1) > 0) else 0.0
    mdd = max_drawdown(curve)
    calmar = float(annual / abs(mdd)) if mdd < 0 else 0.0
    up = int((r > 0).sum())
    down = int((r < 0).sum())
    win = up / (up + down) if (up + down) else 0.0

    excess = 0.0
    if benchmark_returns is not None:
        b = benchmark_returns.dropna()
        if len(b) > 0:
            b_curve = equity_curve(b)
            b_years = len(b) / TRADING_DAYS
            b_annual = float(b_curve.iloc[-1] ** (1.0 / b_years) - 1.0) if b_years > 0 else 0.0
            excess = annual - b_annual

    return BacktestMetrics(
        n_days=n,
        total_return=total,
        annual_return=annual,
        annual_vol=vol,
        sharpe=sharpe,
        max_drawdown=mdd,
        calmar=calmar,
        win_rate=win,
        best_day=float(r.max()),
        worst_day=float(r.min()),
        excess_annual_return=excess,
    )


def _pearson(x: pd.Series, y: pd.Series) -> float:
    """Pearson correlation computed manually.

    Avoids pandas' Series.corr -> numpy.corrcoef, which triggers a native
    crash (Windows 0xc06d007f) under this conda numpy/MKL build.
    """
    xc = x - x.mean()
    yc = y - y.mean()
    denom = float(np.sqrt((xc**2).sum()) * np.sqrt((yc**2).sum()))
    if denom == 0.0:
        return float("nan")
    return float((xc * yc).sum() / denom)


def information_coefficient(
    predictions: pd.Series,
    forward_returns: pd.Series,
) -> tuple[float, float]:
    """Mean daily cross-sectional IC (Pearson) and Rank IC (Spearman).

    Both series share a MultiIndex (datetime, instrument). For each date we
    correlate that day's predictions against realized forward returns across
    instruments, then average the per-day correlations.
    """
    df = pd.DataFrame({"pred": predictions, "fwd": forward_returns}).dropna()
    if df.empty:
        return 0.0, 0.0

    ics, rank_ics = [], []
    for _, day in df.groupby(level="datetime"):
        if len(day) < 3:
            continue
        ic = _pearson(day["pred"], day["fwd"])
        # Spearman = Pearson on ranks
        ric = _pearson(day["pred"].rank(), day["fwd"].rank())
        if pd.notna(ic):
            ics.append(ic)
        if pd.notna(ric):
            rank_ics.append(ric)

    ic_mean = float(np.mean(ics)) if ics else 0.0
    ric_mean = float(np.mean(rank_ics)) if rank_ics else 0.0
    return ic_mean, ric_mean
